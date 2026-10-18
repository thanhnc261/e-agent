"""Feature toggles in the kernel (ADR 0027, target architecture §6.4.8).

Fallback: a feature in ``on`` mode may return to the existing path only before the first
write reservation. The consumer decides when that applies; `record_fallback` records the
``feature.fallback`` event with a typed reason and leaves the run state unchanged,
because a fallback code never ends a run (ADR 0025).

Shadow (``execution_ir: shadow``, Task 2c.5, XA-24): after today's validation passes a write
proposal, `_shadow_plan` compiles it into a 1-step plan, validates it, computes its digest
and records the comparison with the action digest. It acts on nothing: no driver call, no
provider read, no budget use, and the run, the action and the approval are today's.

No event here carries caller text: each message is a fixed one, so no provider, compiler,
validator or model string reaches the ledger or the evidence export (PR-25, PR-28).
"""

from __future__ import annotations

from types import MappingProxyType

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.common import new_id
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import TERMINAL_RUN_STATES, ReasonCode, RunRecord
from e_agent.contracts.step import StepKind, StepStatus
from e_agent.contracts.task import TaskDefinition
from e_agent.sdk.store import EventSpec

from .approval import compute_digest
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
    }
)
"""The fallback codes (ADR 0025 names them for ``execution_ir``) and each one's fixed message."""

SHADOW_MESSAGES = MappingProxyType(
    {
        "compile": FALLBACK_MESSAGES[ReasonCode.IR_COMPILE_FAILED],
        "validate": FALLBACK_MESSAGES[ReasonCode.IR_VALIDATION_FAILED],
    }
)
"""Each shadow stage's fixed ``ir.shadow_failed`` message; the event carries no reason code."""

ON_UNAVAILABLE = "execution_ir: on is not available yet; use off or shadow"


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


def check_features(features: Features) -> Features:
    """Refuse a mode that is not built yet: a selectable mode must be complete (ADR 0027).
    Task 2c.6 removes the ``on`` refusal."""
    if features.execution_ir is FeatureMode.ON:
        raise KernelError(ErrorCode.STARTUP_REJECTED, ON_UNAVAILABLE)
    return features


class FeaturesMixin(ContinuationMixin):
    _features: Features

    @property
    def _ir_shadow(self) -> bool:
        return self._features.execution_ir is FeatureMode.SHADOW

    def _admit_task(
        self, run: RunRecord, task_kind: str | None
    ) -> tuple[RunRecord, list[EventSpec]]:
        """At run creation, in shadow: link the run to the definition its task kind names
        (D8, ADR 0028), or return the run's one ``ir.shadow_failed`` (`IR_TASK_UNRESOLVED`)
        for the creating write's batch, when there is no kind (an API or UI run) or the kind
        names no admitted definition. In ``off`` the run and its batch are today's."""
        if not self._ir_shadow:
            return run, []
        task = self._registry.task_definitions.get(task_kind) if task_kind else None
        if task is None:
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
        if feature not in Features.model_fields:
            raise KernelError(ErrorCode.INVALID_REQUEST, f"unknown feature {feature!r}")
        message = FALLBACK_MESSAGES.get(reason)
        if message is None:
            raise KernelError(ErrorCode.INVALID_REQUEST, f"{reason} is not a fallback code")
        if run.state in TERMINAL_RUN_STATES:
            raise KernelError(ErrorCode.CONFLICT, "a finished run cannot fall back")
        return await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.FEATURE_FALLBACK,
                    {"feature": feature, "reason_code": reason, "message": message},
                    None,
                )
            ],
        )
