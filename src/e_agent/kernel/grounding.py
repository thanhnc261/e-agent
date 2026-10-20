"""``features.grounded_answers`` for typed answers: checked citations (ADR 0033 §1, §2, §5,
Task 3e.1, Review Focus 5 and 7).

**The check** (`check_citations`, pure). A citation resolves when its ``evidence_id`` names
an observation of **this run** (the observations passed in, which the kernel takes from the
run's continuation only, never from the store or the tenant: Review Focus 5, threat T6), its
RFC 6901 ``pointer`` exists in that observation's ``data``, and the value there equals the
cited value: equal ``jcs-sha256-v1`` digests (ADR 0006), with every JSON number written as
its canonical decimal string first, as the context pack renders it (``number_text``). A
pointer that names nothing, or is not RFC 6901, is unresolved. The check makes no provider
read and no model call. In a run pinned ``context_assembler: on`` it reads the data as the
pack's class walk shows it to the model (`ClassView`): a masked value or a removed key is
unresolved, exactly like a key that does not exist, and a cited marker never resolves, so
the check is no oracle on what the pack withheld (review R1-1, PR-26).

**The answer path** (`_handle_answer`, per the run's pinned mode, `_run_modes`):

- ``off``: today. Citations are dropped: nothing is checked, recorded or stored.
- ``shadow``: the answer goes to its verifier as today. Its own write (``proposal.created``)
  carries the citations at rest and ``grounding.compared`` (counts and per-citation
  verdicts), so the run's revision is today's. A check error records
  ``grounding.shadow_failed`` with its stage and a fixed message instead, and changes
  nothing else.
- ``on``: before the answer's action exists and before its verifier reads, an unresolved or
  mismatched citation is the repair finding ``KERNEL-CITATION`` (one per citation, its
  evidence id and pointer, never a value), returned within ``max_validation_repairs`` and
  recorded in ``validation.completed`` with no action id, as digests when the citation named
  nothing (`repair_at_rest`, Task 3.R1). When every citation resolves the answer takes
  today's path and its verifier decides (PR-19).

**At rest** a citation is ``value_digest``, never the value (PR-26), with ``evidence_id`` and
``pointer`` verbatim only when they named a value of this run's evidence, else their digests
(`kernel/at_rest.py`, Task 3.R1), under ``citations`` in ``proposal.created``, only for a run
pinned ``shadow`` or ``on`` with at least one checked citation. ``ActionRecord`` gains no
field, and the domain answer's arguments never hold the citations.

**Failure** (ADR 0027): a check that cannot run in ``on`` records ``feature.fallback``
``GROUNDING_CHECK_FAILED`` before the run's first reservation (no ``action.reserved``
event), and the answer goes to its verifier as today with its citations dropped; after one,
the run fails closed with ``GROUNDING_UNAVAILABLE``, in reconciliation while a reservation
is unresolved (`_end_closed`). No event carries exception text, a cited value or an
observed value.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from e_agent.contracts import data_classes as dc
from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.common import new_id
from e_agent.contracts.context_pack import DroppedReason, masked_marker
from e_agent.contracts.data_classes import parse_pointer
from e_agent.contracts.digest import CanonicalizationError, digest
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.grounding import Citation, CitationCounts, GroundingCompared
from e_agent.contracts.outcome import OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunRecord, RunState
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.sdk.ports import DriverInput, Observation
from e_agent.sdk.store import EventSpec

from .approval import compute_digest
from .at_rest import citation_at_rest, finding_at_rest, repair_at_rest
from .context import ClassLookup, context_route
from .context_on import ON_POLICY
from .context_walk import Walker, _plain
from .continuation import _Continuation, _GatewayReader
from .errors import KernelError
from .reconstruct import proposal_keys
from .repeat import INVALID_DIGEST, RepeatMixin
from .verification import outcome_payload

KERNEL_CITATION = "KERNEL-CITATION"


class CitationStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    """No observation of this run has the evidence id, or its data has no value at the
    pointer (or the pointer is not RFC 6901)."""
    MISMATCHED = "mismatched"
    """The value at the pointer is not the cited value."""


CITATION_MESSAGES = MappingProxyType(
    {
        CitationStatus.UNRESOLVED: "This citation names no evidence of this run, or no value "
        "at its pointer; cite a value this run read.",
        CitationStatus.MISMATCHED: "The cited value is not the value at the pointer in the "
        "cited evidence.",
    }
)
"""The fixed message of each ``KERNEL-CITATION`` repair finding, by status."""
GROUNDING_SHADOW_MESSAGE = "The grounding check could not run."
"""The fixed ``grounding.shadow_failed`` message of the ``check`` stage."""
REPEATED_ANSWER = "The structured answer was independently verified."

_INDEX = re.compile(r"0|[1-9][0-9]*")
_MISSING = object()


def value_digest(value: Any) -> str:
    """The ``jcs-sha256-v1`` digest of a JSON value, every number as its canonical decimal
    string (ADR 0006). Raises `KernelError` or `CanonicalizationError` for a value outside
    the profile."""
    return digest(_plain(value))


def _tokens(pointer: str) -> tuple[str, ...] | None:
    """The pointer's reference tokens, or None when it is not RFC 6901."""
    if pointer == "":
        return ()
    try:
        return parse_pointer(pointer)
    except ValueError:
        return None


def _follow(
    node: Any, tokens: tuple[str, ...], positions: Mapping[int, list[int]] | None = None
) -> tuple[Any, tuple[str, ...]]:
    """The value at ``tokens`` (``_MISSING`` when there is none) and its pointer in the
    original data: ``positions`` maps a rendered list to its members' original indices."""
    original: list[str] = []
    for token in tokens:
        if isinstance(node, Mapping):
            if token not in node:
                return _MISSING, ()
            node = node[token]
            original.append(token)
        elif isinstance(node, list | tuple):
            if not _INDEX.fullmatch(token) or int(token) >= len(node):
                return _MISSING, ()
            index, at = int(token), (positions or {}).get(id(node))
            original.append(str(at[index] if at else index))
            node = node[index]
        else:
            return _MISSING, ()
    return node, tuple(original)


def _value_at(data: Any, pointer: str) -> Any:
    """The value at an RFC 6901 pointer in raw data, or ``_MISSING``."""
    tokens = _tokens(pointer)
    return _MISSING if tokens is None else _follow(data, tokens)[0]


MARKERS = frozenset(masked_marker(c) for c in dc.DataClass if c is not dc.DataClass.SECRET)
"""The markers the class walk writes: a secret is never masked, only removed
(`ContextPolicy` refuses any other action for it)."""


def _holds_marker(value: Any) -> bool:
    if isinstance(value, str):
        return value in MARKERS
    if isinstance(value, Mapping):
        return any(_holds_marker(v) for v in value.values())
    if isinstance(value, list | tuple):
        return any(_holds_marker(v) for v in value)
    return False


class ClassView:
    """Observation data as the context pack's class walk renders it to the model, for a run
    pinned ``context_assembler: on`` (review R1-1, PR-26): the same `Walker`, class
    declarations and route row as `assemble`, so masking and secret removal apply, never
    the per-turn size bound. A value at or above any class-walk removal (a masked value, a
    removed secret, an unnamed key left out, all logged as ``class_route`` drops) is no
    value, so a reduced container never resolves: the check is never an oracle on what the
    pack withheld, nor grounds a claim the provider data contradicts (R1-1, R2-1)."""

    def __init__(self, classes: ClassLookup, route: Mapping[str, Any]) -> None:
        self._classes = classes
        self._rules = ON_POLICY.class_rules[context_route(route)]
        self._walked: dict[int, tuple[Walker, dict[str, Any], set[tuple[str, ...]]]] = {}

    def value_at(self, observation: Observation, pointer: str) -> Any:
        tokens = _tokens(pointer)
        if tokens is None:
            return _MISSING
        if id(observation) not in self._walked:
            index = dc.ClassIndex(self._classes(observation.contract_id))
            walker = Walker(index, self._rules, observation.evidence.evidence_id)
            rendered = walker.root(observation.data)
            removed = _removals(walker, observation.evidence.evidence_id)
            self._walked[id(observation)] = (walker, rendered, removed)
        walker, rendered, removed = self._walked[id(observation)]
        value, at = _follow(rendered, tokens, walker.positions)
        if value is _MISSING or any(p[: len(at)] == at for p in removed):
            return _MISSING
        return value


def _removals(walker: Walker, evidence_id: str) -> set[tuple[str, ...]]:
    """The original pointers of the walk's class removals: each ``class_route`` drop names
    a masked or removed value, or the parent of the unnamed keys it left out."""
    removed = {tuple(p) for p in walker.mask_pointers}
    prefix = f"{evidence_id}#"
    for drop in walker.drops:
        if drop.reason is DroppedReason.CLASS_ROUTE and drop.ref.startswith(prefix):
            tokens = _tokens(drop.ref[len(prefix) :])
            removed.add(() if tokens is None else tokens)  # unreadable: the whole data
    return removed


@dataclass(frozen=True)
class CitationVerdict:
    """One citation's verdict, never its value: evidence id, pointer, value digest (``invalid``
    outside the digest profile) and whether they ``named`` a value of this run (Task 3.R1)."""

    evidence_id: str
    pointer: str
    value_digest: str
    status: CitationStatus
    named: bool = False

    def at_rest(self) -> dict[str, str]:
        return citation_at_rest(self.evidence_id, self.pointer, self.value_digest, named=self.named)


@dataclass(frozen=True)
class GroundingResult:
    """The verdicts of a proposal's citations, in citation order."""

    verdicts: tuple[CitationVerdict, ...]

    @property
    def grounded(self) -> bool:
        """Whether every citation resolved (vacuously, when there is none)."""
        return all(v.status is CitationStatus.RESOLVED for v in self.verdicts)

    def counts(self) -> dict[str, int]:
        statuses = [v.status for v in self.verdicts]
        return {
            "cited": len(statuses),
            **{status.value: statuses.count(status) for status in CitationStatus},
        }

    def at_rest(self) -> list[dict[str, str]]:
        return [v.at_rest() for v in self.verdicts]

    def findings(self, stored: bool = False) -> tuple[Finding, ...]:
        """One ``KERNEL-CITATION`` per citation that did not resolve, never a value (ADR 0032
        §5); ``stored``: as recorded, digests for one that named nothing (Task 3.R1)."""
        return tuple(
            finding_at_rest(
                Finding(
                    rule_id=KERNEL_CITATION,
                    rule_version="1",
                    status=ValidationStatus.FAIL,
                    message=CITATION_MESSAGES[v.status],
                    observed=v.pointer,
                    evidence_ids=(v.evidence_id,),
                ),
                digested=stored and not v.named,
            )
            for v in self.verdicts
            if v.status is not CitationStatus.RESOLVED
        )


def _verdict(
    by_id: Mapping[str, list[Observation]], citation: Citation, view: ClassView | None
) -> CitationVerdict:
    sources = by_id.get(citation.evidence_id, ())
    if view is None:
        found = [_value_at(o.data, citation.pointer) for o in sources]
    else:
        found = [view.value_at(o, citation.pointer) for o in sources]
    found = [value for value in found if value is not _MISSING]

    def verdict(status: CitationStatus, cited: str) -> CitationVerdict:
        return CitationVerdict(citation.evidence_id, citation.pointer, cited, status, bool(found))

    try:
        cited = value_digest(citation.value)
    except (KernelError, CanonicalizationError):
        return verdict(CitationStatus.MISMATCHED, INVALID_DIGEST)  # equals no stored value
    if view is not None and _holds_marker(citation.value):
        return verdict(CitationStatus.UNRESOLVED, cited)  # a marker is not evidence
    if not found:
        return verdict(CitationStatus.UNRESOLVED, cited)
    for value in found:
        try:
            if value_digest(value) == cited:
                return verdict(CitationStatus.RESOLVED, cited)
        except (KernelError, CanonicalizationError):
            continue  # a provider value outside the profile equals no cited value
    return verdict(CitationStatus.MISMATCHED, cited)


def check_citations(
    observations: Iterable[Observation],
    citations: Iterable[Citation],
    view: ClassView | None = None,
) -> GroundingResult:
    """Each citation's verdict against ``observations``: the caller passes this run's
    continuation observations, so evidence of another run never resolves (Review Focus 5).
    With a ``view`` (pinned ``context_assembler: on``) values are those the class walk
    shows the model; without one, the raw data the driver was given. Pure: no provider
    read, no model call. A walk that raises propagates: the check cannot run."""
    by_id: dict[str, list[Observation]] = {}
    for observation in observations:
        by_id.setdefault(observation.evidence.evidence_id, []).append(observation)
    return GroundingResult(tuple(_verdict(by_id, c, view) for c in citations))


@dataclass(frozen=True)
class GroundingProbe:
    """What the check found before the answer's action: the mode it acts in (``off`` when
    nothing is recorded or stored), its result, whether a shadow check failed, and the run
    when a fallback moved its revision (final check FA-2)."""

    mode: FeatureMode
    result: GroundingResult | None = None
    failed: bool = False
    run: RunRecord | None = None

    def stored(self) -> dict[str, Any]:
        """The ``proposal.created`` key: the at-rest citations, when any were checked."""
        if self.mode is FeatureMode.OFF or self.result is None or not self.result.verdicts:
            return {}
        return {"citations": self.result.at_rest()}

    def events(self, action_id: str | None) -> list[EventSpec]:
        """``shadow`` only: the answer's ``grounding.compared``, or ``grounding.shadow_failed``;
        written with its ``proposal.created``, or with a repeated answer's final (no action)."""
        if self.mode is not FeatureMode.SHADOW:
            return []
        if self.failed or self.result is None:
            payload: dict[str, Any] = {"stage": "check", "message": GROUNDING_SHADOW_MESSAGE}
            return [(RunEventType.GROUNDING_SHADOW_FAILED, payload, action_id)]
        verdicts = tuple(v.status.value for v in self.result.verdicts)
        cited = CitationCounts(**self.result.counts(), verdicts=verdicts)
        payload = GroundingCompared(citations=cited).model_dump(mode="json")
        return [(RunEventType.GROUNDING_COMPARED, payload, action_id)]


class GroundingMixin(RepeatMixin):
    async def _grounding_probe(
        self, run: RunRecord, cont: _Continuation, citations: tuple[Citation, ...]
    ) -> GroundingProbe | RunRecord | DriverInput:
        """Check a typed answer's citations before its action exists. A `GroundingProbe`
        continues today's path; in ``on`` a citation that does not resolve returns its
        ``KERNEL-CITATION`` repair, and a check that cannot run after a reservation returns
        the closed run."""
        modes = self._run_modes(cont)
        mode = modes.grounded_answers
        if mode is FeatureMode.OFF:
            return GroundingProbe(FeatureMode.OFF)  # dropped, never stored
        try:
            view = None
            if modes.context_assembler is FeatureMode.ON:  # what the pack showed (R1-1)
                view = ClassView(self._registry.data_classes, self._route)
            result = check_citations(cont.observations.values(), citations, view)
        except Exception:  # no exception text reaches an event (PR-25, PR-28)
            if mode is FeatureMode.SHADOW:
                return GroundingProbe(mode, failed=True)
            if await self._has_reserved(run):
                return await self._end_closed(run, ReasonCode.GROUNDING_UNAVAILABLE)
            fell = await self._fell_back(run, "grounded_answers", ReasonCode.GROUNDING_CHECK_FAILED)
            return GroundingProbe(FeatureMode.OFF, run=fell)  # verified as today, citations dropped
        if mode is FeatureMode.ON and not result.grounded:
            current = await self._store.get_run(run.tenant_id, run.run_id)
            return await repair_at_rest(self._repair_finding, current, cont, result)
        return GroundingProbe(mode, result)

    async def _handle_answer(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput:
        """Structured answers: no approval or dispatch; the domain verifier recomputes
        the answer from fresh, independent reads. Its citations are checked first, per the
        run's pinned ``grounded_answers`` mode (`_grounding_probe`)."""
        ctx = cont.ctx
        try:  # as a write proposal: a repair finding, never an exception (2c.8c)
            connection = self._connections.usable(ctx, proposal.connection_id)
        except KernelError:
            return await self._connection_refused(run, cont)
        verifier = self._registry.verifier_for(proposal.contract_id)
        if verifier is None:  # it can never be verified: fail, never claim it (review P-1)
            return await self._no_verifier(run)
        probe = await self._grounding_probe(run, cont, proposal.citations)
        if not isinstance(probe, GroundingProbe):  # `on`: KERNEL-CITATION, or closed
            return probe
        run = probe.run or run  # a fallback moved the revision
        try:
            action_digest = compute_digest(
                {"contract_id": proposal.contract_id, "arguments": dict(proposal.arguments)}
            )
        except CanonicalizationError:
            action_digest = INVALID_DIGEST
        if await self._repeats_verified_answer(
            cont, proposal, connection.connection_id, action_digest
        ):
            return await self._finish_verified(  # its shadow events too (3e.1 R1-2)
                cont, (), REPEATED_ANSWER, acknowledge=False, extra=probe.events(None)
            )
        action = ActionRecord(
            action_id=new_id("act"),
            tenant_id=ctx.tenant_id,
            run_id=run.run_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id="answer",
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            arguments=dict(proposal.arguments),
            digest=action_digest,
            state=ActionState.PROPOSED,
            revision=1,
            supersedes_action_id=cont.last_action_id,
        )
        await self._store.put_action(
            action,
            None,
            [
                (
                    RunEventType.PROPOSAL_CREATED,
                    {
                        "contract_id": action.contract_id,
                        "arguments": action.arguments,
                        "kind": "answer",
                        "supersedes": cont.last_action_id,
                        **proposal_keys(action),
                        **probe.stored(),  # ADR 0033 §1: shadow and on only
                    },
                    action.action_id,
                ),
                *probe.events(action.action_id),
            ],
        )
        cont.last_action_id = action.action_id
        action = await self._transition(action, ActionState.VALIDATED)
        reader = _GatewayReader(self, cont, connection.connection_id)
        try:
            report = await verifier.verify(ctx, action, None, reader)
        except Exception as exc:  # verification unavailable: never claim the answer
            report = OutcomeReport(
                run_id=ctx.run_id,
                action_id=action.action_id,
                status=OutcomeStatus.UNKNOWN,
                checks=(),
                verifier_id=verifier.verifier_id,
                verifier_version=type(exc).__name__,
                reported_at=self._clock(),
            )
        report = self._kept(report)
        verified = report.status is OutcomeStatus.VERIFIED
        target = ActionState.VERIFIED if verified else ActionState.VERIFICATION_FAILED
        await self._store.record_outcome(
            ctx.tenant_id,
            report,
            action.model_copy(update={"state": target, "revision": action.revision + 1}),
            action.revision,
            [(RunEventType.OUTCOME_REPORTED, outcome_payload(report, target), action.action_id)],
        )
        if verified:
            return DriverInput(
                task=run.task,
                observations=tuple(cont.observations.values()),
                action_result={"status": "VERIFIED"},
            )
        run = await self._store.get_run(run.tenant_id, run.run_id)
        if cont.repairs >= ctx.budgets.max_validation_repairs:
            return await self._set_run_state(
                run, RunState.FAILED, "answer not verified", code=ReasonCode.VERIFICATION_FAILED
            )
        cont.repairs += 1
        findings = tuple(
            Finding(
                rule_id=f"VERIFY-{c.name}",
                rule_version="1",
                status=ValidationStatus.FAIL,
                message=f"answer check {c.name} failed",
                expected=c.expected,
                observed=c.observed,
            )
            for c in report.checks
            if not c.passed
        ) or (
            Finding(
                rule_id="VERIFY",
                rule_version="1",
                status=ValidationStatus.UNKNOWN,
                message="answer could not be verified",
            ),
        )
        return DriverInput(
            task=run.task, observations=tuple(cont.observations.values()), findings=findings
        )
