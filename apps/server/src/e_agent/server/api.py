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
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.context import HostContext, Principal, TaskContext
from e_agent.contracts.digest import digest
from e_agent.contracts.events import RunEvent
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.contracts.work import WorkClaim
from e_agent.kernel.approval import ApprovalPresentation
from e_agent.kernel.discovery import (
    SCHEMA_VERSION as DISCOVERY_SCHEMA_VERSION,
)
from e_agent.kernel.discovery import (
    member_connections,
    task_catalog,
)
from e_agent.kernel.errors import ErrorCode, KernelError
from e_agent.kernel.evidence import build_evidence
from e_agent.sdk.store import ConcurrencyConflict, NotFound
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


class SubmitInput(_Body):
    input: str = Field(min_length=1, max_length=4000)
    expected_revision: int = Field(ge=1)


class CreateRunResponse(BaseModel):
    run_id: str
    created: bool


class ActionSummary(BaseModel):
    action_id: str
    contract_id: str
    state: ActionState
    arguments: dict[str, Any]


class TextFrame(BaseModel):
    message_id: str
    stream_id: str
    offset: int
    text: str
    reset: bool


class RunSnapshot(BaseModel):
    run: RunRecord
    latest_sequence: int
    actions: list[ActionSummary]
    pending_approval: ApprovalPresentation | None
    streaming_text: TextFrame | None = None


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


class PublicTextBus:
    """Bounded process memory; never writes public token fragments to the ledger."""

    def __init__(self) -> None:
        self.stream_id = new_id("text_stream")
        self.frames: dict[tuple[str, str], list[TextFrame]] = {}
        self.prefixes: dict[tuple[str, str], str] = {}
        self.messages: dict[tuple[str, str], str] = {}

    async def emit(self, ctx: TaskContext, text: str, *, new_message: bool = False) -> None:
        key = (ctx.tenant_id, ctx.run_id)
        if key not in self.frames and len(self.frames) >= 128:
            oldest = next(iter(self.frames))
            self.frames.pop(oldest)
            self.prefixes.pop(oldest, None)
            self.messages.pop(oldest, None)
        frames = self.frames.setdefault(key, [])
        if new_message or key not in self.messages:
            self.messages[key] = new_id("message")
        prefix = "" if new_message else self.prefixes.get(key, "")
        text = text[: max(0, 32000 - len(prefix))]
        if not text:
            return
        offset = frames[-1].offset + 1 if frames else 1
        frames.append(
            TextFrame(
                message_id=self.messages[key],
                stream_id=self.stream_id,
                offset=offset,
                text=text,
                reset=new_message,
            )
        )
        self.frames[key] = frames[-128:]
        self.prefixes[key] = prefix + text

    def snapshot(self, tenant_id: str, run_id: str) -> TextFrame | None:
        key = (tenant_id, run_id)
        frames = self.frames.get(key, [])
        if not frames:
            return None
        return TextFrame(
            message_id=self.messages[key],
            stream_id=self.stream_id,
            offset=frames[-1].offset,
            text=self.prefixes[key],
            reset=True,
        )

    def after(self, tenant_id: str, run_id: str, offset: int) -> list[TextFrame]:
        frames = self.frames.get((tenant_id, run_id), [])
        if frames and offset < frames[0].offset - 1:
            snapshot = self.snapshot(tenant_id, run_id)
            return [snapshot] if snapshot else []
        return [frame for frame in frames if frame.offset > offset]


class ApiState:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.sessions: dict[str, Session] = {}
        self.text = PublicTextBus()
        runtime.coordinator.set_text_sink(self.text)
        self.tasks: set[asyncio.Task[Any]] = set()
        self.stopping = False

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

        pulse = asyncio.create_task(heartbeat())
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
                if claim.fence > 1 and not untouched:
                    await rt.coordinator.recover_run(claim.tenant_id, claim.run_id)
                elif claim.kind == "start":
                    await rt.coordinator.start_admitted_run(claim.tenant_id, claim.run_id)
                elif claim.kind == "input":
                    await rt.coordinator.continue_input(claim.tenant_id, claim.run_id)
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
            try:
                async with rt.store.work_scope(claim):
                    await self._mark_failed(claim.run_id)
                    await rt.store.finish_work(claim)
            except Exception:
                # Leave the claim for lease expiry and another owner to reconcile.
                return
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)

    async def _mark_failed(self, run_id: str) -> None:
        """Unexpected host error: apply the crash rules, never guess an outcome."""
        rt = self.runtime
        try:
            await rt.coordinator.recover_run(rt.operator.tenant_id, run_id)
        except NotFound:
            return


class MemberConnection(BaseModel):
    """Member-safe connection summary (ADR 0017). No secret or administrative field."""

    connection_id: str
    integration_id: str
    ownership: str
    acting_identity: str | None
    allowed_resources: list[str]
    capabilities: list[str]
    configuration_status: str
    observed_health: Literal["unknown"]
    """Always unknown: rendering a view never probes a provider."""
    revision: int


class MemberConnections(BaseModel):
    schema_version: str
    observed_at: str
    connections: list[MemberConnection]


class TaskTemplate(BaseModel):
    """An admitted task type, with the availability the requester actually has."""

    template_id: str
    title: str
    description: str
    input_intent: Literal["free_text"]
    availability: Literal["available", "unavailable"]
    unavailable_reason: (
        Literal["no_usable_connection", "ambiguous_binding", "no_executor", "no_verifier"] | None
    )
    required_capabilities: list[str]
    bounded_context: str


class TaskCatalog(BaseModel):
    schema_version: str
    observed_at: str
    templates: list[TaskTemplate]


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
        worker = asyncio.create_task(holder["state"].worker())
        holder["state"].tasks.add(worker)
        yield
        state = holder["state"]
        state.stopping = True
        for task in list(state.tasks):
            task.cancel()
        await asyncio.gather(*state.tasks, return_exceptions=True)
        close = getattr(runtime.store, "close", None)
        if close is not None:
            await close()

    app = FastAPI(title="e-agent API", version="1", lifespan=lifespan)

    def state() -> ApiState:
        return holder["state"]

    @app.exception_handler(KernelError)
    async def kernel_error(_: Request, exc: KernelError) -> JSONResponse:
        return _error(exc.code, exc.safe_message)

    @app.exception_handler(ConcurrencyConflict)
    async def concurrency_conflict(_: Request, exc: ConcurrencyConflict) -> JSONResponse:
        return _error(ErrorCode.CONFLICT, "request conflicts with the current run")

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
            "self_approval_allowed": rt.profile.operator.allow_self_approval,
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
        claimed, created = await rt.coordinator.admit_run(
            s.principal,
            body.task,
            rt.scope,
            run_id=run_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            host_context=body.host_context,
        )
        return CreateRunResponse(run_id=claimed, created=created)

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
            streaming_text=state().text.snapshot(s.principal.tenant_id, run_id),
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
        text_cursor = 0
        while not await request.is_disconnected():
            batch = await rt.store.list_events(s.principal.tenant_id, run_id, cursor)
            for event in batch:
                cursor = event.sequence
                yield ServerSentEvent(
                    data=event.model_dump(mode="json"), event="run_event", id=str(event.sequence)
                )
            for frame in state().text.after(s.principal.tenant_id, run_id, text_cursor):
                text_cursor = frame.offset
                yield ServerSentEvent(data=frame.model_dump(mode="json"), event="text_delta")
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
        actor = s.principal.model_dump(mode="json")
        actor["roles"] = sorted(s.principal.roles)
        payload = {**body.model_dump(mode="json"), "actor": actor}
        request_digest = digest(
            {
                "action_id": body.action_id,
                "digest": body.digest,
                "revision": str(body.expected_revision),
            }
        )
        await rt.store.enqueue_work(
            s.principal.tenant_id, run_id, "decide", payload, request_digest
        )
        return Accepted(status="accepted")

    @app.post("/v1/runs/{run_id}/inputs", status_code=202)
    async def submit_input(
        run_id: str,
        body: SubmitInput,
        s: Session = Depends(session),
    ) -> Accepted:
        rt = state().runtime
        run = await rt.store.get_run(s.principal.tenant_id, run_id)
        if run.requester_id != s.principal.principal_id:
            raise KernelError(ErrorCode.FORBIDDEN, "only the requester may answer")
        if run.revision != body.expected_revision or run.state is not RunState.WAITING_INPUT:
            events = await rt.store.list_events(s.principal.tenant_id, run_id)
            if any(
                e.type == "input.received"
                and e.payload.get("expected_revision") == body.expected_revision
                and e.payload.get("input") == body.input
                for e in events
            ):
                return Accepted(status="accepted")
            raise KernelError(ErrorCode.CONFLICT, "input does not match the pending question")
        await rt.coordinator.accept_input(
            s.principal, run_id, body.input, body.expected_revision, enqueue=True
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

    # -- member discovery (ADR 0017): read-only projections of admitted metadata ---
    def _member_context(s: Session) -> TaskContext:
        rt = state().runtime
        return TaskContext(
            run_id="discovery",
            tenant_id=s.principal.tenant_id,
            principal=s.principal,
            resource_scope=rt.scope,
        )

    @app.get("/v1/me/connections")
    async def my_connections(s: Session = Depends(session)) -> MemberConnections:
        rt = state().runtime
        catalog = rt.connections
        projected = (
            member_connections(catalog, rt.registry, _member_context(s))
            if catalog is not None
            else ()
        )
        return MemberConnections(
            schema_version=DISCOVERY_SCHEMA_VERSION,
            observed_at=utc_now().isoformat(),
            connections=[MemberConnection(**vars(c)) for c in projected],
        )

    @app.get("/v1/me/task-catalog")
    async def my_task_catalog(s: Session = Depends(session)) -> TaskCatalog:
        rt = state().runtime
        catalog = rt.connections
        projected = (
            task_catalog(catalog, rt.registry, _member_context(s)) if catalog is not None else ()
        )
        return TaskCatalog(
            schema_version=DISCOVERY_SCHEMA_VERSION,
            observed_at=utc_now().isoformat(),
            templates=[TaskTemplate(**vars(t)) for t in projected],
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
