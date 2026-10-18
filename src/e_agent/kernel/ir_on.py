"""Execution IR ``on``, single-step plans (Task 2c.6, ADR 0025, ADR 0028, target §6.4).

A run in ``on`` that resolved its task definition at admission executes the IR:

- its tool set is the definition's capabilities, passed to the driver on every turn
  (`_with_tools`, owner decision D6); the kernel refuses a driver read outside it
  (`GatewayMixin._driver_read`) and turns a proposal outside it into a repair finding
  (`_outside_task_set`);
- its budgets are the profile's with the definition's set fields merged over them, and its
  approval TTL is the definition's when it has one (D7);
- a write proposal that today's validation passes compiles to a 1-step plan, which is
  validated, digested and stored (`_on_plan`). The plan's digest is the action digest, so the
  approval and its presentation are today's; the action is linked to the plan (``plan_id``,
  ``step_index`` 0) in the approval write;
- each stage of a linked action writes step records in the batch of its own events
  (`_step_start`, `_step_finish`, `_step_pair`);
- at run end the acceptance spec is checked (`_acceptance_unmet`, through `_succeed` or
  `_fail_unmet` on the live finish paths and on recovery); unmet ends ``ACCEPTANCE_UNMET``.

Fallback (ENG-TOGGLE-2): before the first reservation, an unresolved definition, a compile
failure or a validation failure records ``feature.fallback`` with a fixed message and the
proposal continues on today's path, unlinked; after the reservation nothing falls back. A run
that resolves no definition at admission falls back there, once, and then runs as ``off``.
Only the pure IR calls are guarded; a store error propagates.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.common import new_id
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunRecord, RunState
from e_agent.contracts.step import StepKind, StepRecord, StepStatus
from e_agent.contracts.task import TaskDefinition, acceptance_met
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.sdk.ports import DriverInput
from e_agent.sdk.store import EventBatch
from pydantic import ValidationError

from .approval import compute_digest
from .continuation import _Continuation
from .errors import ErrorCode, KernelError
from .features import FeaturesMixin
from .ir import (
    SINGLE_STEP_ID,
    PlanValidationContext,
    StepDigestContext,
    compile_proposal,
    plan_digest_input,
    validate_plan,
)
from .step import finish_step, start_step

FEATURE = "execution_ir"
OUTSIDE_SET = "The proposed capability is not in the run's task definition."
"""The fixed message of the ``KERNEL-PLAN-CAPABILITY`` repair finding (no model text)."""


def merged_budgets(profile: Budgets, task: TaskDefinition) -> Budgets:
    """The profile's budgets with only the fields the definition sets merged over them
    (2c.2 review R-2); admission already refused a definition that widens one (D7)."""
    if task.budgets is None:
        return profile
    return profile.model_copy(
        update={name: getattr(task.budgets, name) for name in task.budgets.model_fields_set}
    )


class IrOnMixin(FeaturesMixin):
    @property
    def _ir_on(self) -> bool:
        return self._features.execution_ir is FeatureMode.ON

    def _on_task(self, run: RunRecord) -> TaskDefinition | None:
        """The definition the run executes in ``on``; None in ``off`` and ``shadow`` (shadow
        narrows nothing) and for a run that resolved none."""
        return self._run_task(run) if self._ir_on else None

    def _allowed(self, run: RunRecord) -> tuple[str, ...] | None:
        task = self._on_task(run)
        return None if task is None else task.capabilities

    def _with_tools(self, run: RunRecord, step_input: DriverInput) -> DriverInput:
        """The driver input for one turn, carrying the run's tool set in ``on`` (D6)."""
        allowed = self._allowed(run)
        if allowed is None:
            return step_input
        return dataclasses.replace(step_input, allowed_capabilities=allowed)

    def _ttl_for(self, run: RunRecord) -> timedelta:
        task = self._on_task(run)
        if task is None or task.approval_ttl is None:
            return self._approval_ttl
        return task.approval_ttl

    # -- proposals -------------------------------------------------------------------------
    async def _outside_task_set(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput | None:
        """A proposal outside the run's tool set is a repair finding, never a fallback: the
        fallback path would widen the set. None when the proposal is inside it."""
        allowed = self._allowed(run)
        if allowed is None or proposal.contract_id in allowed:
            return None
        finding = Finding(
            rule_id="KERNEL-PLAN-CAPABILITY",
            rule_version="1",
            status=ValidationStatus.FAIL,
            message=OUTSIDE_SET,
        )
        payload = {"status": "FAIL", "findings": [finding.model_dump(mode="json")]}
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.VALIDATION_COMPLETED, payload, None)],
        )
        if cont.repairs >= cont.ctx.budgets.max_validation_repairs:  # as a blocked proposal
            return await self._set_run_state(
                run, RunState.FAILED, "validation blocked", code=ReasonCode.VALIDATION_FAILED
            )
        cont.repairs += 1
        await self._persist(run.run_id)
        return DriverInput(
            task=run.task, observations=tuple(cont.observations.values()), findings=(finding,)
        )

    async def _on_plan(
        self,
        run: RunRecord,
        cont: _Continuation,
        proposal: ActionProposal,
        action: ActionRecord,
        digest_ctx: StepDigestContext,
    ) -> tuple[ActionRecord, list[StepRecord]]:
        """Compile, validate, digest and store ``proposal`` as the 1-step plan of a validated
        ``action``. Returns the action linked to the plan and the approval-wait start row for
        the approval write; on a failure, records ``feature.fallback`` and returns the action
        unlinked and no rows, so the proposal continues on today's path."""
        if run.task_id is None:
            return action, []  # unresolved at admission, recorded there once; runs as `off`
        task = self._on_task(run)
        if task is None:  # the linked definition is no longer admitted (a resumed run)
            await self._fall_back(run, ReasonCode.IR_TASK_UNRESOLVED)
            return action, []
        try:
            plan = compile_proposal(proposal, task, plan_id=new_id("plan"))
        except Exception:  # an IR error never reaches the run; today's path continues
            await self._fall_back(run, ReasonCode.IR_COMPILE_FAILED)
            return action, []
        effects = {
            cid: self._registry.capabilities[cid].effect
            for cid in task.capabilities
            if cid in self._registry.capabilities
        }
        limits = PlanValidationContext(
            effects=effects, max_admitted_writes=cont.ctx.budgets.max_admitted_writes
        )
        try:
            findings = validate_plan(plan, task, limits)
            digest = compute_digest(
                plan_digest_input(
                    plan, {SINGLE_STEP_ID: digest_ctx}, run_operation_id=run.logical_operation_id
                )
            )
        except Exception:  # the digest profile is the validate stage's
            findings, digest = (), None
        if findings or digest != action.digest:  # the approval binds today's action digest
            await self._fall_back(run, ReasonCode.IR_VALIDATION_FAILED)
            return action, []
        linked = action.model_copy(update={"plan_id": plan.plan_id, "step_index": 0})
        validate = await self._step_pair(
            linked, StepKind.VALIDATE, StepStatus.SUCCEEDED, input_refs=digest_ctx.evidence
        )
        compiled = {
            "plan_id": plan.plan_id,
            "plan_digest": digest,
            "step_count": len(plan.steps),
            "task_id": task.task_id,
            "task_version": task.version,
            "digest_matches": True,
        }
        await self._store.put_plan(
            run.tenant_id,
            run.run_id,
            plan,
            [(RunEventType.IR_PLAN_COMPILED, compiled, action.action_id), *validate],
        )
        return linked, await self._step_start(linked, StepKind.APPROVAL_WAIT)

    async def _fall_back(self, run: RunRecord, reason: ReasonCode) -> None:
        current = await self._store.get_run(run.tenant_id, run.run_id)
        await self.record_fallback(current, FEATURE, reason)

    # -- step records ----------------------------------------------------------------------
    @staticmethod
    def _step_id(action: ActionRecord, kind: StepKind) -> str:
        return f"{action.plan_id}/{SINGLE_STEP_ID}/{kind}"

    async def _last_steps(self, action: ActionRecord) -> list[StepRecord]:
        return await self._store.list_steps(action.tenant_id, action.run_id)

    async def _step_start(
        self, action: ActionRecord, kind: StepKind, *, input_refs: Iterable[EvidenceRef] = ()
    ) -> list[StepRecord]:
        """The start row of a linked action's stage; none for an unlinked action (today's
        path, ``off`` and ``shadow`` included)."""
        if action.plan_id is None:
            return []
        steps = await self._last_steps(action)
        return [
            start_step(
                tenant_id=action.tenant_id,
                run_id=action.run_id,
                step_id=self._step_id(action, kind),
                sequence=steps[-1].sequence + 1 if steps else 0,
                kind=kind,
                now=self._clock(),
                action_id=action.action_id,
                input_refs=input_refs,
            )
        ]

    async def _step_finish(
        self, action: ActionRecord, kind: StepKind, status: StepStatus
    ) -> list[StepRecord]:
        """The row that ends the stage's open start row; none when no start row is open."""
        if action.plan_id is None:
            return []
        steps = await self._last_steps(action)
        step_id = self._step_id(action, kind)
        rows = [s for s in steps if s.step_id == step_id]
        if not rows or rows[-1].status is not StepStatus.STARTED:
            return []
        now = max(self._clock(), rows[-1].started_at)
        return [finish_step(rows[-1], sequence=steps[-1].sequence + 1, status=status, now=now)]

    async def _step_pair(
        self,
        action: ActionRecord,
        kind: StepKind,
        status: StepStatus,
        *,
        input_refs: Iterable[EvidenceRef] = (),
    ) -> list[StepRecord]:
        """Both rows of a stage recorded in one write (validate, verify)."""
        started = await self._step_start(action, kind, input_refs=input_refs)
        if not started:
            return []
        (row,) = started
        now = max(self._clock(), row.started_at)
        return [row, finish_step(row, sequence=row.sequence + 1, status=status, now=now)]

    async def _transition_with_steps(
        self,
        action: ActionRecord,
        to: ActionState,
        event: tuple[RunEventType, dict[str, Any]],
        steps: list[StepRecord],
    ) -> ActionRecord:
        """`_transition` with step rows in its batch; exactly `_transition` without rows."""
        if not steps:
            return await self._transition(action, to, event)
        if to not in ALLOWED_ACTION_TRANSITIONS[action.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal transition {action.state}->{to}")
        batch: EventBatch = [(event[0], event[1], action.action_id), *steps]
        updated = action.model_copy(update={"state": to, "revision": action.revision + 1})
        return await self._store.put_action(updated, action.revision, batch)

    # -- acceptance ------------------------------------------------------------------------
    async def _acceptance_unmet(self, run: RunRecord) -> bool:
        """Whether a run in ``on`` that resolved a definition ends without meeting its
        acceptance spec (ADR 0028). Read from the kernel's own records: VERIFIED actions and
        the verifier's reports, never model output (ENG-TRUST-1). A linked definition that is
        no longer admitted cannot be checked, so the run fails closed."""
        if not self._ir_on or run.task_id is None:
            return False
        task = self._run_task(run)
        if task is None:
            return True
        actions = await self._store.list_actions(run.tenant_id, run.run_id)
        verified = [a for a in actions if a.state is ActionState.VERIFIED]
        counts = Counter(a.contract_id for a in verified)
        answer_ids = {
            a.action_id for a in verified if a.contract_id == task.acceptance.required_answer
        }
        reports: list[OutcomeReport] = []
        if answer_ids:
            for event in await self._store.list_events(run.tenant_id, run.run_id):
                if event.type is RunEventType.OUTCOME_REPORTED and event.action_id in answer_ids:
                    try:
                        reports.append(OutcomeReport.model_validate(event.payload))
                    except ValidationError:  # the verifier-unavailable shape is no report
                        continue
        return not acceptance_met(task.acceptance, counts, reports)

    async def _succeed(self, run: RunRecord, reason: str, code: ReasonCode) -> RunRecord:
        """End the run SUCCEEDED, or FAILED with ``ACCEPTANCE_UNMET`` in ``on`` when the
        definition's acceptance spec is not met."""
        if await self._acceptance_unmet(run):
            return await self._fail_unmet(run)
        return await self._set_run_state(run, RunState.SUCCEEDED, reason, code=code)

    async def _fail_unmet(self, run: RunRecord) -> RunRecord:
        """The one ``ACCEPTANCE_UNMET`` ending, shared by every finish path."""
        return await self._set_run_state(
            run, RunState.FAILED, "acceptance unmet", code=ReasonCode.ACCEPTANCE_UNMET
        )
