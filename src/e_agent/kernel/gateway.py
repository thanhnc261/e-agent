"""Authorized, recorded reads through the action gateway (Phase 1 split of coordinator.py)."""

from __future__ import annotations

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.events import RunEventType
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import (
    Observation,
    ReadRequest,
)

from .continuation import ContinuationMixin, _Continuation
from .errors import ErrorCode, KernelError


class GatewayMixin(ContinuationMixin):
    # ---------------------------------------------------------------- reads
    async def _gateway_read(
        self, cont: _Continuation, request: ReadRequest, *, count_budget: bool
    ) -> Observation:
        ctx = cont.ctx
        if count_budget and cont.read_calls >= ctx.budgets.max_read_calls:
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "read call budget exhausted")
        descriptor = self._registry.descriptor(request.contract_id)
        if descriptor.effect is not EffectKind.READ:
            raise KernelError(ErrorCode.INVALID_REQUEST, "write capability requested as a read")
        self._connections.usable(ctx, request.connection_id)
        decision = self._policy.evaluate(ctx, descriptor, request.connection_id)
        if not decision.permitted:
            raise KernelError(ErrorCode.FORBIDDEN, "read not permitted")
        binding = self._registry.resolve(request.contract_id, request.connection_id)
        obs = await self._timed(
            cont,
            lambda: self._registry.executor_for(binding).read(ctx, binding, request),
            ctx.budgets.provider_timeout_seconds,
        )
        if (
            obs.evidence.tenant_id != ctx.tenant_id
            or obs.request_id != request.request_id
            or obs.contract_id != request.contract_id
        ):
            raise KernelError(
                ErrorCode.FORBIDDEN, "read result does not match the authorized request"
            )
        if count_budget:
            cont.read_calls += 1
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.READ_RECORDED,
                    {
                        "request_id": request.request_id,
                        "contract_id": request.contract_id,
                        "connection_id": request.connection_id,
                        "evidence_id": obs.evidence.evidence_id,
                        "revision": obs.evidence.revision,
                    },
                    None,
                )
            ],
        )
        return obs

    async def _record_rejected_read(
        self, cont: _Continuation, request: ReadRequest, exc: KnownNoEffectError
    ) -> None:
        """A provider-rejected read had no effect: count it and tell the driver (ADR 0022)."""
        cont.read_calls += 1
        cont.read_errors[request.request_id] = f"{exc.code}: {exc.safe_message}"
        run = await self._store.get_run(cont.ctx.tenant_id, cont.ctx.run_id)
        await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [
                (
                    RunEventType.READ_REJECTED,
                    {
                        "request_id": request.request_id,
                        "contract_id": request.contract_id,
                        "connection_id": request.connection_id,
                        "code": exc.code,
                        "message": exc.safe_message,
                    },
                    None,
                )
            ],
        )
