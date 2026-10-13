"""Approval requests, expiry and decisions (Phase 1 split of coordinator.py).

Approval digests stay in approval.py.
"""

from __future__ import annotations

from datetime import datetime

from e_agent.contracts.action import ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalDecision, ApprovalRecord
from e_agent.contracts.common import new_id
from e_agent.contracts.context import Principal
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)

from .approval import (
    ApprovalPresentation,
    presentation_for,
)
from .continuation import LOG, ContinuationMixin, _Continuation
from .errors import ErrorCode, KernelError
from .policy import APPROVER_ROLE


class ApprovalFlowMixin(ContinuationMixin):
    # ------------------------------------------------------------- approvals
    async def pending_approval(self, tenant_id: str, run_id: str) -> ApprovalPresentation:
        run = await self._store.get_run(tenant_id, run_id)
        cont = await self._load_cont(run.tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL or cont.pending_action_id is None:
            raise KernelError(ErrorCode.NOT_FOUND, "no pending approval")
        action = await self._store.get_action(tenant_id, cont.pending_action_id)
        assert cont.approval_requested_at is not None
        previous = None
        if action.supersedes_action_id is not None:
            superseded = await self._store.get_action(tenant_id, action.supersedes_action_id)
            previous = superseded.arguments
        return presentation_for(
            action,
            previous_arguments=previous,
            input_schema=self._registry.input_schemas.get(
                self._registry.descriptor(action.contract_id).input_schema_id
            ),
            run_revision=run.revision,
            canonical_proposal=cont.canonical_proposal,
            findings=cont.last_validation.findings if cont.last_validation else (),
            expires_at=cont.approval_requested_at + self._approval_ttl,
        )

    async def _expire_pending(self, cont: _Continuation, action: ActionRecord) -> RunRecord:
        """Expiry outcome of a pending approval, shared by decide and the sweeper (ADR 0019).

        The continuation is persisted by `_set_run_state` together with the run update.
        """
        if action.state is not ActionState.BLOCKED:  # BLOCKED: resuming an interrupted expiry
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.APPROVAL_DECIDED, {"decision": "expired"}),
            )
        cont.pending_action_id = None
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        return await self._set_run_state(
            run, RunState.FAILED, "approval expired", code=ReasonCode.APPROVAL_EXPIRED
        )

    async def _enqueue_expiry(self, run: RunRecord, now: datetime) -> bool:
        if await self._store.has_pending_work(run.tenant_id, run.run_id):
            return False  # a decision or an earlier sweep is already queued or running
        try:
            cont = await self._peek_cont(run.tenant_id, run.run_id)
        except KernelError:
            LOG.debug("approval sweep: no continuation for run %s/%s", run.tenant_id, run.run_id)
            return False
        if cont.pending_action_id is None or cont.approval_requested_at is None:
            return False
        if now <= cont.approval_requested_at + self._approval_ttl:
            return False
        payload = {
            "action_id": cont.pending_action_id,
            "requested_at": cont.approval_requested_at.isoformat(),
        }
        await self._store.enqueue_work(
            run.tenant_id, run.run_id, "expire", payload, digest(payload)
        )
        return True

    async def sweep_expired_approvals(self) -> int:
        """Enqueue fenced `expire` work for every approval past its TTL.

        Never mutates run, action or continuation state: the worker applies the expiry
        under a work claim (ADR 0019).
        """
        now = self._clock()
        queued = 0
        for run in await self._store.list_unfinished_runs():
            if run.state is not RunState.WAITING_APPROVAL:
                continue
            try:
                if await self._enqueue_expiry(run, now):
                    queued += 1
            except Exception as exc:  # one bad run must not block the rest of the sweep
                LOG.warning(
                    "approval sweep skipped run %s/%s (%s)",
                    run.tenant_id,
                    run.run_id,
                    type(exc).__name__,
                    exc_info=True,
                )
        return queued

    async def expire_approval(self, tenant_id: str, run_id: str, action_id: str) -> RunRecord:
        """Executed under a work claim: re-check everything, then apply the expiry outcome."""
        run = await self._store.get_run(tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL:
            return run
        cont = await self._load_cont(tenant_id, run_id)
        if cont.pending_action_id != action_id or cont.approval_requested_at is None:
            return run
        if self._clock() <= cont.approval_requested_at + self._approval_ttl:
            return run
        action = await self._store.get_action(tenant_id, action_id)
        return await self._expire_pending(cont, action)

    async def decide(
        self,
        *,
        actor: Principal,
        run_id: str,
        action_id: str,
        action_digest: str,
        expected_run_revision: int,
        decision: ApprovalDecision,
    ) -> RunRecord:
        run = await self._store.get_run(actor.tenant_id, run_id)
        if APPROVER_ROLE not in actor.roles:
            raise KernelError(ErrorCode.FORBIDDEN, "actor is not an approver")
        if actor.principal_id == run.requester_id and not self._allow_self_approval:
            raise KernelError(ErrorCode.FORBIDDEN, "the requester cannot approve their own run")
        if run.revision != expected_run_revision:
            raise KernelError(ErrorCode.CONFLICT, "run changed; reload before deciding")
        cont = await self._load_cont(run.tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL or cont.pending_action_id != action_id:
            raise KernelError(ErrorCode.CONFLICT, "action is not awaiting approval")
        action = await self._store.get_action(actor.tenant_id, action_id)
        if action.digest != action_digest:
            raise KernelError(ErrorCode.APPROVAL_STALE, "digest does not match pending action")
        if cont.surface_digest and cont.surface_digest != self._registry.surface_digest():
            # Plugins, schemas or bindings changed since the proposal was made (T17).
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.APPROVAL_DECIDED, {"decision": "surface_changed"}),
            )
            cont.pending_action_id = None
            run = await self._store.get_run(actor.tenant_id, run_id)
            await self._set_run_state(
                run, RunState.FAILED, "capability surface changed", code=ReasonCode.SURFACE_CHANGED
            )
            raise KernelError(ErrorCode.APPROVAL_STALE, "capabilities changed; start a new run")
        now = self._clock()
        assert cont.approval_requested_at is not None
        if now > cont.approval_requested_at + self._approval_ttl:
            await self._expire_pending(cont, action)
            raise KernelError(ErrorCode.APPROVAL_STALE, "approval window expired")

        record = ApprovalRecord(
            approval_id=new_id("apr"),
            tenant_id=actor.tenant_id,
            run_id=run_id,
            action_id=action_id,
            action_digest=action_digest,
            actor_id=actor.principal_id,
            decision=decision,
            policy_version=str(cont.canonical_proposal["policy_version"]),
            issued_at=now,
            expires_at=now + self._approval_ttl,
        )
        approved_action = action.model_copy(
            update={
                "state": ActionState.BLOCKED
                if decision is ApprovalDecision.REJECTED
                else ActionState.APPROVED,
                "revision": action.revision + 1,
            }
        )
        await self._store.record_approval(
            record,
            [
                (
                    RunEventType.APPROVAL_DECIDED,
                    {"decision": decision, "actor_id": actor.principal_id, "digest": action_digest},
                    action_id,
                )
            ],
            action=approved_action,
            expected_revision=action.revision,
        )
        if decision is ApprovalDecision.REJECTED:
            cont.pending_action_id = None
            run = await self._store.get_run(actor.tenant_id, run_id)
            return await self._set_run_state(
                run, RunState.FAILED, "rejected by approver", code=ReasonCode.APPROVAL_REJECTED
            )
        return await self._dispatch(cont, approved_action, record)
