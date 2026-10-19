"""The conformance cases. Each is driver-neutral and names the scenario it drives; the
driver's adapter maps the scenario to its own input.

The topics are the Phase 3 plan's list for Task 3f.1 (from the core plan's Phase 4) plus the
protocol's own. Every topic has at least one case, and every case applies to at least one
driver (`test_driver_conformance`).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context_pack import STABLE_LAYERS, ContextLayer, tool_return_text
from e_agent.contracts.grounding import Citation, ProposalRationale
from e_agent.sdk.errors import DriverBudgetExceeded
from e_agent.sdk.ports import (
    AgentDriver,
    AskClarification,
    DriverStep,
    FinalAnswer,
    GroundingOffer,
    Observation,
    ProposeAction,
    ProposePlan,
    RequestReads,
)

from . import world
from .harness import DriverAdapter, ModelView, NoModel, Subject
from .world import (
    CREATE_DRAFT_PO,
    DRAFT_PO_TASK,
    SHORTAGE_ANSWER,
    SHORTAGE_TASK,
    SHORTAGE_TOOLS,
    VERIFIED,
    Host,
    World,
    advance,
    ctx,
    emitted_contracts,
    shape,
    to_proposal,
)

TOPICS = (
    "tools",
    "deferred",
    "resume",
    "pack",
    "clearing",
    "findings",
    "repair",
    "grounding",
    "budget",
    "hygiene",
    "protocol",
)
"""The plan's ten topics, in its order, then the protocol's own."""

CaseRun = Callable[[DriverAdapter, World], Awaitable[None]]


@dataclass(frozen=True)
class Case:
    case_id: str
    topic: str
    checks: str
    run: CaseRun


CASES: list[Case] = []


def case(case_id: str, checks: str) -> Callable[[CaseRun], CaseRun]:
    topic = case_id.split(".", 1)[0]
    assert topic in TOPICS, f"{case_id}: unknown topic"

    def register(run: CaseRun) -> CaseRun:
        assert all(c.case_id != case_id for c in CASES), f"{case_id} registered twice"
        CASES.append(Case(case_id, topic, checks, run))
        return run

    return register


def _views(subject: Subject) -> list[ModelView] | None:
    """The subject's model views, or None for a driver without a model."""
    try:
        return subject.views()
    except NoModel:
        return None


def _proposal(step: DriverStep) -> ProposeAction:
    assert isinstance(step, ProposeAction), f"expected a proposal, got {step!r}"
    return step


REPAIR_STEPS = (ProposeAction, ProposePlan, AskClarification)


# ---------------------------------------------------------------------------- tools
@case(
    "tools.offered_equals_allowed",
    "every model request offers exactly the run's allowed_capabilities as business tools",
)
async def offered_equals_allowed(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("shortage-off-tool")
    run = ctx("run-tools-offered", max_admitted_writes=0)
    host = Host(SHORTAGE_TASK, allowed=SHORTAGE_TOOLS)
    await to_proposal(subject.driver, run, host)
    views = subject.views()
    assert views
    for view in views:
        assert view.offered == set(SHORTAGE_TOOLS), view.offered


@case(
    "tools.calls_within_allowed",
    "every read and proposal stays inside allowed_capabilities, and the run still answers",
)
async def calls_within_allowed(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("shortage-off-tool")
    run = ctx("run-tools-calls", max_admitted_writes=0)
    host = Host(SHORTAGE_TASK, allowed=SHORTAGE_TOOLS)
    steps = await to_proposal(subject.driver, run, host)
    outside = [c for c in emitted_contracts(steps) if c not in SHORTAGE_TOOLS]
    assert not outside, f"calls outside the tool set: {outside}"
    assert _proposal(steps[-1]).proposal.contract_id == SHORTAGE_ANSWER


# ------------------------------------------------------------------------- deferred
@case(
    "deferred.reads_then_write",
    "reads come back as RequestReads, a write as ProposeAction that runs nothing, and the "
    "host's result ends in a final answer",
)
async def reads_then_write(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po")
    run = ctx("run-deferred")
    host = Host(DRAFT_PO_TASK)
    steps = await to_proposal(subject.driver, run, host)
    for step in steps[:-1]:
        assert isinstance(step, RequestReads) and step.reads
        ids = [read.request_id for read in step.reads]
        assert len(ids) == len(set(ids)), "request ids repeat"
        assert {w.effects[read.contract_id] for read in step.reads} == {EffectKind.READ}
    proposal = _proposal(steps[-1]).proposal
    assert proposal.contract_id == CREATE_DRAFT_PO
    assert w.effects[proposal.contract_id] is EffectKind.WRITE
    before = _views(subject)
    final = await advance(subject.driver, run, host, action_result=VERIFIED)
    assert isinstance(final, FinalAnswer) and final.text.strip()
    if before is not None:  # the write's return is the host's result, and only after it
        last = (_views(subject) or [])[-1]
        [write] = set(last.call_ids) - set(before[-1].call_ids)
        assert last.returns[write] == VERIFIED
        assert not any(write in view.return_ids for view in before)


@case(
    "deferred.mixed_turn_defers_write",
    "a write asked together with reads is not proposed until the reads have returned",
)
async def mixed_turn(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("mixed")
    run = ctx("run-mixed")
    host = Host(DRAFT_PO_TASK)
    first = await advance(subject.driver, run, host)
    assert isinstance(first, RequestReads)
    assert {w.effects[read.contract_id] for read in first.reads} == {EffectKind.READ}
    second = await advance(subject.driver, run, host)
    assert _proposal(second).proposal.contract_id == CREATE_DRAFT_PO
    views = _views(subject)
    if views is not None:  # the early write was answered with a refusal, never run
        early = set(views[1].call_ids) - {read.request_id for read in first.reads}
        refused = [views[1].returns[call_id] for call_id in early]
        assert refused and all("error" in r for r in refused), refused


# --------------------------------------------------------------------------- resume
@case(
    "resume.after_restart",
    "a driver resumed after every turn, as the kernel resumes it, returns the same steps as "
    "one that never stopped",
)
async def after_restart(adapter: DriverAdapter, w: World) -> None:
    turns: tuple[dict[str, Any], ...] = (
        {},
        {},
        {"findings": (world.finding(),)},
        {"action_result": VERIFIED},
    )
    for packed in (False, True):
        control, resumed = adapter.subject("draft-po-repair"), adapter.subject("draft-po-repair")
        run = ctx(f"run-resume-{packed}")
        hosts = Host(DRAFT_PO_TASK, packed=packed), Host(DRAFT_PO_TASK, packed=packed)
        for index, kw in enumerate(turns):
            expected = await advance(control.driver, run, hosts[0], **kw)
            resumed.restart(run.run_id)
            got = await advance(resumed.driver, run, hosts[1], **kw)
            assert shape(got) == shape(expected), f"pack={packed}, turn {index}: {got!r}"
        assert isinstance(expected, FinalAnswer)


@case(
    "resume.rendering_marker",
    "a run that rendered a pack keeps rendering: pack through a restore and a later turn "
    "without one; a run that never did has no marker, and a restore changes nothing",
)
async def rendering_marker(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po")
    off, on = ctx("run-marker-off"), ctx("run-marker-on")
    host = Host(DRAFT_PO_TASK)
    await advance(subject.driver, off, host)
    plain = subject.snapshot(off.run_id)
    assert plain is not None and "rendering" not in plain
    subject.restart(off.run_id)
    assert subject.snapshot(off.run_id) == json.loads(json.dumps(plain))

    packed = Host(DRAFT_PO_TASK, packed=True)
    await advance(subject.driver, on, packed)
    marked = subject.snapshot(on.run_id)
    assert marked is not None and marked["rendering"] == "pack"
    subject.restart(on.run_id, off.run_id)
    assert subject.snapshot(on.run_id) == json.loads(json.dumps(marked))
    packed.packed = False  # a later turn without a pack keeps the marker
    await advance(subject.driver, on, packed)
    later = subject.snapshot(on.run_id)
    assert later is not None and later["rendering"] == "pack"


@case(
    "resume.continuation_both_or_neither",
    "a driver has both snapshot and restore or neither, and a run it never saw has no snapshot",
)
async def both_or_neither(adapter: DriverAdapter, w: World) -> None:
    driver = adapter.subject("draft-po").driver
    has = hasattr(driver, "snapshot"), hasattr(driver, "restore")
    assert has[0] == has[1], f"snapshot/restore: {has}"
    if has[0]:
        assert driver.snapshot("run-never-seen") is None  # type: ignore[attr-defined]


# ----------------------------------------------------------------------------- pack
SENTINEL = "supplier:SENTINEL-not-in-the-pack"


def _corrupted(observation: Observation) -> Observation:
    """The observation with every supplier ref replaced: what the driver is handed is not
    what the pack rendered."""
    text = json.dumps(observation.data).replace("supplier:approved-co", SENTINEL)
    return Observation(
        request_id=observation.request_id,
        contract_id=observation.contract_id,
        data=json.loads(text),
        evidence=observation.evidence,
    )


@case(
    "pack.only_pack_reaches_model",
    "with a pack, the driver reads observations only from it: Observation.data never reaches "
    "the model or the step, and each tool return is the pack's tool_return_text",
)
async def only_pack(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po")
    run = ctx("run-pack-only")
    host = Host(DRAFT_PO_TASK, packed=True, handed=_corrupted)
    steps = await to_proposal(subject.driver, run, host)
    steps.append(await advance(subject.driver, run, host, action_result=VERIFIED))
    assert SENTINEL not in repr([shape(step) for step in steps])
    assert _proposal(steps[-2]).proposal.arguments["supplier_ref"] == "supplier:approved-co"
    views = _views(subject)
    if views is None:
        return
    rendered = {o.evidence.evidence_id: tool_return_text(o) for o in host.packs[-1].observations}
    for view in views:
        assert SENTINEL not in view.sent
    for call_id, content in views[-1].returns.items():
        if world.evidence_id(call_id) in rendered:
            assert content == rendered[world.evidence_id(call_id)]


@case(
    "pack.stable_prefix_unchanged",
    "every request of a pack run has the same instructions, holding the stable prefix and "
    "never the dynamic suffix, which is the request's last user prompt",
)
async def stable_prefix(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po-repair")
    run = ctx("run-prefix")
    host = Host(DRAFT_PO_TASK, packed=True)
    await to_proposal(subject.driver, run, host)
    await advance(subject.driver, run, host, findings=(world.finding(),))
    await advance(subject.driver, run, host, action_result=VERIFIED)
    views = subject.views()
    assert len(views) == len(host.packs) == 4
    assert len({view.instructions for view in views}) == 1
    for view, pack in zip(views, host.packs, strict=True):
        for layer in STABLE_LAYERS:
            if text := pack.stable_prefix.get(layer):
                assert text in view.instructions, layer
        ledger = pack.dynamic_suffix[ContextLayer.LEDGER]
        assert ledger not in view.instructions
        assert ledger in view.prompts[-1]


# ------------------------------------------------------------------------- clearing
@case(
    "clearing.cleared_is_not_read",
    "a cleared observation is not read as a fact: its data reaches neither the model nor a "
    "proposal",
)
async def cleared_not_read(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po")
    run = ctx("run-cleared")
    host = Host(DRAFT_PO_TASK, packed=True)
    await advance(subject.driver, run, host)
    step = await advance(subject.driver, run, host, pack_turn=host.turn + 9)
    assert all(o.truncated for o in host.packs[-1].observations), "the pack cleared nothing"
    unread = "supplier:unvetted-co"  # only in the offers read's data
    assert unread not in repr(shape(step))
    views = _views(subject)
    if views is None:  # no model: a proposal could only come from the cleared data
        assert isinstance(step, FinalAnswer | AskClarification), f"proposed from it: {step!r}"
    else:  # a model may still propose; it never saw the data
        assert unread not in views[-1].sent


@case(
    "clearing.keeps_call_return_pairs",
    "clearing keeps every tool call and its return, ids and order unchanged, with the pack's "
    "stub as the return",
)
async def keeps_pairs(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po")
    run = ctx("run-pairs")
    host = Host(DRAFT_PO_TASK, packed=True)
    await to_proposal(subject.driver, run, host)
    final = await advance(
        subject.driver, run, host, action_result=VERIFIED, pack_turn=host.turn + 9
    )
    assert isinstance(final, FinalAnswer)
    last = subject.views()[-1]
    assert last.call_ids == last.return_ids and len(last.call_ids) == 4
    stubs = {o.evidence.evidence_id: tool_return_text(o) for o in host.packs[-1].observations}
    reads = [i for i in last.return_ids if world.evidence_id(i) in stubs]
    assert len(reads) == 3
    for call_id in reads:
        content = last.returns[call_id]
        assert content == stubs[world.evidence_id(call_id)]
        assert json.loads(content)["data"] == {"omitted": "cleared"}


@case(
    "clearing.not_while_pending",
    "while a write is pending nothing is cleared, even when the pack asks; the write's result "
    "ends the wait",
)
async def not_while_pending(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po-repair")
    run = ctx("run-pending")
    host = Host(DRAFT_PO_TASK, packed=True)
    await to_proposal(subject.driver, run, host)
    before = {o.evidence.evidence_id: tool_return_text(o) for o in host.packs[-1].observations}
    step = await advance(
        subject.driver,
        run,
        host,
        findings=(world.finding(),),
        pack_turn=host.turn + 9,
        deferred_pending=False,  # the pack asks to clear
    )
    assert isinstance(step, ProposeAction)
    assert all(o.truncated for o in host.packs[-1].observations)
    pending = subject.views()[-1]
    for call_id in pending.return_ids:
        if world.evidence_id(call_id) in before:
            assert pending.returns[call_id] == before[world.evidence_id(call_id)]
    await advance(subject.driver, run, host, action_result=VERIFIED, pack_turn=host.turn + 9)
    done = subject.views()[-1]
    assert done.call_ids == done.return_ids
    for call_id in done.return_ids:
        if world.evidence_id(call_id) in before:
            assert json.loads(done.returns[call_id])["data"] == {"omitted": "cleared"}


# ------------------------------------------------------------------------- findings
@case(
    "findings.in_suffix_not_history",
    "with a pack, a finding's text reaches the model in the request-only suffix, never in a "
    "tool return or the persisted history",
)
async def findings_in_suffix(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po-repair")
    run = ctx("run-findings")
    host = Host(DRAFT_PO_TASK, packed=True)
    await to_proposal(subject.driver, run, host)
    text = "FINDING-TEXT-only-in-the-suffix"
    step = await advance(subject.driver, run, host, findings=(world.finding(text),))
    assert isinstance(step, REPAIR_STEPS)
    view = subject.views()[-1]
    assert text in view.prompts[-1]
    assert text not in json.dumps(view.returns, default=str)
    assert text not in "".join(view.prompts[:-1])
    assert text not in json.dumps(subject.snapshot(run.run_id))
    await advance(subject.driver, run, host, action_result=VERIFIED)
    assert text not in subject.views()[-1].sent
    assert text not in json.dumps(subject.snapshot(run.run_id))


# --------------------------------------------------------------------------- repair
@case(
    "repair.new_proposal_or_clarification",
    "a blocked proposal's findings get a new proposal or a clarification, with and without a pack",
)
async def repair(adapter: DriverAdapter, w: World) -> None:
    for packed in (False, True):
        subject = adapter.subject("draft-po-repair")
        run = ctx(f"run-repair-{packed}")
        host = Host(DRAFT_PO_TASK, packed=packed)
        await to_proposal(subject.driver, run, host)
        step = await advance(subject.driver, run, host, findings=(world.finding(),))
        assert isinstance(step, REPAIR_STEPS), f"pack={packed}: {step!r}"


@case(
    "repair.never_silent",
    "a reply with no public content after a finding is a clarification, never an empty answer",
)
async def never_silent(adapter: DriverAdapter, w: World) -> None:
    for packed in (False, True):
        subject = adapter.subject("repair-silent")
        run = ctx(f"run-silent-{packed}")
        host = Host(DRAFT_PO_TASK, packed=packed)
        await to_proposal(subject.driver, run, host)
        step = await advance(subject.driver, run, host, findings=(world.finding(),))
        assert isinstance(step, REPAIR_STEPS), f"pack={packed}: {step!r}"
        if isinstance(step, AskClarification):
            assert step.question.strip()


# ------------------------------------------------------------------------ grounding
def _no_envelope_arguments(proposal: ProposeAction) -> None:
    arguments = proposal.proposal.arguments
    assert "citations" not in arguments and "rationale" not in arguments, arguments


@case(
    "grounding.citations_in_envelope",
    "with grounding offered, an answer's citations have the Citation shape, name this run's "
    "evidence and travel in the envelope, never in the arguments",
)
async def citations(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("shortage-cited")
    run = ctx("run-cited", max_admitted_writes=0)
    host = Host(SHORTAGE_TASK, grounding=GroundingOffer.CITE)
    step = _proposal((await to_proposal(subject.driver, run, host))[-1])
    assert step.proposal.contract_id == SHORTAGE_ANSWER
    _no_envelope_arguments(step)
    cited = step.proposal.citations
    assert cited and all(isinstance(c, Citation) for c in cited)
    assert {c.evidence_id for c in cited} <= host.evidence_ids
    assert all(c.pointer.startswith("/") for c in cited)


@case(
    "grounding.rationale_in_envelope",
    "with grounding offered, a write's rationale is a ProposalRationale naming this run's "
    "evidence, in the envelope, never in the arguments",
)
async def rationale(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po-rationale")
    run = ctx("run-rationale")
    host = Host(DRAFT_PO_TASK, grounding=GroundingOffer.CITE)
    step = _proposal((await to_proposal(subject.driver, run, host))[-1])
    assert step.proposal.contract_id == CREATE_DRAFT_PO
    _no_envelope_arguments(step)
    why = step.proposal.rationale
    assert isinstance(why, ProposalRationale)
    assert why.cited_evidence and set(why.cited_evidence) <= host.evidence_ids


@case(
    "grounding.off_offers_nothing",
    "with grounding off, no tool offers citations or rationale and a proposal carries "
    "neither, even when the model sends them",
)
async def grounding_off(adapter: DriverAdapter, w: World) -> None:
    for scenario, task, writes in (
        ("shortage-cited", SHORTAGE_TASK, 0),
        ("draft-po-rationale", DRAFT_PO_TASK, 1),
    ):
        subject = adapter.subject(scenario)
        run = ctx(f"run-off-{scenario}", max_admitted_writes=writes)
        step = _proposal((await to_proposal(subject.driver, run, Host(task)))[-1])
        _no_envelope_arguments(step)
        assert step.proposal.citations == () and step.proposal.rationale is None
        for view in _views(subject) or []:
            for schema in view.schemas.values():
                assert not {"citations", "rationale"} & set(schema.get("properties", {}))


@case(
    "grounding.mode_from_input_only",
    "the grounding offer follows each call's DriverInput.grounding, never earlier calls",
)
async def mode_per_call(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("shortage-cited-thrice")
    offers = (GroundingOffer.CITE, GroundingOffer.OFF, GroundingOffer.CITE)
    for index, offer in enumerate(offers):
        run = ctx(f"run-mode-{index}", max_admitted_writes=0)
        step = _proposal(
            (await to_proposal(subject.driver, run, Host(SHORTAGE_TASK, grounding=offer)))[-1]
        )
        _no_envelope_arguments(step)
        assert bool(step.proposal.citations) is (offer is GroundingOffer.CITE), offer


# --------------------------------------------------------------------------- budget
@case(
    "budget.tokens_respected",
    "once the run's model tokens reach max_model_tokens, every turn raises "
    "DriverBudgetExceeded without another model request",
)
async def tokens(adapter: DriverAdapter, w: World) -> None:
    subject = adapter.subject("draft-po")
    run = ctx("run-budget", max_model_tokens=1)
    host = Host(DRAFT_PO_TASK)
    try:
        await advance(subject.driver, run, host)
    except DriverBudgetExceeded:
        pass
    else:
        raise AssertionError("a turn over max_model_tokens did not raise")
    spent = len(subject.views())
    assert spent <= 1, "more than one model request after the budget was spent"
    for _ in range(2):
        try:
            await advance(subject.driver, run, host)
        except DriverBudgetExceeded:
            pass
        else:
            raise AssertionError("a turn after the budget was spent did not raise")
        assert len(subject.views()) == spent, "a model request after the budget was spent"


# -------------------------------------------------------------------------- hygiene
@case(
    "hygiene.no_hidden_reasoning",
    "thinking parts and reasoning tags reach no step, no persisted snapshot and no later "
    "request, with and without a pack",
)
async def no_reasoning(adapter: DriverAdapter, w: World) -> None:
    from .adapters import SECRET_TAG, SECRET_THINKING

    for packed in (False, True):
        subject = adapter.subject("thinking")
        run = ctx(f"run-thinking-{packed}")
        host = Host(DRAFT_PO_TASK, packed=packed)
        steps = await to_proposal(subject.driver, run, host)
        steps.append(await advance(subject.driver, run, host, action_result=VERIFIED))
        assert isinstance(steps[-1], FinalAnswer) and steps[-1].text.strip()
        persisted = json.dumps(subject.snapshot(run.run_id))
        for secret in (SECRET_THINKING, SECRET_TAG, "<think>"):
            assert secret not in repr([shape(s) for s in steps])
            assert secret not in persisted
            assert not any(secret in v.sent for v in subject.views()[1:])


# ------------------------------------------------------------------------- protocol
@case("protocol.identity", "the driver is an AgentDriver with a non-empty driver_id")
async def identity(adapter: DriverAdapter, w: World) -> None:
    driver = adapter.subject("draft-po").driver
    assert isinstance(driver, AgentDriver)
    assert isinstance(driver.driver_id, str) and driver.driver_id.strip()


@case(
    "protocol.host_chooses_connection",
    "every read and proposal names the host's connection, never one from model output",
)
async def connection(adapter: DriverAdapter, w: World) -> None:
    for scenario, task, writes in (("draft-po", DRAFT_PO_TASK, 1), ("shortage", SHORTAGE_TASK, 0)):
        subject = adapter.subject(scenario)
        run = ctx(f"run-conn-{scenario}", max_admitted_writes=writes)
        for step in await to_proposal(subject.driver, run, Host(task)):
            if isinstance(step, RequestReads):
                assert {r.connection_id for r in step.reads} == {subject.connection_id}
            else:
                assert _proposal(step).proposal.connection_id == subject.connection_id


@case(
    "protocol.runs_isolated",
    "two runs that take turns on one driver return the same steps as each run alone",
)
async def isolated(adapter: DriverAdapter, w: World) -> None:
    async def steps_of(driver: AgentDriver, runs: list[str]) -> dict[str, list[Any]]:
        hosts = {r: Host(DRAFT_PO_TASK) for r in runs}
        seen: dict[str, list[Any]] = {r: [] for r in runs}
        for kw in ({}, {}, {"findings": (world.finding(),)}):
            for r in runs:
                seen[r].append(shape(await advance(driver, ctx(r), hosts[r], **kw)))
        return seen

    alone = await steps_of(adapter.subject("draft-po-repair").driver, ["run-a"])
    together = await steps_of(adapter.subject("draft-po-repair-twice").driver, ["run-a", "run-b"])
    assert together["run-a"] == alone["run-a"]
    assert together["run-b"] == alone["run-a"]
    assert [found[0] for found in alone["run-a"]][1:] == ["propose", "propose"]
