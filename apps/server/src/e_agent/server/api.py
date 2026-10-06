"""HTTP application API (MVP design §12, ADR 0007).

- Identity comes only from the authenticated session, never from request bodies.
- Local mode: a loopback-only POST /v1/local/session issues an HttpOnly,
  SameSite=Strict cookie plus a CSRF token required on state-changing requests.
- Run work (driver turns, dispatch, verification) runs as background tasks; the
  client follows progress on the SSE stream of durable run events.
- Errors are structured {code, message, correlation_id}; a run of another tenant
  is indistinguishable from a missing run.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from e_agent.contracts.action import ActionState
from e_agent.contracts.approval import ApprovalDecision
from e_agent.contracts.common import new_id
from e_agent.contracts.context import HostContext, Principal
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEvent
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.kernel.approval import ApprovalPresentation
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.evidence import build_evidence
from e_agent.sdk.store import NotFound
from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .bootstrap import Runtime

SESSION_COOKIE = "e_agent_session"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}
STATUS = {
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.FORBIDDEN: 404,  # never reveal existence across scope
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.APPROVAL_STALE: 409,
    ErrorCode.VALIDATION_BLOCKED: 422,
    ErrorCode.BUDGET_EXCEEDED: 429,
    ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
    ErrorCode.ACTION_UNRESOLVED: 409,
    ErrorCode.STARTUP_REJECTED: 503,
}
CSP = (
    "default-src 'self'; img-src 'self' data:; connect-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'"
)


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRun(_Body):
    task: str = Field(min_length=1, max_length=4000)
    host_context: HostContext | None = None  # untrusted hints, resolved or dropped (ADR 0011)


class Decide(_Body):
    action_id: str
    digest: str
    expected_revision: int
    decision: Literal["approved", "rejected"]


class CreateRunResponse(BaseModel):
    run_id: str
    created: bool


class ActionSummary(BaseModel):
    action_id: str
    contract_id: str
    state: ActionState
    arguments: dict[str, Any]


class RunSnapshot(BaseModel):
    run: RunRecord
    latest_sequence: int
    actions: list[ActionSummary]
    pending_approval: ApprovalPresentation | None


class Accepted(BaseModel):
    status: Literal["accepted"]


class StateResponse(BaseModel):
    state: RunState
    unresolved: bool = False


class SessionResponse(BaseModel):
    csrf_token: str
    principal: str
    tenant: str


@dataclass
class Session:
    principal: Principal
    csrf: str


class ApiState:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.sessions: dict[str, Session] = {}
        self.tasks: set[asyncio.Task[Any]] = set()
        self.run_locks: dict[str, asyncio.Lock] = {}

    def spawn(self, run_id: str, work: Callable[[], Awaitable[Any]]) -> None:
        lock = self.run_locks.setdefault(run_id, asyncio.Lock())

        async def guarded() -> None:
            async with lock:
                try:
                    await work()
                except Exception:
                    await self._mark_failed(run_id)

        task = asyncio.create_task(guarded())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _mark_failed(self, run_id: str) -> None:
        """Unexpected host error: apply the crash rules, never guess an outcome."""
        rt = self.runtime
        try:
            await rt.coordinator.recover_run(rt.operator.tenant_id, run_id)
        except NotFound:
            return


def _error(code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS.get(code, 400),
        content={"code": code, "message": message, "correlation_id": new_id("corr")},
    )


def create_app(
    runtime_factory: Callable[[], Awaitable[Runtime]],
    *,
    local_mode: bool = True,
    static_dir: Path | None = None,
) -> FastAPI:
    holder: dict[str, ApiState] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = await runtime_factory()
        await runtime.coordinator.recover()
        holder["state"] = ApiState(runtime)
        yield
        state = holder["state"]
        for task in list(state.tasks):
            task.cancel()
        close = getattr(runtime.store, "close", None)
        if close is not None:
            await close()

    app = FastAPI(title="e-agent API", version="1", lifespan=lifespan)

    def state() -> ApiState:
        return holder["state"]

    @app.exception_handler(KernelError)
    async def kernel_error(_: Request, exc: KernelError) -> JSONResponse:
        return _error(exc.code, exc.safe_message)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound) -> JSONResponse:
        return _error(ErrorCode.NOT_FOUND, "not found")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def session(request: Request, x_csrf_token: str | None = Header(default=None)) -> Session:
        token = request.cookies.get(SESSION_COOKIE)
        found = state().sessions.get(token or "")
        if found is None:
            raise KernelError(ErrorCode.FORBIDDEN, "authentication required")
        if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
            x_csrf_token or "", found.csrf
        ):
            raise KernelError(ErrorCode.FORBIDDEN, "missing or invalid CSRF token")
        return found

    # -- health -------------------------------------------------------------
    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready() -> dict[str, Any]:
        rt = state().runtime
        return {
            "status": "ready",
            "environment": rt.profile.environment,
            "plugins": rt.registry.report.admitted,
            "store": rt.profile.store.kind,
        }

    # -- local session (loopback only, never production auth) ---------------
    @app.post("/v1/local/session")
    async def local_session(request: Request, response: Response) -> SessionResponse:
        client = request.client.host if request.client else ""
        if not local_mode or client not in LOOPBACK:
            raise KernelError(ErrorCode.FORBIDDEN, "local sessions are loopback-only")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        state().sessions[token] = Session(state().runtime.operator, csrf)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, samesite="strict", secure=False, path="/"
        )
        rt = state().runtime
        return SessionResponse(
            csrf_token=csrf, principal=rt.operator.principal_id, tenant=rt.operator.tenant_id
        )

    # -- runs ------------------------------------------------------------------
    @app.post("/v1/runs", status_code=202)
    async def create_run(
        body: CreateRun,
        s: Session = Depends(session),
        idempotency_key: str = Header(min_length=8, max_length=200),
    ) -> CreateRunResponse:
        rt = state().runtime
        request_digest = digest(body.model_dump(mode="json", exclude_none=True))
        run_id = new_id("run")
        claimed, existing_digest = await rt.store.claim_idempotency(
            s.principal.tenant_id, s.principal.principal_id, idempotency_key, request_digest, run_id
        )
        if existing_digest != request_digest:
            raise KernelError(ErrorCode.CONFLICT, "idempotency key reused with another request")
        if claimed == run_id:
            state().spawn(
                run_id,
                lambda: rt.coordinator.start_run(
                    s.principal, body.task, rt.scope, run_id=run_id, host_context=body.host_context
                ),
            )
        return CreateRunResponse(run_id=claimed, created=claimed == run_id)

    @app.get("/v1/runs/{run_id}")
    async def get_run(run_id: str, s: Session = Depends(session)) -> RunSnapshot:
        rt = state().runtime
        run = await rt.store.get_run(s.principal.tenant_id, run_id)
        events = await rt.store.list_events(s.principal.tenant_id, run_id)
        actions = await rt.store.list_actions(s.principal.tenant_id, run_id)
        pending = None
        if run.state is RunState.WAITING_APPROVAL:
            try:
                pending = await rt.coordinator.pending_approval(s.principal.tenant_id, run_id)
            except KernelError:
                pending = None
        return RunSnapshot(
            run=run,
            latest_sequence=events[-1].sequence if events else 0,
            actions=[
                ActionSummary(
                    action_id=a.action_id,
                    contract_id=a.contract_id,
                    state=a.state,
                    arguments=a.arguments,
                )
                for a in actions
            ],
            pending_approval=pending,
        )

    @app.get("/v1/runs/{run_id}/events")
    async def events(
        run_id: str, after_sequence: int = 0, s: Session = Depends(session)
    ) -> list[RunEvent]:
        rt = state().runtime
        await rt.store.get_run(s.principal.tenant_id, run_id)
        events: list[RunEvent] = await rt.store.list_events(
            s.principal.tenant_id, run_id, after_sequence
        )
        return events

    async def visible_run(run_id: str, s: Session = Depends(session)) -> Session:
        """Resolve scope before any streaming starts: absent and foreign look the same."""
        await state().runtime.store.get_run(s.principal.tenant_id, run_id)
        return s

    @app.get("/v1/runs/{run_id}/stream", response_class=EventSourceResponse)
    async def stream(
        run_id: str,
        request: Request,
        s: Session = Depends(visible_run),
        last_event_id: str | None = Header(default=None),
        after_sequence: int = 0,
    ) -> AsyncIterator[ServerSentEvent]:
        """Resume from ``Last-Event-ID`` (automatic reconnect) or ``after_sequence``
        (a new EventSource after a snapshot, which cannot set headers)."""
        rt = state().runtime
        header = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
        cursor = max(header, after_sequence)
        idle = 0
        while not await request.is_disconnected():
            batch = await rt.store.list_events(s.principal.tenant_id, run_id, cursor)
            for event in batch:
                cursor = event.sequence
                yield ServerSentEvent(
                    data=event.model_dump(mode="json"), event="run_event", id=str(event.sequence)
                )
            run = await rt.store.get_run(s.principal.tenant_id, run_id)
            if run.state in TERMINAL_RUN_STATES and not batch:
                yield ServerSentEvent(data={"state": run.state}, event="end")
                return
            idle = 0 if batch else idle + 1
            if idle and idle % 50 == 0:
                yield ServerSentEvent(comment="keep-alive")
            await asyncio.sleep(0.2)

    @app.get("/v1/runs/{run_id}/approvals/pending")
    async def pending(
        run_id: str,
        s: Session = Depends(session),
    ) -> ApprovalPresentation:
        return await state().runtime.coordinator.pending_approval(s.principal.tenant_id, run_id)

    @app.post("/v1/runs/{run_id}/approvals", status_code=202)
    async def decide(run_id: str, body: Decide, s: Session = Depends(session)) -> Accepted:
        rt = state().runtime
        pres = await rt.coordinator.pending_approval(s.principal.tenant_id, run_id)
        if pres.action_id != body.action_id or pres.digest != body.digest:
            raise KernelError(ErrorCode.APPROVAL_STALE, "approval does not match pending action")
        if pres.run_revision != body.expected_revision:
            raise KernelError(ErrorCode.CONFLICT, "run changed; reload before deciding")
        decision = ApprovalDecision(body.decision)
        state().spawn(
            run_id,
            lambda: rt.coordinator.decide(
                actor=s.principal,
                run_id=run_id,
                action_id=body.action_id,
                action_digest=body.digest,
                expected_run_revision=body.expected_revision,
                decision=decision,
            ),
        )
        return Accepted(status="accepted")

    @app.post("/v1/runs/{run_id}/cancel")
    async def cancel(run_id: str, s: Session = Depends(session)) -> StateResponse:
        run = await state().runtime.coordinator.cancel(s.principal, run_id)
        return StateResponse(state=run.state, unresolved=run.state is RunState.NEEDS_RECONCILIATION)

    @app.post("/v1/runs/{run_id}/reconcile")
    async def reconcile(run_id: str, s: Session = Depends(session)) -> StateResponse:
        run = await state().runtime.coordinator.reconcile(s.principal, run_id)
        return StateResponse(state=run.state)

    @app.get("/v1/runs/{run_id}/evidence")
    async def evidence(run_id: str, s: Session = Depends(session)) -> dict[str, Any]:
        rt = state().runtime
        return await build_evidence(
            rt.store,
            s.principal.tenant_id,
            run_id,
            environment=rt.profile.environment,
            versions=rt.versions,
        )

    if static_dir is not None and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")
    return app


def serve(profile_path: str | None, host: str, port: int, static_dir: str | None) -> None:
    import uvicorn

    from .bootstrap import build_runtime
    from .profile import load_profile

    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("local mode binds to loopback only (MVP design §12)")
    profile = load_profile(profile_path)
    app = create_app(
        lambda: build_runtime(profile),
        local_mode=True,
        static_dir=Path(static_dir) if static_dir else None,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")
