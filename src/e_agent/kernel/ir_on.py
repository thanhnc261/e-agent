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
  (`_step_start`, `_step_finish`, `_step_pair`, `_revalidated`, `_close_open`);
- the admitted definition is snapshotted into the run's continuation and used for the whole
  run, whatever the registry later holds (Codex C-1); a bound run without a readable snapshot
  fails before its next driver turn (`_unbound_snapshot`, 2c.6 review R-2), and its tool set
  is empty as a second defence;
- at run end the acceptance spec is checked (`_acceptance_gap`, through `_succeed` or
  `_fail_unmet` on the live finish paths and on recovery); unmet ends ``ACCEPTANCE_UNMET``
  with a ``KERNEL-ACCEPTANCE`` finding in the same write (Codex C-2).

Fallback (ENG-TOGGLE-2): before the first reservation, an unresolved definition, a compile
failure or a validation failure records ``feature.fallback`` with a fixed message and the
proposal continues on today's path, unlinked; after the reservation nothing falls back. A run
that resolves no definition at admission falls back there, once, and then runs as ``off``.
Only the pure IR calls are guarded; a store error propagates.

`_with_tools`, the one function both driver call sites use, also runs the per-call route
check (`FeaturesMixin._check_route`, ADR 0032 §9, T23).
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import timedelta
from types import MappingProxyType
from typing import Any

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.common import new_id
from e_agent.contracts.context import Budgets
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.features import FeatureMode
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.run import ReasonCode, RunRecord, RunState
from e_agent.contracts.step import StepKind, StepRecord, StepStatus
from e_agent.contracts.task import GROUNDED_ANSWER, AcceptanceSpec, TaskDefinition, acceptance_met
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.sdk.ports import DriverInput
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
from .reconstruct import without_reconstruction_keys
from .step import finish_step, start_step

FEATURE = "execution_ir"
OUTSIDE_SET = "The proposed capability is not in the run's task definition."
"""The fixed message of the ``KERNEL-PLAN-CAPABILITY`` repair finding (no model text)."""


PLAN_INTERRUPTED = "plan interrupted between steps; the remaining steps were not started"
"""The fixed reason of a plan that cannot resume between its steps (Task 2c.8): a process
no longer in ``on``, or a run recovery cannot resume (`PlanFlowMixin._resume_plan`)."""

NO_CONNECTION = "The proposed connection is not available to this run for the capability."
"""The fixed message of the ``KERNEL-CONNECTION`` repair finding (2c.9, no model text)."""
NO_VERIFIER = "No independent verifier is available for the proposed answer."
"""The fixed message of the ``KERNEL-VERIFIER`` finding (2c.8c review P-1)."""

ACCEPTANCE_MESSAGES = MappingProxyType(
    {
        "effects": "The run ended without the required verified effects.",
        "answer": "The run ended without the required verified answer.",
        "either": "The run ended with neither the required verified effects "
        "nor the required verified answer.",
        "unavailable": "The run's admitted task definition is unavailable, "
        "so its acceptance cannot be met.",
        "grounded": "The run ended without a grounded answer.",
    }
)
"""The fixed messages of the ``KERNEL-ACCEPTANCE`` finding, by the alternative left unmet."""


def acceptance_gap(spec: AcceptanceSpec | None) -> str:
    """The fixed message naming the alternative an unmet ``spec`` left unmet (no model text)."""
    if spec is None:
        return ACCEPTANCE_MESSAGES["unavailable"]
    if spec.grounded_answer:
        return ACCEPTANCE_MESSAGES["grounded"]
    if spec.required_effects and spec.required_answer is not None:
        return ACCEPTANCE_MESSAGES["either"]
    return ACCEPTANCE_MESSAGES["effects" if spec.required_effects else "answer"]


def merged_budgets(profile: Budgets, task: TaskDefinition) -> Budgets:
    """The profile's budgets with only the fields the definition sets merged over them
    (2c.2 review R-2); admission already refused a definition that widens one (D7).

    Called once, at admission, on the registry's definition. Never on a continuation's
    snapshot: ``model_fields_set`` does not survive its JSON round trip, so every field would
    read as set and widen the profile back to the defaults (2c.6 review R-1). A resumed run
    keeps the merged budgets of its persisted ``TaskContext``."""
    if task.budgets is None:
        return profile
    return profile.model_copy(
        update={name: getattr(task.budgets, name) for name in task.budgets.model_fields_set}
    )


def _fixed(rule_id: str, message: str) -> Finding:
    return Finding(rule_id=rule_id, rule_version="1", status=ValidationStatus.FAIL, message=message)


class IrOnMixin(FeaturesMixin):
    @property
    def _ir_on(self) -> bool:
        return self._features.execution_ir is FeatureMode.ON

    def _on_task(self, run: RunRecord, cont: _Continuation | None) -> TaskDefinition | None:
        """The definition a bound run executes in ``on``: the snapshot admitted into its
        continuation, never a fresh registry lookup (ADR 0028, Codex C-1). None in ``off`` and
        ``shadow`` (shadow narrows nothing), for a run that resolved none, and for a bound run
        whose snapshot is missing or names another definition."""
        if not self._ir_on or run.task_id is None or cont is None or cont.task is None:
            return None
        task = cont.task
        return task if (task.task_id, task.version) == (run.task_id, run.task_version) else None

    def _allowed(self, run: RunRecord, cont: _Continuation | None) -> tuple[str, ...] | None:
        """The run's tool set in ``on``: the snapshot's capabilities. A bound run without a
        readable snapshot fails closed with the empty set; None (today's tools) is only for a
        run that never resolved a definition."""
        if not self._ir_on or run.task_id is None:
            return None
        task = self._on_task(run, cont)
        return () if task is None else task.capabilities

    def _with_tools(
        self, run: RunRecord, cont: _Continuation, step_input: DriverInput
    ) -> DriverInput:
        """The driver input for one turn, carrying the run's tool set in ``on`` (D6). Every
        model call is built here, so the route check runs here first (ADR 0032 §9)."""
        self._check_route(cont)
        allowed = self._allowed(run, cont)
        if allowed is None:
            return step_input
        return dataclasses.replace(step_input, allowed_capabilities=allowed)

    def _ttl_for(self, run: RunRecord, cont: _Continuation) -> timedelta:
        task = self._on_task(run, cont)
        if task is None or task.approval_ttl is None:
            return self._approval_ttl
        return task.approval_ttl

    # -- proposals -------------------------------------------------------------------------
    async def _outside_task_set(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput | None:
        """A proposal outside the run's tool set is a repair finding, never a fallback: the
        fallback path would widen the set. None when the proposal is inside it."""
        allowed = self._allowed(run, cont)
        if allowed is None or proposal.contract_id in allowed:
            return None
        return await self._repair_finding(
            run, cont, (_fixed("KERNEL-PLAN-CAPABILITY", OUTSIDE_SET),)
        )

    async def _repair_finding(
        self, run: RunRecord, cont: _Continuation, findings: tuple[Finding, ...]
    ) -> RunRecord | DriverInput:
        """Kernel findings on a proposal that made no action: recorded in
        ``validation.completed`` and returned to the driver within ``max_validation_repairs``,
        as a blocked proposal is; past the budget the run fails ``VALIDATION_FAILED``."""
        payload = {"status": "FAIL", "findings": [f.model_dump(mode="json") for f in findings]}
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
            task=run.task, observations=tuple(cont.observations.values()), findings=findings
        )

    async def _connection_refused(
        self, run: RunRecord, cont: _Continuation
    ) -> RunRecord | DriverInput:
        """A proposal or plan step on a connection the run cannot use, or one without a
        binding for its capability: the fixed ``KERNEL-CONNECTION`` repair finding, never an
        exception that strands the run (2c.9). The kernel never picks another connection."""
        return await self._repair_finding(run, cont, (_fixed("KERNEL-CONNECTION", NO_CONNECTION),))

    async def _no_verifier(self, run: RunRecord) -> RunRecord:
        """An answer whose capability has no verifier: FAILED ``VERIFICATION_FAILED`` with the
        fixed ``KERNEL-VERIFIER`` finding in the same write, before any action exists."""
        finding = _fixed("KERNEL-VERIFIER", NO_VERIFIER).model_dump(mode="json")
        payload = {"status": "FAIL", "findings": [finding]}
        return await self._set_run_state(
            run,
            RunState.FAILED,
            "no verifier for answer",
            code=ReasonCode.VERIFICATION_FAILED,
            before=[(RunEventType.VALIDATION_COMPLETED, payload, None)],
        )

    def _kept(self, report: OutcomeReport) -> OutcomeReport:
        """The report as the kernel stores it: read-back values only in ``on``, where lineage
        and recovery need them; ``off`` and ``shadow`` store exactly what they stored before."""
        if self._ir_on or report.verified_values is None:
            return report
        return report.model_copy(update={"verified_values": None})

    @staticmethod
    def _approved_input(cont: _Continuation) -> dict[str, Any]:
        """The approved digest input the action in flight is checked against: the current
        plan step's for a multi-step plan (Task 2c.7), else the one canonical proposal."""
        if cont.plan is not None:
            return cont.plan.inputs[cont.plan.current]
        return cont.canonical_proposal

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
        task = self._on_task(run, cont)
        if task is None:  # defensive: `_outside_task_set` already refused every proposal
            raise KernelError(ErrorCode.CONFLICT, "the run's admitted definition is unavailable")
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
    def _step_id(self, action: ActionRecord, kind: StepKind) -> str:
        """``<plan id>/<plan step id>/<kind>``: the plan's own step id for a multi-step plan,
        `SINGLE_STEP_ID` for a compiled single proposal."""
        cont = self._runs.get(action.run_id)
        plan = cont.plan if cont is not None else None
        step = SINGLE_STEP_ID
        if plan is not None and plan.plan_id == action.plan_id and action.step_index is not None:
            step = plan.step_ids[action.step_index]
        return f"{action.plan_id}/{step}/{kind}"

    async def _last_steps(self, action: ActionRecord) -> list[StepRecord]:
        return await self._store.list_steps(action.tenant_id, action.run_id)

    async def _step_start(
        self,
        action: ActionRecord,
        kind: StepKind,
        *,
        input_refs: Iterable[EvidenceRef] = (),
        after: Sequence[StepRecord] = (),
    ) -> list[StepRecord]:
        """The start row of a linked action's stage; none for an unlinked action (today's
        path, ``off`` and ``shadow`` included). ``after`` are rows not yet stored that the
        same write records first, so the sequence continues past them."""
        if action.plan_id is None:
            return []
        steps = [*await self._last_steps(action), *after]
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
        """Both rows of a stage recorded in one write (validate, revalidate, verify)."""
        started = await self._step_start(action, kind, input_refs=input_refs)
        if not started:
            return []
        (row,) = started
        now = max(self._clock(), row.started_at)
        return [row, finish_step(row, sequence=row.sequence + 1, status=status, now=now)]

    async def _revalidated(self, action: ActionRecord, status: StepStatus) -> list[StepRecord]:
        """The rows of a dispatch-time revalidation (target §6.4.5): the end of a later plan
        step's open validate row, or a validate pair for an approved step whose proposal-time
        row is already closed."""
        return await self._step_finish(action, StepKind.VALIDATE, status) or (
            await self._step_pair(action, StepKind.VALIDATE, status)
        )

    async def _close_open(self, action: ActionRecord, status: StepStatus) -> list[StepRecord]:
        """End every open row of a linked action that stops where it is (a cancel, a
        recovery block), so a finished run leaves no stage started."""
        if action.plan_id is None:
            return []
        steps = await self._last_steps(action)
        last = {s.step_id: s for s in steps if s.action_id == action.action_id}
        rows, sequence = [], (steps[-1].sequence + 1 if steps else 0)
        for row in (r for r in last.values() if r.status is StepStatus.STARTED):
            now = max(self._clock(), row.started_at)
            rows.append(finish_step(row, sequence=sequence, status=status, now=now))
            sequence += 1
        return rows

    # -- acceptance ------------------------------------------------------------------------
    async def _acceptance_gap(self, run: RunRecord, cont: _Continuation | None) -> str | None:
        """The fixed ``KERNEL-ACCEPTANCE`` message when a bound run in ``on`` ends without
        meeting its admitted definition's acceptance spec (ADR 0028), else None. Read from
        the kernel's own records: VERIFIED actions and the verifier's reports, never model
        output (ENG-TRUST-1). A bound run without its snapshot cannot be checked, so it fails
        closed. ``off``, ``shadow`` and an unbound run read nothing and return None."""
        if not self._ir_on or run.task_id is None:
            return None
        task = self._on_task(run, cont)
        if task is None:
            return acceptance_gap(None)
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
                        report = without_reconstruction_keys(event.type, event.payload)
                        reports.append(OutcomeReport.model_validate(report))
                    except ValidationError:  # the verifier-unavailable shape is no report
                        continue
        grounded = task.acceptance.grounded_answer and any(  # its own record (ADR 0033 §3)
            e.type is RunEventType.MESSAGE_FINAL and e.payload.get("contract_id") == GROUNDED_ANSWER
            for e in await self._store.list_events(run.tenant_id, run.run_id)
        )
        if acceptance_met(task.acceptance, counts, reports, grounded=grounded):
            return None
        return acceptance_gap(task.acceptance)

    async def _succeed(
        self,
        run: RunRecord,
        cont: _Continuation | None,
        reason: str,
        code: ReasonCode,
        *,
        final: str | None = None,
    ) -> RunRecord:
        """End the run SUCCEEDED, or FAILED with ``ACCEPTANCE_UNMET`` in ``on`` when the
        admitted definition's acceptance spec is not met. A multi-step plan succeeds only when
        the store holds a VERIFIED action for each of its steps: recovery resumes a plan with
        a step left first (`_resume_plan`), and one it cannot resume fails ``INTERRUPTED``.
        ``final`` is the driver's closing text, recorded as ``message.final`` in its own write
        only when the run succeeds, as a verified finish skips its acknowledgement when
        acceptance is unmet."""
        plan = cont.plan if cont is not None else None
        if plan is not None:  # the durable actions decide, never the snapshot (Codex C-2)
            actions = await self._store.list_actions(run.tenant_id, run.run_id)
            verified = {
                a.step_index
                for a in actions
                if a.plan_id == plan.plan_id and a.state is ActionState.VERIFIED
            }
            if verified != set(range(len(plan.step_ids))):
                return await self._set_run_state(
                    run, RunState.FAILED, PLAN_INTERRUPTED, code=ReasonCode.INTERRUPTED
                )
        gap = await self._acceptance_gap(run, cont)
        if gap is not None:
            return await self._fail_unmet(run, gap)
        if final is not None:
            run = await self._store.update_run(
                run.model_copy(update={"revision": run.revision + 1}),
                run.revision,
                [(RunEventType.MESSAGE_FINAL, {"text": final}, None)],
            )
        return await self._set_run_state(run, RunState.SUCCEEDED, reason, code=code)

    async def _fail_unmet(self, run: RunRecord, message: str) -> RunRecord:
        """The one ``ACCEPTANCE_UNMET`` ending, shared by every finish path: the kernel's
        acceptance finding (persisted as validation findings are, in ``validation.completed``)
        ahead of the terminal transition, in one write."""
        finding = _fixed("KERNEL-ACCEPTANCE", message)
        payload = {"status": "FAIL", "findings": [finding.model_dump(mode="json")]}
        return await self._set_run_state(
            run,
            RunState.FAILED,
            "acceptance unmet",
            code=ReasonCode.ACCEPTANCE_UNMET,
            before=[(RunEventType.VALIDATION_COMPLETED, payload, None)],
        )

    async def _unbound_snapshot(self, run: RunRecord, cont: _Continuation) -> RunRecord | None:
        """A bound run in ``on`` whose admitted snapshot is unreadable ends at once, before
        any driver turn, rather than spending turns on an empty tool set (2c.6 review R-2).
        None for every other run."""
        if not self._ir_on or run.task_id is None or self._on_task(run, cont) is not None:
            return None
        return await self._fail_unmet(run, acceptance_gap(None))
