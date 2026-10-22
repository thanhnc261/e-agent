"""Feature toggles in the kernel (ADR 0027, target architecture §6.4.8).

Fallback: a feature in ``on`` mode may return to the existing path only before the first
write reservation. The consumer decides when that applies; `record_fallback` records the
``feature.fallback`` event with a typed reason and leaves the run state unchanged,
because a fallback code never ends a run (ADR 0025).

Shadow (``execution_ir: shadow``, Task 2c.5, XA-24): after today's validation passes a write
proposal, `_shadow_plan` compiles it into a 1-step plan, validates it, computes its digest
and records the comparison with the action digest. It acts on nothing: no driver call, no
provider read, no budget use, and the run, the action and the approval are today's.

Phase 3 (ADR 0032 §8, §11): a run pins ``context_assembler``, ``kernel_repeat`` and
``grounded_answers``, and since Phase 4 ``conversations`` (ADR 0023 §9), in its continuation
when it is prepared (`RunModes`, written only when a mode is not ``off``), and every later
toggle site reads the pin through `_run_modes`, never the profile. The three Phase 3 fallback
codes, five terminal codes and the ``conversations`` fallback code each have one fixed
message here.

No event here carries caller text: each message is a fixed one, so no provider, compiler,
validator or model string reaches the ledger or the evidence export (PR-25, PR-28).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.common import new_id
from e_agent.contracts.context_pack import ContextRoute
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features, RunModes
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunRecord, RunState
from e_agent.contracts.step import StepKind, StepStatus
from e_agent.contracts.task import TaskDefinition
from e_agent.sdk.store import EventSpec

from .approval import compute_digest
from .context import context_route
from .continuation import ContinuationMixin, _Continuation
from .errors import ErrorCode, KernelError
from .ir import (
    SINGLE_STEP_ID,
    PlanValidationContext,
    StepDigestContext,
    compile_proposal,
    plan_digest_input,
    validate_plan,
)
from .step import finish_step, start_step

FALLBACK_MESSAGES = MappingProxyType(
    {
        ReasonCode.IR_TASK_UNRESOLVED: "The run names no task definition.",
        ReasonCode.IR_COMPILE_FAILED: "The proposal could not be compiled into a plan.",
        ReasonCode.IR_VALIDATION_FAILED: "The compiled plan did not pass validation.",
        ReasonCode.CONTEXT_ASSEMBLY_FAILED: "The context pack could not be assembled; "
        "the turn used the run history.",
        ReasonCode.REPEAT_CHECK_FAILED: "The repeated-call check could not run; "
        "the call continued on the existing path.",
        ReasonCode.GROUNDING_CHECK_FAILED: "The grounding check could not run; "
        "the answer continued on the existing path.",
        ReasonCode.CONVERSATION_CONTEXT_FAILED: "The carried conversation context could not "
        "be built; the run started without it.",
    }
)
"""The fallback codes and each one's fixed message: ADR 0025 names the ``execution_ir`` ones,
ADR 0031, 0032 and 0033 the Phase 3 ones, ADR 0023 the ``conversations`` one."""

FALLBACK_FEATURES = MappingProxyType(
    {
        ReasonCode.IR_TASK_UNRESOLVED: "execution_ir",
        ReasonCode.IR_COMPILE_FAILED: "execution_ir",
        ReasonCode.IR_VALIDATION_FAILED: "execution_ir",
        ReasonCode.CONTEXT_ASSEMBLY_FAILED: "context_assembler",
        ReasonCode.REPEAT_CHECK_FAILED: "kernel_repeat",
        ReasonCode.GROUNDING_CHECK_FAILED: "grounded_answers",
        ReasonCode.CONVERSATION_CONTEXT_FAILED: "conversations",
    }
)
"""The feature each fallback code belongs to; `fallback_event` refuses any other pair."""

TERMINAL_MESSAGES = MappingProxyType(
    {
        ReasonCode.CONTEXT_UNAVAILABLE: "The context pack could not be assembled, "
        "and the run cannot fall back.",
        ReasonCode.REPEAT_UNAVAILABLE: "The repeated-call check is unavailable, "
        "and the run cannot fall back.",
        ReasonCode.GROUNDING_UNAVAILABLE: "The grounding check is unavailable, "
        "and the run cannot fall back.",
        ReasonCode.DRIVER_STATE_MISMATCH: "The driver state does not match the run's pinned modes.",
        ReasonCode.ROUTE_BOUNDARY_UNMET: "The model route is not local and has no data "
        "processing declaration, so no model call was made.",
    }
)
"""The Phase 3 terminal codes (ADR 0032 §11) and each one's fixed message: the reason of the
run state change it ends, and of ``context.failed``. No message names a route or setting
value."""

CONTEXT_FAILED_CODES = frozenset(
    {
        ReasonCode.CONTEXT_UNAVAILABLE,
        ReasonCode.ROUTE_BOUNDARY_UNMET,
        ReasonCode.DRIVER_STATE_MISMATCH,
    }
)
"""The codes ``context.failed`` carries for a skipped acknowledgement turn (ADR 0032 §8,
§11)."""

SHADOW_MESSAGES = MappingProxyType(
    {
        "compile": FALLBACK_MESSAGES[ReasonCode.IR_COMPILE_FAILED],
        "validate": FALLBACK_MESSAGES[ReasonCode.IR_VALIDATION_FAILED],
    }
)
"""Each shadow stage's fixed ``ir.shadow_failed`` message; the event carries no reason code."""

CONTEXT_SHADOW_MESSAGES = MappingProxyType(
    {
        "inputs": "The context pack inputs could not be derived from the run's records.",
        "assemble": "The context pack could not be assembled.",
        "compare": "The context pack could not be compared with its unbounded inputs.",
    }
)
"""Each ``context_assembler: shadow`` stage's fixed ``context.shadow_failed`` message (ADR 0032
§7); like ``ir.shadow_failed`` the event carries no reason code and no exception text."""


LOCAL_ROUTE = MappingProxyType(
    {"data_boundary": "local", "data_boundary_basis": "verified", "data_processing_declared": False}
)
"""The route facts of a coordinator built without any (ADR 0030: the scripted driver's)."""

UNRESOLVED_RESERVATION = frozenset(
    {ActionState.RESERVED, ActionState.DISPATCHING, ActionState.UNKNOWN, ActionState.COMMITTED}
)
"""Action states of a write reservation not yet resolved by a decisive outcome (ADR 0032 §8)."""


ROUTE_STRICTNESS = MappingProxyType(
    {ContextRoute.LOCAL: 0, ContextRoute.HOSTED_DECLARED: 1, ContextRoute.HOSTED_UNDECLARED: 2}
)
"""How much each class-rule row masks (ADR 0032 §5): a higher row masks more."""


class RouteRefused(Exception):
    """`_with_tools` refused a model call on the current route (ADR 0032 §9); never escapes
    the kernel's two driver call sites."""


def unmasked_allowed(route: Mapping[str, Any]) -> bool:
    """Whether unmasked run data may reach the route: it is ``local``, or the profile declares
    ``data_processing`` for it (ADR 0030). Missing facts allow nothing."""
    return route.get("data_boundary") == "local" or route.get("data_processing_declared") is True


def fallback_event(feature: str, reason: ReasonCode) -> EventSpec:
    """The ``feature.fallback`` event: a typed reason and its fixed message, no caller text."""
    if feature not in Features.model_fields:
        raise KernelError(ErrorCode.INVALID_REQUEST, f"unknown feature {feature!r}")
    message = FALLBACK_MESSAGES.get(reason)
    if message is None:
        raise KernelError(ErrorCode.INVALID_REQUEST, f"{reason} is not a fallback code")
    if FALLBACK_FEATURES[reason] != feature:
        raise KernelError(ErrorCode.INVALID_REQUEST, f"{reason} is not a {feature} fallback code")
    payload = {"feature": feature, "reason_code": reason, "message": message}
    return (RunEventType.FEATURE_FALLBACK, payload, None)


def context_failed_event(reason: ReasonCode) -> EventSpec:
    """``context.failed`` for a skipped acknowledgement turn: the code, its fixed message and
    the turn, no caller text (ADR 0032 §11)."""
    if reason not in CONTEXT_FAILED_CODES:
        raise KernelError(ErrorCode.INVALID_REQUEST, f"{reason} is not a context.failed code")
    payload = {
        "reason_code": reason,
        "message": TERMINAL_MESSAGES[reason],
        "turn": "acknowledgement",
    }
    return (RunEventType.CONTEXT_FAILED, payload, None)


def context_shadow_failed_event(stage: str, turn: int, *, acknowledgement: bool) -> EventSpec:
    """``context.shadow_failed``: the stage, its fixed message and the driver turn, nothing
    else (ADR 0032 §7, PR-26). The run is otherwise unchanged."""
    payload = {
        "stage": stage,
        "message": CONTEXT_SHADOW_MESSAGES[stage],
        "turn": turn,
        "acknowledgement": acknowledgement,
    }
    return (RunEventType.CONTEXT_SHADOW_FAILED, payload, None)


def _task_unresolved(action_id: str | None) -> EventSpec:
    reason = ReasonCode.IR_TASK_UNRESOLVED
    payload = {"reason_code": reason, "message": FALLBACK_MESSAGES[reason]}
    return (RunEventType.IR_SHADOW_FAILED, payload, action_id)


def _shadow_failed(stage: str, action_id: str) -> EventSpec:
    return (
        RunEventType.IR_SHADOW_FAILED,
        {"stage": stage, "message": SHADOW_MESSAGES[stage]},
        action_id,
    )


class FeaturesMixin(ContinuationMixin):
    _features: Features
    _route: Mapping[str, Any]
    """The model route's boundary facts as plain values (ADR 0030), from bootstrap."""

    @property
    def _ir_shadow(self) -> bool:
        return self._features.execution_ir is FeatureMode.SHADOW

    def _pin_modes(self) -> RunModes | None:
        """The pin a run prepared now stores: None when every pinned mode is ``off``, so an
        ``off`` continuation is byte-identical (ADR 0032 §8, ADR 0023 §9)."""
        modes = RunModes.from_features(self._features)
        return None if modes.all_off else modes

    def _check_route(self, cont: _Continuation) -> None:
        """The per-call route check (ADR 0032 §9, T23), run by `_with_tools` before every
        model call: the route is not pinned, so a run that resumes after a restart on a route
        that may not receive unmasked data makes no model call unless it is pinned
        ``context_assembler: on``.

        A run pinned ``on`` keeps the loosest boundary a call of it has used
        (``context_boundary``, set by its first call): its driver history holds the model's
        own text and arguments and any fallback turn's unmasked returns, masked only for that
        route, so a call on a stricter route is refused (review D3-41). Off and shadow runs
        record nothing."""
        if self._run_modes(cont).context_assembler is not FeatureMode.ON:
            if not unmasked_allowed(self._route):
                raise RouteRefused
            return
        route = context_route(self._route)
        seen = cont.context_boundary
        if seen is not None and ROUTE_STRICTNESS[route] > ROUTE_STRICTNESS[seen]:
            raise RouteRefused
        if seen is None or ROUTE_STRICTNESS[route] < ROUTE_STRICTNESS[seen]:
            cont.context_boundary = route

    async def _end_closed(self, run: RunRecord, code: ReasonCode) -> RunRecord:
        """End a run with a Phase 3 terminal code (ADR 0032 §10): FAILED, or
        NEEDS_RECONCILIATION when a write reservation is unresolved, through an existing pair
        of the table, with the code's fixed message."""
        run = await self._store.get_run(run.tenant_id, run.run_id)
        actions = await self._store.list_actions(run.tenant_id, run.run_id)
        unresolved = any(a.state in UNRESOLVED_RESERVATION for a in actions)
        return await self._set_run_state(
            run,
            RunState.NEEDS_RECONCILIATION if unresolved else RunState.FAILED,
            TERMINAL_MESSAGES[code],
            code=code,
        )

    @staticmethod
    def _run_modes(cont: _Continuation) -> RunModes:
        """The run's pinned modes; an absent pin means every mode is ``off``. Every toggle
        site of the three Phase 3 features and of ``conversations`` reads this, never the
        profile."""
        return cont.modes if cont.modes is not None else RunModes()

    def _admit_task(
        self, run: RunRecord, task_kind: str | None
    ) -> tuple[RunRecord, list[EventSpec]]:
        """At run creation, in shadow or on: link the run to the definition its task kind
        names (D8, ADR 0028), or return the run's one unresolved record for the creating
        write's batch, when there is no kind (an API or UI run) or the kind names no admitted
        definition: ``ir.shadow_failed`` in shadow, ``feature.fallback`` in on (the run then
        runs as ``off``), both with `IR_TASK_UNRESOLVED`. In ``off`` the run and its batch are
        today's."""
        mode = self._features.execution_ir
        if mode is FeatureMode.OFF:
            return run, []
        task = self._registry.task_definitions.get(task_kind) if task_kind else None
        if task is None:
            if mode is FeatureMode.ON:
                return run, [fallback_event("execution_ir", ReasonCode.IR_TASK_UNRESOLVED)]
            return run, [_task_unresolved(None)]
        linked = run.model_copy(update={"task_id": task.task_id, "task_version": task.version})
        return linked, []

    def _run_task(self, run: RunRecord) -> TaskDefinition | None:
        task = self._registry.task_definitions.get(run.task_id) if run.task_id else None
        return task if task is not None and task.version == run.task_version else None

    async def _shadow_plan(
        self,
        run: RunRecord,
        cont: _Continuation,
        proposal: ActionProposal,
        action: ActionRecord,
        digest_ctx: StepDigestContext,
    ) -> list[EventSpec]:
        """Compile, validate and digest ``proposal`` as a 1-step plan, after today's validation
        passed it (target §6.4.8). On success the plan, ``ir.plan_compiled`` and the validate
        step's rows are written in one `put_plan` and nothing is returned. On failure nothing
        is written: the returned ``ir.shadow_failed`` goes into the caller's next write, so the
        run revision is today's. A run that resolved no definition at creation recorded that
        there, once, and its proposals skip this step.

        Only the pure IR calls are guarded; a store error propagates. Exception text and
        findings never reach a payload."""
        if run.task_id is None:
            return []  # unresolved at creation, recorded there once (`_admit_task`)
        task = self._run_task(run)
        if task is None:  # the linked definition is no longer admitted (a resumed run)
            return [_task_unresolved(action.action_id)]
        try:
            plan = compile_proposal(proposal, task, plan_id=new_id("plan"))
        except Exception:  # a shadow error never reaches the live path
            return [_shadow_failed("compile", action.action_id)]
        effects = {
            cid: self._registry.capabilities[cid].effect
            for cid in task.capabilities
            if cid in self._registry.capabilities
        }
        limits = PlanValidationContext(
            effects=effects, max_admitted_writes=cont.ctx.budgets.max_admitted_writes
        )
        try:
            if validate_plan(plan, task, limits):
                return [_shadow_failed("validate", action.action_id)]
            canonical = plan_digest_input(
                plan, {SINGLE_STEP_ID: digest_ctx}, run_operation_id=run.logical_operation_id
            )
            digest = compute_digest(canonical)
        except Exception:  # the digest profile is the validate stage's
            return [_shadow_failed("validate", action.action_id)]
        # Next sequence after the run's steps; the store's locked check refuses any race.
        steps = await self._store.list_steps(run.tenant_id, run.run_id)
        sequence = steps[-1].sequence + 1 if steps else 0
        now = self._clock()
        started = start_step(
            tenant_id=run.tenant_id,
            run_id=run.run_id,
            step_id=f"{plan.plan_id}/{SINGLE_STEP_ID}/validate",
            sequence=sequence,
            kind=StepKind.VALIDATE,
            now=now,
            action_id=action.action_id,
            input_refs=digest_ctx.evidence,
        )
        finished = finish_step(started, sequence=sequence + 1, status=StepStatus.SUCCEEDED, now=now)
        compiled = {
            "plan_id": plan.plan_id,
            "plan_digest": digest,
            "step_count": len(plan.steps),
            "task_id": task.task_id,
            "task_version": task.version,
            "digest_matches": digest == action.digest,
        }
        await self._store.put_plan(
            run.tenant_id,
            run.run_id,
            plan,
            [(RunEventType.IR_PLAN_COMPILED, compiled, action.action_id), started, finished],
        )
        return []

    async def record_fallback(self, run: RunRecord, feature: str, reason: ReasonCode) -> RunRecord:
        """Append ``feature.fallback`` in one transaction and return the updated run.

        The run's state, reason and reason code are unchanged; only its revision moves, so
        the caller keeps using the returned record.
        """
        event = fallback_event(feature, reason)
        if run.state in TERMINAL_RUN_STATES:
            raise KernelError(ErrorCode.CONFLICT, "a finished run cannot fall back")
        return await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}), run.revision, [event]
        )
