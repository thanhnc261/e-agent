"""Reconciliation, cancellation and restart recovery (Phase 1 split of coordinator.py)."""

from __future__ import annotations

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.context import Principal
from e_agent.contracts.events import RunEventType
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.contracts.run import (
    TERMINAL_RUN_STATES,
    ReasonCode,
    RunRecord,
    RunState,
)

from .continuation import LOG, _Continuation
from .errors import ErrorCode, KernelError
from .ir_on import IrOnMixin


class RecoveryMixin(IrOnMixin):
    # --------------------------------------------------------- reconciliation
    async def reconcile(self, operator: Principal, run_id: str) -> RunRecord:
        """Read-only reconciliation of UNKNOWN actions. Never sends a write. A plan step it
        proves committed and verified queues the plan's resume (`_after_step_verified`)."""
        run = await self._store.get_run(operator.tenant_id, run_id)
        if run.state is not RunState.NEEDS_RECONCILIATION:
            raise KernelError(ErrorCode.CONFLICT, "run does not need reconciliation")
        cont = await self._load_cont(run.tenant_id, run_id)
        actions = [
            a
            for a in await self._store.list_actions(operator.tenant_id, run_id)
            if a.state is ActionState.UNKNOWN
        ]
        if not actions:
            raise KernelError(ErrorCode.CONFLICT, "no unresolved action")
        action = actions[0]
        binding = self._registry.resolve(action.contract_id, action.connection_id)
        found = await self._registry.executor_for(binding).reconcile(cont.ctx, binding, action)
        await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.RECONCILIATION_COMPLETED,
                    {"found": found.status if found else "not_found"},
                    action.action_id,
                )
            ],
        )
        if found is None:
            return await self._store.get_run(operator.tenant_id, run_id)  # stays unresolved
        return await self._apply_receipt(cont, action, found)

    async def cancel(self, actor: Principal, run_id: str) -> RunRecord:
        run = await self._store.get_run(actor.tenant_id, run_id)
        if run.state in TERMINAL_RUN_STATES:
            return run
        unresolved = [
            a
            for a in await self._store.list_actions(actor.tenant_id, run_id)
            if a.state in {ActionState.DISPATCHING, ActionState.UNKNOWN}
        ]
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.RUN_CANCEL_REQUESTED, {"actor_id": actor.principal_id}, None)],
        )
        if unresolved:
            return await self._set_run_state(
                run,
                RunState.NEEDS_RECONCILIATION,
                "cancel requested; effect must be reconciled",
                code=ReasonCode.EFFECT_UNKNOWN,
            )
        try:
            cont: _Continuation | None = await self._load_cont(actor.tenant_id, run_id)
        except KernelError:
            cont = None
        if cont and cont.pending_action_id:
            pending = await self._store.get_action(actor.tenant_id, cont.pending_action_id)
            if ActionState.BLOCKED in ALLOWED_ACTION_TRANSITIONS[pending.state]:
                await self._transition(pending, ActionState.BLOCKED)
            cont.pending_action_id = None
        cancelled = await self._set_run_state(
            run, RunState.CANCELLED, "cancelled before dispatch", code=ReasonCode.CANCELLED
        )
        active = self._active_calls.get(run_id)
        if active is not None:
            active.cancel()
        return cancelled

    # --------------------------------------------------------------- recovery
    async def recover(self) -> list[RunRecord]:
        """Startup recovery (MVP design §9 crash rules). Never sends a write.

        - DISPATCHING: the call may have executed -> UNKNOWN, reconcile later.
        - APPROVED/RESERVED without dispatch: blocked; a new approval is required.
        - COMMITTED while VERIFYING: re-run the independent read-back.
        - RUNNING with no pending effect: the driver turn was lost -> FAILED.
        - A multi-step plan (execution IR ``on``) whose latest action is VERIFIED with a
          later step unstarted: enqueue one fenced ``resume`` work item; the worker resumes
          the plan under its claim (`resume_plan`, ADR 0025 amendment). Committed steps are
          never replayed.
        """
        recovered: list[RunRecord] = []
        for run in await self._store.list_unfinished_runs():
            if await self._store.has_pending_work(run.tenant_id, run.run_id):
                continue
            try:
                result = await self._recover_run(run)
            except Exception as exc:  # one bad run must not block the rest of recovery
                LOG.warning(
                    "startup recovery skipped run %s/%s (%s)",
                    run.tenant_id,
                    run.run_id,
                    type(exc).__name__,
                    exc_info=True,
                )
                continue
            if result is not None:
                recovered.append(result)
        return recovered

    async def recover_run(self, tenant_id: str, run_id: str) -> RunRecord:
        """Apply the crash rules to one run whose host-side work died unexpectedly."""
        run = await self._store.get_run(tenant_id, run_id)
        if run.state in TERMINAL_RUN_STATES:
            return run
        self._runs.pop(run_id, None)  # the in-memory continuation may be mid-mutation
        return await self._recover_run(run) or run

    async def resume_plan(self, tenant_id: str, run_id: str) -> RunRecord:
        """Executed under a ``resume`` work claim (ADR 0025 amendment). Re-check under the
        claim that the run is RUNNING or VERIFYING with plan state, else drop the item; then
        continue the plan as a live finish does, through every pre-reservation guard. A plan
        that can no longer resume (a crashed earlier claim started its next step) gets the
        crash rules, which never send a write."""
        run = await self._store.get_run(tenant_id, run_id)
        if run.state not in {RunState.RUNNING, RunState.VERIFYING}:
            return run
        try:
            cont = await self._load_cont(tenant_id, run_id)
        except KernelError:
            return run
        if cont.plan is None:
            return run
        actions, latest = await self._latest_action(run)
        resumed = None
        if latest is not None:
            self._plan_runs.add(run_id)
            try:
                resumed = await self._resume_plan(cont, latest, actions)
            finally:
                self._plan_runs.discard(run_id)
        if resumed is not None:
            return resumed
        return await self._recover_run(run) or run

    async def _latest_action(
        self, run: RunRecord
    ) -> tuple[list[ActionRecord], ActionRecord | None]:
        """The run's actions and the one its last ``proposal.created`` names."""
        actions = await self._store.list_actions(run.tenant_id, run.run_id)
        events = await self._store.list_events(run.tenant_id, run.run_id)
        latest_id = next(
            (
                event.action_id
                for event in reversed(events)
                if event.type is RunEventType.PROPOSAL_CREATED
            ),
            None,
        )
        return actions, next((a for a in actions if a.action_id == latest_id), None)

    async def _recover_run(self, run: RunRecord) -> RunRecord | None:
        actions, latest = await self._latest_action(run)
        try:
            cont = await self._load_cont(run.tenant_id, run.run_id)
        except KernelError:
            cont = None
        dispatching = [a for a in actions if a.state is ActionState.DISPATCHING]
        undispatched = [
            a for a in actions if a.state in {ActionState.APPROVED, ActionState.RESERVED}
        ]
        committed = [a for a in actions if a.state is ActionState.COMMITTED]
        if dispatching and cont is not None:
            action = dispatching[0]
            now = self._clock()
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                attempt=1,
                status=ReceiptStatus.UNKNOWN,
                sanitized_error="worker lost during dispatch",
                started_at=now,
                finished_at=now,
            )
            return await self._apply_receipt(cont, action, receipt)
        elif undispatched:
            for action in undispatched:
                await self._transition(action, ActionState.BLOCKED)
            if cont is not None:
                cont.pending_action_id = None
            run = await self._store.get_run(run.tenant_id, run.run_id)
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "interrupted before dispatch; approve a new run",
                code=ReasonCode.INTERRUPTED,
            )
        elif committed and cont is not None:
            receipts = await self._store.list_receipts(run.tenant_id, committed[0].action_id)
            return await self._verify(cont, committed[0], receipts[-1])
        elif any(a.state is ActionState.UNKNOWN for a in actions):
            return await self._set_run_state(
                run,
                RunState.NEEDS_RECONCILIATION,
                "persisted write outcome unknown",
                code=ReasonCode.EFFECT_UNKNOWN,
            )
        elif (
            latest is not None
            and latest.state is ActionState.VERIFIED
            and run.state
            not in {
                RunState.WAITING_APPROVAL,
                RunState.WAITING_INPUT,
            }
        ):
            if cont is not None:  # an `on` plan with a step left queues its resume
                resumed = await self._resume_plan(cont, latest, actions)
                if resumed is not None:
                    return resumed
                cont.pending_action_id = None
            # The live finish path's acceptance check (`on`, ADR 0028); `off` is today's.
            return await self._succeed(run, cont, "outcome verified", ReasonCode.VERIFIED)
        elif latest is not None and latest.state is ActionState.VERIFICATION_FAILED:
            return await self._set_run_state(
                run,
                RunState.FAILED,
                "outcome verification failed",
                code=ReasonCode.VERIFICATION_FAILED,
            )
        elif run.state in {RunState.RUNNING, RunState.CREATED}:
            reason = "interrupted during driver turn"
            if latest is not None and latest.plan_id is not None and latest.step_index:
                # A later plan step's action exists, never reserved: fail closed, send nothing.
                reason = f"interrupted before plan step {latest.step_index + 1} reserved"
            return await self._set_run_state(
                run, RunState.FAILED, reason, code=ReasonCode.INTERRUPTED
            )
        return None
