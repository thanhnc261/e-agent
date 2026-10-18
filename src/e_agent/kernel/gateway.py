"""Authorized, recorded reads through the action gateway (Phase 1 split of coordinator.py)."""

from __future__ import annotations

from e_agent.contracts.capability import EffectKind
from e_agent.contracts.events import RunEventType
from e_agent.contracts.run import RunRecord
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import (
    Observation,
    ReadRequest,
)

from .continuation import _Continuation
from .errors import ErrorCode, KernelError
from .ir_on import IrOnMixin

OUTSIDE_TASK = "OUTSIDE_TASK_DEFINITION"
"""Rejection code of a driver read outside the run's tool set (execution IR ``on``, D6)."""
UNUSABLE_CONNECTION = "CONNECTION_NOT_AVAILABLE"
NO_READ_CONNECTION = "the connection is not available to this run for the capability"
"""The fixed code and message of a driver read on a connection the run cannot use (2c.8c):
the same whatever made it unusable, and never a credential, subject or connection state."""


class _ConnectionRefused(KernelError):
    """`usable` or `resolve` refused a read's connection. Code and message are the original
    ones, so the kernel's own reads (verifier, revalidation) raise exactly as before; only
    `_driver_read` turns it into a rejected read."""


class GatewayMixin(IrOnMixin):
    # ---------------------------------------------------------------- reads
    async def _driver_read(
        self, run: RunRecord, cont: _Continuation, request: ReadRequest
    ) -> Observation:
        """A read the driver asked for. In ``on`` the kernel refuses a capability outside the
        run's tool set before any provider call; the refusal is a rejected read the driver is
        told about (ADR 0022). Verifier and revalidation reads are the kernel's own and go
        straight through `_gateway_read`: a verifier may read a host-only capability.

        A connection the run cannot use (absent, out of scope, inactive, another user's, or
        without a binding for the capability) is refused the same way, in every mode, with one
        fixed message and before any provider call (2c.8c); the driver can recover within its
        budgets, and the run never leaves its turn on an exception."""
        allowed = self._allowed(run, cont)
        if allowed is not None and request.contract_id not in allowed:
            raise KnownNoEffectError(OUTSIDE_TASK, "the capability is not in the run's task")
        try:
            return await self._gateway_read(cont, request, count_budget=True)
        except _ConnectionRefused:
            raise KnownNoEffectError(UNUSABLE_CONNECTION, NO_READ_CONNECTION) from None

    async def _gateway_read(
        self, cont: _Continuation, request: ReadRequest, *, count_budget: bool
    ) -> Observation:
        ctx = cont.ctx
        if count_budget and cont.read_calls >= ctx.budgets.max_read_calls:
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "read call budget exhausted")
        descriptor = self._registry.descriptor(request.contract_id)
        if descriptor.effect is not EffectKind.READ:
            raise KernelError(ErrorCode.INVALID_REQUEST, "write capability requested as a read")
        try:
            self._connections.usable(ctx, request.connection_id)
        except KernelError as exc:
            raise _ConnectionRefused(exc.code, exc.safe_message) from exc
        decision = self._policy.evaluate(ctx, descriptor, request.connection_id)
        if not decision.permitted:
            raise KernelError(ErrorCode.FORBIDDEN, "read not permitted")
        try:
            binding = self._registry.resolve(request.contract_id, request.connection_id)
        except KernelError as exc:
            raise _ConnectionRefused(exc.code, exc.safe_message) from exc
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
