"""Evidence bundle export (MVP design §11).

A redacted, self-describing JSON record of one run: environment class, versions, events,
proposals/findings, approvals, receipts and outcomes. It contains no secrets (the ledger
never stores them), no driver continuation and no model reasoning; operators export it
through an authorized command.

A run that executed an action plan (execution IR ``on``, ADR 0025) also carries the additive
``plan`` key, the plan its latest linked action belongs to with each step's status, and a
run with step records carries ``steps``. Neither key appears without that data, so an
``off`` bundle is unchanged (ENG-TOGGLE-1). The read-back values a plan's lineage copies
from stay out of the bundle (PR-26). An exporter that passes its admission report's
defaulted effect declarations gets the additive ``defaulted_declarations`` key (ADR 0029
Operations). A run that pinned a Phase 3 mode carries the additive ``modes`` key, the pin
read from its kernel continuation (ADR 0032 §8, §13); an all-``off`` run pins nothing, so
its bundle has no such key. A run pinned ``context_assembler: on`` also carries ``context``:
per driver turn, its ``context.assembled`` record (turn, fallback, pack digest, drop log of
kinds, kernel refs and reasons; ADR 0032 §13). Nothing else of the continuation is exported.
Every bundle carries the additive ``explanation`` key, the projection of its events and
steps (ADR 0033 §6): ids, versions, digests and statuses, no observation values or model
text. A run that ended ``GROUNDED`` (``grounded.answer.v1``, ADR 0033 §3) carries the additive
``grounded_answer`` key: its summary, the model's free text outside the citations, labelled
``unverified``, and each at-rest citation labelled ``grounded``; no other bundle has it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.common import utc_now
from e_agent.contracts.events import RunEvent, RunEventType
from e_agent.contracts.explain import Explanation
from e_agent.contracts.features import FeatureMode, Features, RunModes
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunRecord
from e_agent.contracts.task import GROUNDED_ANSWER
from e_agent.sdk.store import RunStore

from .explain import explain
from .progress import project_progress
from .reconstruct import reconstruct
from .registry import DefaultedDeclaration

EVIDENCE_SCHEMA = "e-agent-evidence-v1"
EVIDENCE_PAGE = 1000  # events read per store call while exporting (ADR 0018)


# A kernel guard refused the action before it had any effect. For a multi-step plan the
# refusal is the refused step's: earlier steps may have committed and been verified, and the
# `plan` section lists them (ADR 0025). VERIFICATION_FAILED is deliberately absent: it
# follows a COMMITTED receipt (a write happened and the read-back disagreed), so it is `failed`.
BLOCKED_BY_DESIGN = frozenset(
    {
        ReasonCode.VALIDATION_FAILED,
        ReasonCode.POLICY_DENIED,
        ReasonCode.STALE,
        ReasonCode.SURFACE_CHANGED,
        ReasonCode.APPROVAL_REJECTED,
        ReasonCode.OPERATION_RESERVED,
        ReasonCode.PLAN_LINEAGE_REJECTED,
        ReasonCode.ROUTE_BOUNDARY_UNMET,  # no model call was made (ADR 0032 §11)
    }
)
# The Phase 3 `*_UNAVAILABLE` codes are infrastructure (ADR 0032 §11); DRIVER_STATE_MISMATCH
# is `failed`, and the Phase 3 fallback codes never end a run.
INFRASTRUCTURE_OR_BUDGET = frozenset(
    {
        ReasonCode.BUDGET_EXHAUSTED,
        ReasonCode.INTERRUPTED,
        ReasonCode.PROVIDER_ERROR,
        ReasonCode.CONNECTION_BUSY,
        ReasonCode.CONTEXT_UNAVAILABLE,
        ReasonCode.REPEAT_UNAVAILABLE,
        ReasonCode.GROUNDING_UNAVAILABLE,
    }
)

STEP_STATUS = {
    ActionState.VERIFIED: "verified",
    ActionState.COMMITTED: "committed",
    ActionState.DISPATCHING: "unknown",  # the provider may have executed it
    ActionState.UNKNOWN: "unknown",
    ActionState.FAILED: "failed",
    ActionState.VERIFICATION_FAILED: "failed",
}
"""A plan step's status by its action's state (target §6.4.6). A step with no action, or
whose action never reached dispatch (proposed, validated, blocked, awaiting approval,
approved or reserved), is ``unstarted``: no provider call was made for it."""


def defaulted_payload(declarations: Sequence[DefaultedDeclaration]) -> list[dict[str, Any]]:
    """The effect declarations admission accepted on their defaults (ADR 0029 Operations),
    as `/health/ready` and the evidence bundle list them: names only, never a setting."""
    return [
        {
            "plugin_id": d.plugin_id,
            "subject": d.subject,
            "subject_id": d.subject_id,
            "fields": list(d.fields),
        }
        for d in declarations
    ]


def classify(
    run_state: str,
    reason: str | None,
    environment: str,
    reason_code: ReasonCode | None = None,
) -> str:
    if run_state == "SUCCEEDED":
        return f"{environment}:succeeded"
    if run_state not in {str(s) for s in TERMINAL_RUN_STATES}:
        return f"{environment}:unresolved"
    if reason_code is not None:
        if reason_code in BLOCKED_BY_DESIGN:
            return f"{environment}:blocked-by-design"
        if reason_code in INFRASTRUCTURE_OR_BUDGET:
            return f"{environment}:infrastructure-or-budget"
        return f"{environment}:failed"
    # Rows written before ADR 0018 carry no code: keep the historical text rules.
    text = (reason or "").lower()
    if "validation" in text or "rejected" in text or "policy" in text:
        return f"{environment}:blocked-by-design"
    if "budget" in text or "interrupted" in text or "provider" in text:
        return f"{environment}:infrastructure-or-budget"
    return f"{environment}:failed"


async def _all_events(store: RunStore, tenant_id: str, run_id: str) -> list[RunEvent]:
    """The whole ledger, read page by page so one export never issues an unbounded read."""
    events: list[RunEvent] = []
    cursor = 0
    while True:
        page = await store.list_events(tenant_id, run_id, cursor, limit=EVIDENCE_PAGE)
        events.extend(page)
        if len(page) < EVIDENCE_PAGE:
            return events
        cursor = page[-1].sequence


async def _plan_section(
    store: RunStore, tenant_id: str, events: list[RunEvent], actions: list[ActionRecord]
) -> dict[str, Any] | None:
    """The plan the run's latest plan-linked action belongs to, each step with its action
    and status; None when no action is linked to a plan (``off``, ``shadow``)."""
    by_id = {a.action_id: a for a in actions}
    order = [
        by_id[e.action_id]
        for e in events
        if e.type is RunEventType.PROPOSAL_CREATED and e.action_id in by_id
    ]
    linked = [a for a in order if a.plan_id is not None]
    if not linked:
        return None
    plan = await store.get_plan(tenant_id, str(linked[-1].plan_id))
    step_actions = {a.step_index: a for a in linked if a.plan_id == plan.plan_id}
    steps = []
    for index, step in enumerate(plan.steps):
        action = step_actions.get(index)
        steps.append(
            {
                "step_id": step.step_id,
                "step_index": index,
                "contract_id": step.proposal.contract_id,
                "depends_on": list(step.depends_on),
                "action_id": action.action_id if action else None,
                "action_state": str(action.state) if action else None,
                "status": STEP_STATUS.get(action.state, "unstarted") if action else "unstarted",
            }
        )
    return {
        "plan_id": plan.plan_id,
        "task_id": plan.task_id,
        "task_version": plan.task_version,
        "step_count": len(plan.steps),
        "steps": steps,
    }


async def _pinned_modes(store: RunStore, tenant_id: str, run_id: str) -> RunModes | None:
    """The run's pinned Phase 3 modes from its kernel continuation, None when it pinned none."""
    stored = await store.load_continuation(tenant_id, run_id)
    if stored is None:
        return None
    pin = stored[0].get("data", {}).get("modes")
    return None if pin is None else RunModes.model_validate(pin)


CONTEXT_KEYS = ("turn", "acknowledgement", "fallback", "pack_digest", "drop_log")


def _context_section(events: Sequence[RunEvent]) -> list[dict[str, Any]]:
    """Each ``context.assembled`` of the run: the pack digest and drop log per turn."""
    return [
        {key: e.payload[key] for key in CONTEXT_KEYS if key in e.payload}
        for e in events
        if e.type is RunEventType.CONTEXT_ASSEMBLED
    ]


def _grounded_section(run: RunRecord, events: Sequence[RunEvent]) -> dict[str, Any] | None:
    """The kernel's ``message.final`` of a ``GROUNDED`` end with its labels: the summary is
    model-authored and ``unverified``, each citation ``grounded`` in this run's evidence,
    never ``verified`` (PR-19). None unless the run ended ``GROUNDED`` and wrote that
    record (review R1-3)."""
    if run.reason_code is not ReasonCode.GROUNDED:
        return None
    for e in events:
        if e.type is RunEventType.MESSAGE_FINAL and e.payload.get("contract_id") == GROUNDED_ANSWER:
            return {
                "contract_id": GROUNDED_ANSWER,
                "summary": {"text": e.payload["text"], "label": "unverified"},
                "citations": [{**c, "label": "grounded"} for c in e.payload["citations"]],
            }
    return None


async def build_evidence(
    store: RunStore,
    tenant_id: str,
    run_id: str,
    *,
    environment: str,
    versions: Mapping[str, Any],
    features: Features,
    defaulted_declarations: Sequence[DefaultedDeclaration] | None = None,
    route: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """``defaulted_declarations`` is the exporting runtime's admission report: when given,
    the bundle lists it, an empty list included (ADR 0029 Operations); when omitted, the
    bundle has no such key, as before Task 2c.8a. ``route`` is the model route's data
    boundary facts (``data_boundary``, ``data_boundary_basis``, ``data_processing_declared``;
    ADR 0030) as plain values; when omitted the bundle has no ``route`` key."""
    run = await store.get_run(tenant_id, run_id)
    events = await _all_events(store, tenant_id, run_id)
    actions = await store.list_actions(tenant_id, run_id)
    approvals, receipts = [], []
    for action in actions:
        approvals += [
            a.model_dump(mode="json")
            for a in await store.list_approvals(tenant_id, action.action_id)
        ]
        receipts += [
            r.model_dump(mode="json")
            for r in await store.list_receipts(tenant_id, action.action_id)
        ]
    rule_bundles = sorted(
        {
            str(f.get("rule_id")) + "@" + str(f.get("rule_version"))
            for e in events
            if e.type == "validation.completed"
            for f in e.payload.get("findings", [])
        }
    )
    bundle: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "generated_at": utc_now().isoformat(),
        "environment": environment,
        "classification": classify(run.state, run.reason, environment, run.reason_code),
        "versions": dict(versions),
        "features": features.model_dump(mode="json"),
        "rules_evaluated": rule_bundles,
        "run": run.model_dump(mode="json"),
        "actions": [a.model_dump(mode="json") for a in actions],
        "approvals": approvals,
        "receipts": receipts,
        "outcomes": [e.payload for e in events if e.type == "outcome.reported"],
        "events": [e.model_dump(mode="json") for e in events],
    }
    if defaulted_declarations is not None:
        bundle["defaulted_declarations"] = defaulted_payload(defaulted_declarations)
    if route is not None:
        bundle["route"] = dict(route)
    modes = await _pinned_modes(store, tenant_id, run_id)
    if modes is not None:
        bundle["modes"] = modes.model_dump(mode="json")
        if modes.context_assembler is FeatureMode.ON:
            bundle["context"] = _context_section(events)
    grounded = _grounded_section(run, events)
    if grounded is not None:
        bundle["grounded_answer"] = grounded
    plan = await _plan_section(store, tenant_id, events, actions)
    if plan is not None:
        bundle["plan"] = plan
    steps = await store.list_steps(tenant_id, run_id)
    if steps:
        bundle["steps"] = [s.model_dump(mode="json") for s in steps]
    bundle["explanation"] = explain(
        project_progress(events, steps), reconstruct(events)
    ).model_dump(mode="json")
    return bundle


async def run_explanation(store: RunStore, tenant_id: str, run_id: str) -> Explanation:
    """The explanation of one run in the tenant (ADR 0033 §6): its events read page by page
    and its steps, projected without a model call. A run outside the tenant is not found."""
    await store.get_run(tenant_id, run_id)
    events = await _all_events(store, tenant_id, run_id)
    steps = await store.list_steps(tenant_id, run_id)
    return explain(project_progress(events, steps), reconstruct(events))
