"""Background work: the run-work loop and the approval sweeper (Phase 1 split of api.py).

WorkerMixin is part of ApiState; the logger keeps the name e_agent.server.api.
"""

from __future__ import annotations

import asyncio
import logging

from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.common import new_id
from e_agent.contracts.context import Principal
from e_agent.contracts.run import RunState
from e_agent.contracts.work import WorkClaim
from e_agent.sdk.store import ConcurrencyConflict, NotFound, actor_scope
from e_agent.sdk.tasks import supervised_task

from .bootstrap import Runtime

APPROVAL_SWEEP_SECONDS = 30

LOG = logging.getLogger("e_agent.server.api")


class WorkerMixin:
    runtime: Runtime
    stopping: bool

    async def worker(self) -> None:
        owner = new_id("worker")
        while True:
            try:
                claim = await self.runtime.store.claim_work(owner)
            except Exception:
                await asyncio.sleep(0.2)
                continue
            if claim is None:
                await asyncio.sleep(0.05)
                continue
            await self._run_work(claim)

    async def sweeper(self) -> None:
        while True:
            await asyncio.sleep(APPROVAL_SWEEP_SECONDS)
            try:
                await self.runtime.coordinator.sweep_expired_approvals()
            except Exception as exc:  # the next tick retries; sweeping never fails the server
                LOG.warning("approval sweep failed (%s); retrying next tick", type(exc).__name__)

    async def _run_work(self, claim: WorkClaim) -> None:
        rt = self.runtime
        current = asyncio.current_task()
        assert current is not None

        lease_lost = False

        async def heartbeat() -> None:
            nonlocal lease_lost
            while True:
                await asyncio.sleep(5)
                try:
                    renewed = await rt.store.renew_work(claim)
                except Exception:
                    renewed = False
                if not renewed:
                    lease_lost = True
                    current.cancel()
                    return

        pulse = supervised_task(heartbeat(), name=f"server.heartbeat:{claim.run_id}")
        try:
            async with rt.store.work_scope(claim):
                rt.coordinator.release_continuation(claim.run_id)
                run = await rt.store.get_run(claim.tenant_id, claim.run_id)
                untouched = claim.kind == "start" and run.state is RunState.CREATED
                if claim.kind == "decide" and run.state is RunState.WAITING_APPROVAL:
                    action = await rt.store.get_action(claim.tenant_id, claim.payload["action_id"])
                    untouched = (
                        action.state is ActionState.AWAITING_APPROVAL
                        and run.revision == claim.payload["expected_revision"]
                    )
                if claim.kind == "input" and run.state is RunState.RUNNING:
                    actions = await rt.store.list_actions(claim.tenant_id, claim.run_id)
                    checkpoint = await rt.store.load_continuation(claim.tenant_id, claim.run_id)
                    untouched = bool(checkpoint and checkpoint[1] is not None) and all(
                        action.state
                        in {
                            ActionState.BLOCKED,
                            ActionState.FAILED,
                            ActionState.VERIFIED,
                            ActionState.VERIFICATION_FAILED,
                        }
                        for action in actions
                    )
                if claim.kind == "decide":
                    actor_label = f"principal:{claim.payload['actor']['principal_id']}"
                elif claim.kind in {"start", "input"}:
                    actor_label = f"principal:{run.requester_id}"
                else:
                    actor_label = f"system:worker:{claim.owner}"
                if claim.kind == "expire":
                    # expire_approval re-checks state, pending action and TTL, so replay is safe.
                    untouched = True
                if claim.fence > 1 and not untouched:
                    # A resume claim taken over from a dead owner is a failed resume, and a
                    # failed resume claim never enqueues another (ADR 0025 amendment).
                    with actor_scope(f"system:worker:{claim.owner}"):
                        await rt.coordinator.recover_run(
                            claim.tenant_id, claim.run_id, resume=claim.kind != "resume"
                        )
                else:
                    with actor_scope(actor_label):
                        if claim.kind == "start":
                            await rt.coordinator.start_admitted_run(claim.tenant_id, claim.run_id)
                        elif claim.kind == "input":
                            await rt.coordinator.continue_input(claim.tenant_id, claim.run_id)
                        elif claim.kind == "expire":
                            await rt.coordinator.expire_approval(
                                claim.tenant_id, claim.run_id, claim.payload["action_id"]
                            )
                        elif claim.kind == "resume":  # a plan after a crash (ADR 0025)
                            await rt.coordinator.resume_plan(claim.tenant_id, claim.run_id)
                        else:
                            payload = claim.payload
                            await rt.coordinator.decide(
                                actor=Principal.model_validate(payload["actor"]),
                                run_id=claim.run_id,
                                action_id=payload["action_id"],
                                action_digest=payload["digest"],
                                expected_run_revision=payload["expected_revision"],
                                decision=ApprovalDecision(payload["decision"]),
                            )
                await rt.store.finish_work(claim)
        except asyncio.CancelledError:
            if not lease_lost or self.stopping:
                raise
            # A lost lease stops this claim, not the server worker loop.
            current.uncancel()
        except ConcurrencyConflict:
            # Another owner or a cancellation won. This worker has no recovery authority.
            return
        except Exception:
            LOG.exception("run work failed (run=%s kind=%s)", claim.run_id, claim.kind)
            try:
                async with rt.store.work_scope(claim):
                    with actor_scope(f"system:worker:{claim.owner}"):
                        await self._mark_failed(claim.run_id, resume=claim.kind != "resume")
                    await rt.store.finish_work(claim)
            except Exception:
                # Leave the claim for lease expiry and another owner to reconcile.
                return
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)

    async def _mark_failed(self, run_id: str, *, resume: bool = True) -> None:
        """Unexpected host error: apply the crash rules, never guess an outcome. After a
        failed ``resume`` claim no resume is queued again (``resume=False``)."""
        rt = self.runtime
        try:
            await rt.coordinator.recover_run(rt.operator.tenant_id, run_id, resume=resume)
        except NotFound:
            return
