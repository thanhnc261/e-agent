"""Run coordinator: drives the agent, gates every effect, owns approval and dispatch.

The coordinator is the only component that moves actions through the state
machine (MVP design §7-9, ADR 0003). Drivers only propose; validators only
report findings; executors only execute admitted invocations.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from e_agent.contracts.action import ActionState
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.context import Budgets, HostContext, Principal, TaskContext
from e_agent.contracts.context_pack import ContextLayer
from e_agent.contracts.conversation import (
    CarriedRun,
    Conversation,
    ConversationList,
    ConversationSnapshot,
    MessageRoute,
    ReplyTo,
    RouteKind,
)
from e_agent.contracts.events import RunEventType
from e_agent.contracts.features import FeatureMode, Features, MemberFeatures
from e_agent.contracts.run import (
    ReasonCode,
    RunRecord,
    RunState,
)
from e_agent.sdk.auth import CredentialVersionProvider
from e_agent.sdk.ports import (
    AgentDriver,
    DriverInput,
    PolicyEvaluator,
    SafeTextSink,
)
from e_agent.sdk.store import (
    ConcurrencyConflict,
    ConversationStore,
    EventSpec,
    NotFound,
    RunStore,
)

from .approval_flow import ApprovalFlowMixin
from .carried import (
    MAX_CARRIED_RUNS,
    AnswerDeclarations,
    ComparedLayer,
    answer_declarations,
    carried_digest,
    carry,
    compared_payload,
)
from .connections import ConnectionCatalog
from .context import _Turns, context_route
from .context_on import ON_POLICY
from .continuation import CONTINUATION_SCHEMA as CONTINUATION_SCHEMA
from .continuation import LOG as LOG
from .continuation import _Continuation as _Continuation
from .continuation import _GatewayReader as _GatewayReader
from .conversation import (
    CONVERSATIONS_OFF,
    KEY_REUSED,
    NOT_FOUND_MESSAGE,
    WAIT_FOR_RUN,
    ConversationFlow,
    ConversationStepFailed,
    failure_code,
    message_digest,
    shadow_failed_event,
)
from .dispatch import DispatchMixin
from .errors import ErrorCode, KernelError
from .features import LOCAL_ROUTE, FeaturesMixin, fallback_event
from .gateway import GatewayMixin
from .ir_on import merged_budgets
from .plan_flow import PlanFlowMixin
from .reconstruct import run_created_keys
from .recovery import RecoveryMixin
from .registry import PluginRegistry
from .run_loop import RunLoopMixin
from .transitions import TransitionsMixin
from .verification import VerificationMixin

DEFAULT_APPROVAL_TTL = timedelta(minutes=15)


class RunCoordinator(
    TransitionsMixin,
    RunLoopMixin,
    GatewayMixin,
    PlanFlowMixin,
    ApprovalFlowMixin,
    DispatchMixin,
    VerificationMixin,
    RecoveryMixin,
    FeaturesMixin,
):
    def __init__(
        self,
        *,
        store: RunStore,
        registry: PluginRegistry,
        connections: ConnectionCatalog,
        policy: PolicyEvaluator,
        driver: AgentDriver,
        clock: Callable[[], datetime] = utc_now,
        approval_ttl: timedelta = DEFAULT_APPROVAL_TTL,
        allow_self_approval: bool = False,
        budgets: Budgets | None = None,
        credentials: CredentialVersionProvider | None = None,
        features: Features | None = None,
        route: Mapping[str, Any] | None = None,
    ) -> None:
        """``route`` is the model route's boundary facts as plain values (ADR 0030:
        ``data_boundary``, ``data_boundary_basis``, ``data_processing_declared``), which the
        per-call route check reads (ADR 0032 §9). Bootstrap passes the profile's; without
        it the route is ``local``, as the scripted driver's is."""
        self._store = store
        self._registry = registry
        self._connections = connections
        self._policy = policy
        self._credentials = credentials
        self._driver = driver
        self._clock = clock
        self._approval_ttl = approval_ttl
        self._allow_self_approval = allow_self_approval
        self._budgets = budgets or Budgets()
        self._features = features or Features()  # profile toggles (ADR 0027)
        self._route = dict(LOCAL_ROUTE if route is None else route)
        self._runs: dict[str, _Continuation] = {}
        self._active_calls: dict[str, asyncio.Task[Any]] = {}

    # ------------------------------------------------------------------ runs
    def _prepare_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str | None = None,
        host_context: HostContext | None = None,
        task_kind: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[RunRecord, _Continuation, list[EventSpec]]:
        run_id = run_id or new_id("run")
        run = RunRecord(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            requester_id=principal.principal_id,
            task=task,
            state=RunState.CREATED,
            revision=1,
            logical_operation_id=new_id("op"),  # host-assigned; survives repairs
            created_at=self._clock(),
            conversation_id=conversation_id,  # linked before `run_created_keys` (ADR 0023 §2)
        )
        run, admitted = self._admit_task(run, task_kind)  # execution IR (ADR 0027, ADR 0028)
        # `on` only: the admitted definition narrows the budgets (D7) and is snapshotted into
        # the continuation, which the run uses for its whole life (Codex C-1).
        definition = self._run_task(run) if self._ir_on else None
        ctx = TaskContext(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            principal=principal,
            resource_scope=resource_scope,
            budgets=self._budgets
            if definition is None
            else merged_budgets(self._budgets, definition),
        )
        created: dict[str, Any] = {
            "task": task,
            "driver": self._driver.driver_id,
            **run_created_keys(run),  # ADR 0031 §3, from the run as `_admit_task` linked it
        }
        if host_context is not None:
            resolved, dropped = self._connections.resolve_hints(ctx, host_context.resource_hints)
            # Recorded as untrusted context; selection text is never persisted.
            created["host_context"] = {
                "host_kind": host_context.host_kind,
                "page_url_origin": host_context.page_url_origin,
                "locale": host_context.locale,
                "resolved_hints": [h.model_dump() for h in resolved],
                "dropped_hints": dropped,
            }
        cont = _Continuation(
            ctx=ctx,
            surface_digest=self._registry.surface_digest(),
            task=definition,
            modes=self._pin_modes(),  # ADR 0032 §8: None when every Phase 3 mode is off
        )
        return run, cont, [(RunEventType.RUN_CREATED, created, None), *admitted]

    async def start_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str | None = None,
        host_context: HostContext | None = None,
        task_kind: str | None = None,
    ) -> RunRecord:
        """``task_kind`` names the run's task definition (D8, ADR 0028); in Phase 2 only the
        CLI passes it. ``off`` ignores it, and the run record is today's."""
        run, cont, events = self._prepare_run(
            principal,
            task,
            resource_scope,
            run_id=run_id,
            host_context=host_context,
            task_kind=task_kind,
        )
        await self._store.create_run(run, events)
        self._runs[run.run_id] = cont
        run = await self._set_run_state(run, RunState.RUNNING)
        return await self._drive(run, DriverInput(task=task))

    async def admit_run(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str,
        idempotency_key: str,
        request_digest: str,
        host_context: HostContext | None = None,
        task_kind: str | None = None,
        recorded: Sequence[EventSpec] = (),
    ) -> tuple[str, bool]:
        """``task_kind`` as in `start_run`; the API passes none in Phase 2 (D8).
        ``recorded`` is what a ``conversations: shadow`` fallback records in the admission
        (ADR 0023 §9); the API passes none."""
        run, cont, events = self._prepare_run(
            principal,
            task,
            resource_scope,
            run_id=run_id,
            host_context=host_context,
            task_kind=task_kind,
        )
        events.extend(recorded)
        claimed, previous_digest = await self._store.create_run_idempotent(
            run,
            events,
            {"schema": CONTINUATION_SCHEMA, "data": cont.model_dump(mode="json")},
            principal.principal_id,
            idempotency_key,
            request_digest,
        )
        if previous_digest != request_digest:
            raise KernelError(ErrorCode.CONFLICT, "idempotency key reused with another request")
        return claimed, claimed == run_id

    async def _admit_run_in_conversation(
        self,
        principal: Principal,
        task: str,
        resource_scope: frozenset[str],
        *,
        run_id: str,
        conversation_id: str,
        conversation_revision: int,
        idempotency_key: str,
        request_digest: str,
        host_context: HostContext | None = None,
    ) -> tuple[str, bool]:
        """`admit_run` for a run of ``conversation_id``, at the revision the flow read
        (ADR 0023 §3). A moved revision or an active run is ``CONFLICT`` with the fixed hint
        (`ConversationStepFailed`, on which ``shadow`` falls back). Private: only
        `ConversationFlow` calls it, after its ownership check (review B1-7)."""
        store = self._conversation_store()
        run, cont, events = self._prepare_run(
            principal,
            task,
            resource_scope,
            run_id=run_id,
            host_context=host_context,
            conversation_id=conversation_id,
        )
        mode = self._run_modes(cont).conversations  # the pin (ADR 0023 §9)
        if mode is FeatureMode.ON:
            events.extend(await self._carry_into(cont, principal, conversation_id))
        elif mode is FeatureMode.SHADOW:  # compared, never carried: `cont.carried` stays ()
            events.extend(await self._compare_into(principal, conversation_id, run_id))
        try:
            claimed, previous_digest = await store.create_run_in_conversation(
                run,
                events,
                {"schema": CONTINUATION_SCHEMA, "data": cont.model_dump(mode="json")},
                principal.principal_id,
                idempotency_key,
                request_digest,
                conversation_revision,
            )
        except ConcurrencyConflict:
            raise ConversationStepFailed(ErrorCode.CONFLICT, WAIT_FOR_RUN) from None
        except NotFound:
            raise ConversationStepFailed(ErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE) from None
        if previous_digest != request_digest:
            raise KernelError(ErrorCode.CONFLICT, KEY_REUSED)
        return claimed, claimed == run_id

    async def _carry_into(
        self, cont: _Continuation, principal: Principal, conversation_id: str
    ) -> list[EventSpec]:
        """Build the admitted run's carried items into ``cont.carried`` and return the event
        that records them, in the admission transaction (ADR 0023 §6, §9). Any failure is
        ``feature.fallback`` with ``CONVERSATION_CONTEXT_FAILED``: the run stays linked and
        starts without carried items, before it can reserve anything (ruling 3)."""
        try:
            carried = await self._carried_for(principal, conversation_id, cont.ctx.run_id)
        except Exception:  # no exception text reaches an event (PR-25, PR-28)
            cont.carried = ()
            return [fallback_event("conversations", ReasonCode.CONVERSATION_CONTEXT_FAILED)]
        cont.carried = carried
        if not carried:
            return []
        payload = {
            "conversation_id": conversation_id,
            "carried_run_ids": [c.run_id for c in carried],
            "carried_digest": carried_digest(carried),
        }
        return [(RunEventType.CONVERSATION_CONTEXT_CARRIED, payload, None)]

    async def _compare_into(
        self, principal: Principal, conversation_id: str, run_id: str
    ) -> list[EventSpec]:
        """``shadow``: the carried items and the ``recent_turns`` layer ``on`` would give this
        run's first pack, under the route's class rule and the layer budget, as
        ``conversation.compared`` in the admission transaction (ADR 0023 §9, §11). The pack's
        second fit, against ``max_input_tokens``, depends on that turn's evidence, unknown at
        admission: the layer is the pack's whenever that fit drops no carried run. Nothing
        reaches the driver.
        Any failure is ``conversation.shadow_failed`` with stage ``carry`` and changes
        nothing else. No item, no event, for the conversation's first run."""
        try:
            carried = await self._carried_for(principal, conversation_id, run_id)
            if not carried:
                return []
            turns = _Turns(
                carried,
                ON_POLICY.class_rules[context_route(self._route)],
                self._registry.data_classes,
            )
            budget = ON_POLICY.layer_budgets[ContextLayer.RECENT_TURNS]
            turns.fit(lambda tokens: tokens <= budget)
            layer = ComparedLayer(text=turns.text, tokens=turns.tokens, drops=turns.drops)
            payload = compared_payload(conversation_id, RouteKind.START, carried, layer)
        except Exception as error:  # no exception text reaches an event (PR-25, PR-28)
            return [shadow_failed_event("carry", failure_code(error))]
        return [(RunEventType.CONVERSATION_COMPARED, payload, None)]

    async def _carried_for(
        self, principal: Principal, conversation_id: str, run_id: str
    ) -> tuple[CarriedRun, ...]:
        """The earlier runs' records, read once at admission, and `carry` over them: the
        store's listing order without the admitted run, never sorted by time (ruling R2).
        No earlier run carries nothing."""
        tenant = principal.tenant_id
        listed = await self._conversation_store().list_conversation_runs(
            tenant, principal.principal_id, conversation_id
        )
        runs = [r for r in listed if r.run_id != run_id][-MAX_CARRIED_RUNS:]
        if not runs:
            return ()
        events, actions, evidence = {}, {}, {}
        declarations: dict[str, AnswerDeclarations] = {}
        for run in runs:
            events[run.run_id] = await self._store.list_events(tenant, run.run_id)
            actions[run.run_id] = await self._store.list_actions(tenant, run.run_id)
            stored, _ = await self._read_cont(tenant, run.run_id)
            evidence[run.run_id] = {
                o.evidence.evidence_id: o.evidence for o in stored.observations.values()
            }
            for action in actions[run.run_id]:
                cap = self._registry.capabilities.get(action.contract_id)
                verified = action.state is ActionState.VERIFIED
                if verified and cap is not None and cap.effect is EffectKind.ANSWER:
                    document = self._registry.schema_document(cap.contract_id)
                    declarations[cap.contract_id] = answer_declarations(cap, document)
        return carry(runs, events, actions, evidence, declarations)

    # --------------------------------------------------------- conversations
    def _conversation_store(self) -> ConversationStore:
        if not isinstance(self._store, ConversationStore):
            raise KernelError(ErrorCode.DEPENDENCY_UNAVAILABLE, "no conversation store")
        return self._store

    def _conversation_flow(self) -> ConversationFlow:
        """Built per call, so it always reaches this coordinator's current methods. Routing
        follows the profile's ``conversations`` toggle: no run, and so no pin, exists yet.
        In ``off`` every conversation call is ``NOT_FOUND`` before any store read (§9)."""
        if self._features.conversations is FeatureMode.OFF:
            raise KernelError(ErrorCode.NOT_FOUND, CONVERSATIONS_OFF)
        return ConversationFlow(
            self._conversation_store(),
            self._clock,
            mode=self._features.conversations,
            admit=self._admit_run_in_conversation,
            admit_unlinked=self.admit_run,
            accept=self.accept_input,
            replayed=self.input_replayed,
            run_of=self._store.get_run,
        )

    def member_features(self) -> MemberFeatures:
        """What a member may learn of the modes, in every mode (ADR 0023 §10)."""
        return MemberFeatures(conversations=self._features.conversations)

    async def create_conversation(self, principal: Principal) -> Conversation:
        return await self._conversation_flow().create_conversation(principal)

    async def list_conversations(
        self, principal: Principal, *, after: str | None, limit: int
    ) -> ConversationList:
        return await self._conversation_flow().list_conversations(
            principal, after=after, limit=limit
        )

    async def get_conversation(
        self, principal: Principal, conversation_id: str
    ) -> ConversationSnapshot:
        return await self._conversation_flow().get_conversation(principal, conversation_id)

    async def post_message(
        self,
        principal: Principal,
        conversation_id: str,
        text: str,
        *,
        reply_to: ReplyTo | None,
        host_context: HostContext | None,
        idempotency_key: str,
        resource_scope: frozenset[str],
        request_digest: str | None = None,
    ) -> tuple[MessageRoute, str]:
        """Route one message (ADR 0023 §4): the route and the run id. ``conversation_id``
        comes from the route path and the owner from ``principal``, never from the body.
        ``request_digest`` defaults to `message_digest` of the message, which the API uses."""
        flow = self._conversation_flow()
        if request_digest is None:
            request_digest = message_digest(conversation_id, text, reply_to, host_context)
        return await flow.post_message(
            principal,
            conversation_id,
            text,
            reply_to=reply_to,
            host_context=host_context,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            resource_scope=resource_scope,
        )

    async def start_admitted_run(self, tenant_id: str, run_id: str) -> RunRecord:
        run = await self._store.get_run(tenant_id, run_id)
        if run.state is not RunState.CREATED:
            raise KernelError(ErrorCode.CONFLICT, "run has already started")
        await self._load_cont(tenant_id, run_id)
        run = await self._set_run_state(run, RunState.RUNNING)
        return await self._drive(run, DriverInput(task=run.task))

    def set_text_sink(self, sink: SafeTextSink) -> None:
        attach = getattr(self._driver, "set_text_sink", None)
        if attach is not None:
            attach(sink)

    def release_continuation(self, run_id: str) -> None:
        """Discard a worker's cached checkpoint before a new host claim loads it."""
        self._runs.pop(run_id, None)

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord:
        return await self._store.get_run(tenant_id, run_id)
