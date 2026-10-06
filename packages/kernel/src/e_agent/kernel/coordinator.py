"""Run coordinator: drives the agent, gates every effect, owns approval and dispatch.

The coordinator is the only component that moves actions through the state
machine (MVP design §7-9, ADR 0003). Drivers only propose; validators only
report findings; executors only execute admitted invocations.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from e_agent.contracts.action import ALLOWED_ACTION_TRANSITIONS, ActionRecord, ActionState
from e_agent.contracts.approval import ApprovalDecision, ApprovalRecord
from e_agent.contracts.capability import CapabilityBinding, EffectKind
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.digest import CanonicalizationError
from e_agent.contracts.events import RunEventType
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.outcome import OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.contracts.run import TERMINAL_RUN_STATES, RunRecord, RunState
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import (
    AgentDriver,
    AskClarification,
    DriverInput,
    FinalAnswer,
    Observation,
    PolicyEvaluator,
    ProposeAction,
    ReadRequest,
    RequestReads,
    ValidationInput,
)
from e_agent.sdk.store import DuplicateOperation, EventSpec, RunStore
from pydantic import BaseModel, Field

from .approval import ApprovalPresentation, compute_digest, digest_input, presentation_for
from .connections import ConnectionCatalog
from .errors import ErrorCode, KernelError
from .policy import APPROVER_ROLE
from .registry import PluginRegistry

DEFAULT_APPROVAL_TTL = timedelta(minutes=15)


CONTINUATION_SCHEMA = "kernel-continuation-v1"


class _Continuation(BaseModel):
    """Kernel-side run continuation, persisted through the RunStore at every state
    change so a restarted process can resume (ADR 0003/0004). Contains only
    authorized observations and records; never secrets or model reasoning."""

    ctx: TaskContext
    reads: dict[str, ReadRequest] = Field(default_factory=dict)
    observations: dict[str, Observation] = Field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    turns: int = 0
    read_calls: int = 0
    repairs: int = 0
    writes: int = 0
    pending_action_id: str | None = None
    last_action_id: str | None = None  # repairs link to the action they supersede
    canonical_proposal: dict[str, Any] = Field(default_factory=dict)
    last_validation: ValidationResult | None = None
    approval_requested_at: datetime | None = None


class _GatewayReader:
    """ScopedReader handed to verifiers: authorized, recorded reads only."""

    def __init__(self, coordinator: RunCoordinator, cont: _Continuation, connection_id: str):
        self._coordinator = coordinator
        self._cont = cont
        self._connection_id = connection_id

    async def read(self, contract_id: str, arguments: Mapping[str, Any]) -> Observation:
        request = ReadRequest(
            request_id=new_id("vread"),
            contract_id=contract_id,
            connection_id=self._connection_id,
            arguments=dict(arguments),
        )
        return await self._coordinator._gateway_read(self._cont, request, count_budget=False)


class RunCoordinator:
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
        budgets: Budgets | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._connections = connections
        self._policy = policy
        self._driver = driver
        self._clock = clock
        self._approval_ttl = approval_ttl
        self._budgets = budgets or Budgets()
        self._runs: dict[str, _Continuation] = {}

    # ------------------------------------------------------------------ runs
    async def start_run(
        self, principal: Principal, task: str, resource_scope: frozenset[str]
    ) -> RunRecord:
        run_id = new_id("run")
        ctx = TaskContext(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            principal=principal,
            resource_scope=resource_scope,
            budgets=self._budgets,
        )
        run = RunRecord(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            requester_id=principal.principal_id,
            task=task,
            state=RunState.CREATED,
            revision=1,
            logical_operation_id=new_id("op"),  # host-assigned; survives repairs
            created_at=self._clock(),
        )
        await self._store.create_run(
            run,
            [(RunEventType.RUN_CREATED, {"task": task, "driver": self._driver.driver_id}, None)],
        )
        self._runs[run_id] = _Continuation(ctx=ctx)
        run = await self._set_run_state(run, RunState.RUNNING)
        return await self._drive(run, DriverInput(task=task))

    async def get_run(self, tenant_id: str, run_id: str) -> RunRecord:
        return await self._store.get_run(tenant_id, run_id)

    async def _set_run_state(
        self, run: RunRecord, state: RunState, reason: str | None = None
    ) -> RunRecord:
        events: list[EventSpec] = [
            (
                RunEventType.RUN_STATE_CHANGED,
                {"from": run.state, "to": state, "reason": reason},
                None,
            )
        ]
        if state in TERMINAL_RUN_STATES:
            events.append((RunEventType.RUN_TERMINAL, {"state": state, "reason": reason}, None))
        updated = run.model_copy(
            update={"state": state, "revision": run.revision + 1, "reason": reason}
        )
        await self._persist(run.run_id)
        return await self._store.update_run(updated, run.revision, events)

    async def _load_cont(self, tenant_id: str, run_id: str) -> _Continuation:
        cont = self._runs.get(run_id)
        if cont is not None:
            return cont
        stored = await self._store.load_continuation(tenant_id, run_id)
        if stored is None:
            raise KernelError(ErrorCode.NOT_FOUND, "run has no continuation")
        state, driver_state = stored
        if state.get("schema") != CONTINUATION_SCHEMA:
            raise KernelError(ErrorCode.CONFLICT, "unsupported continuation schema")
        cont = _Continuation.model_validate(state["data"])
        restore = getattr(self._driver, "restore", None)
        if driver_state is not None and restore is not None:
            restore(run_id, driver_state)
        self._runs[run_id] = cont
        return cont

    async def _persist(self, run_id: str) -> None:
        cont = self._runs.get(run_id)
        if cont is None:
            return
        snapshot = getattr(self._driver, "snapshot", None)
        driver_state = snapshot(run_id) if snapshot is not None else None
        await self._store.save_continuation(
            cont.ctx.tenant_id,
            run_id,
            {"schema": CONTINUATION_SCHEMA, "data": cont.model_dump(mode="json")},
            driver_state,
        )

    # ---------------------------------------------------------------- driving
    async def _drive(self, run: RunRecord, step_input: DriverInput) -> RunRecord:
        cont = await self._load_cont(run.tenant_id, run.run_id)
        ctx = cont.ctx
        while True:
            if cont.turns >= ctx.budgets.max_driver_turns:
                return await self._exhausted(run, "driver turns")
            cont.turns += 1
            step = await self._driver.advance(ctx, step_input)

            if isinstance(step, RequestReads):
                for request in step.reads:
                    if cont.read_calls >= ctx.budgets.max_read_calls:
                        return await self._exhausted(run, "read calls")
                    obs = await self._gateway_read(cont, request, count_budget=True)
                    cont.reads[request.request_id] = request
                    cont.observations[request.request_id] = obs
                await self._persist(run.run_id)
                step_input = DriverInput(
                    task=run.task, observations=tuple(cont.observations.values())
                )
                continue

            if isinstance(step, ProposeAction):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                outcome = await self._handle_proposal(run, cont, step.proposal)
                if isinstance(outcome, RunRecord):
                    return outcome
                step_input = outcome
                continue

            if isinstance(step, AskClarification):
                await self._store.update_run(
                    run.model_copy(update={"revision": run.revision + 1}),
                    run.revision,
                    [(RunEventType.INPUT_REQUESTED, {"question": step.question}, None)],
                )
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(run, RunState.WAITING_INPUT)

            if isinstance(step, FinalAnswer):
                run = await self._store.get_run(run.tenant_id, run.run_id)
                run = await self._store.update_run(
                    run.model_copy(update={"revision": run.revision + 1}),
                    run.revision,
                    [(RunEventType.MESSAGE_FINAL, {"text": step.text}, None)],
                )
                if cont.pending_action_id is None:
                    return await self._set_run_state(run, RunState.SUCCEEDED, "answered")
                return run
            raise KernelError(ErrorCode.INVALID_REQUEST, "driver returned an unknown step")

    async def _exhausted(self, run: RunRecord, what: str) -> RunRecord:
        run = await self._store.get_run(run.tenant_id, run.run_id)
        run = await self._store.update_run(
            run.model_copy(update={"revision": run.revision + 1}),
            run.revision,
            [(RunEventType.BUDGET_EXHAUSTED, {"budget": what}, None)],
        )
        return await self._set_run_state(run, RunState.FAILED, f"budget exhausted: {what}")

    # ---------------------------------------------------------------- reads
    async def _gateway_read(
        self, cont: _Continuation, request: ReadRequest, *, count_budget: bool
    ) -> Observation:
        ctx = cont.ctx
        descriptor = self._registry.descriptor(request.contract_id)
        if descriptor.effect is not EffectKind.READ:
            raise KernelError(ErrorCode.INVALID_REQUEST, "write capability requested as a read")
        self._connections.usable(ctx, request.connection_id)
        decision = self._policy.evaluate(ctx, descriptor, request.connection_id)
        if not decision.permitted:
            raise KernelError(ErrorCode.FORBIDDEN, "read not permitted")
        binding = self._registry.resolve(request.contract_id, request.connection_id)
        obs = await self._registry.executor_for(binding).read(ctx, binding, request)
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

    # ------------------------------------------------------------- proposals
    async def _handle_proposal(
        self, run: RunRecord, cont: _Continuation, proposal: ActionProposal
    ) -> RunRecord | DriverInput:
        ctx = cont.ctx
        descriptor = self._registry.descriptor(proposal.contract_id)
        if descriptor.effect is not EffectKind.WRITE:
            raise KernelError(ErrorCode.INVALID_REQUEST, "proposals are for write capabilities")
        if cont.writes >= ctx.budgets.max_admitted_writes:
            return await self._exhausted(run, "admitted writes")
        connection = self._connections.usable(ctx, proposal.connection_id)
        binding = self._registry.resolve(proposal.contract_id, proposal.connection_id)
        decision = self._policy.evaluate(ctx, descriptor, proposal.connection_id)
        validation = await self._validate(ctx, cont, proposal, binding)

        evidence = [cont.observations[r].evidence for r in sorted(cont.observations)]
        canonical = digest_input(
            tenant_id=ctx.tenant_id,
            requester_id=ctx.principal.principal_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id=binding.binding_id,
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            arguments=dict(proposal.arguments),
            expected_effects=proposal.expected_effects,
            evidence=evidence,
            rule_bundle_version=validation.rule_bundle_version,
            policy_version=decision.policy_version,
        )
        try:
            action_digest = compute_digest(canonical)
        except CanonicalizationError as exc:
            validation = ValidationResult(
                status=ValidationStatus.FAIL,
                findings=(
                    Finding(
                        rule_id="KERNEL-ARGS",
                        rule_version="1",
                        status=ValidationStatus.FAIL,
                        message=f"arguments outside the digest profile: {exc}",
                    ),
                ),
                rule_bundle_version=validation.rule_bundle_version,
                validator_id="kernel",
            )
            action_digest = "invalid"

        previous = cont.last_action_id
        action = ActionRecord(
            action_id=new_id("act"),
            tenant_id=ctx.tenant_id,
            run_id=run.run_id,
            logical_operation_id=run.logical_operation_id,
            contract_id=proposal.contract_id,
            binding_id=binding.binding_id,
            connection_id=connection.connection_id,
            connection_version=connection.version,
            credential_subject=connection.credential_subject(),
            arguments=dict(proposal.arguments),
            digest=action_digest,
            state=ActionState.PROPOSED,
            revision=1,
            supersedes_action_id=previous,
        )
        await self._store.put_action(
            action,
            None,
            [
                (
                    RunEventType.PROPOSAL_CREATED,
                    {
                        "contract_id": action.contract_id,
                        "arguments": action.arguments,
                        "supersedes": previous,
                    },
                    action.action_id,
                )
            ],
        )
        cont.last_action_id = action.action_id
        findings_payload = [f.model_dump(mode="json") for f in validation.findings]
        blocked = validation.blocks_write or not decision.permitted
        if blocked:
            action = await self._transition(
                action,
                ActionState.BLOCKED,
                (
                    RunEventType.VALIDATION_COMPLETED,
                    {
                        "status": validation.status,
                        "findings": findings_payload,
                        "policy_reasons": list(decision.reasons),
                    },
                ),
            )
            cont.pending_action_id = None
            if not decision.permitted:
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(run, RunState.FAILED, "policy denied")
            if cont.repairs >= ctx.budgets.max_validation_repairs:
                run = await self._store.get_run(run.tenant_id, run.run_id)
                return await self._set_run_state(run, RunState.FAILED, "validation blocked")
            cont.repairs += 1
            cont.findings = validation.findings
            return DriverInput(
                task=run.task,
                observations=tuple(cont.observations.values()),
                findings=validation.findings,
            )

        action = await self._transition(
            action,
            ActionState.VALIDATED,
            (
                RunEventType.VALIDATION_COMPLETED,
                {"status": validation.status, "findings": findings_payload},
            ),
        )
        cont.pending_action_id = action.action_id
        cont.canonical_proposal = canonical
        cont.last_validation = validation
        cont.approval_requested_at = self._clock()
        action = await self._transition(
            action,
            ActionState.AWAITING_APPROVAL,
            (
                RunEventType.APPROVAL_REQUESTED,
                {
                    "digest": action.digest,
                    "expires_at": (cont.approval_requested_at + self._approval_ttl).isoformat(),
                },
            ),
        )
        run = await self._store.get_run(run.tenant_id, run.run_id)
        return await self._set_run_state(run, RunState.WAITING_APPROVAL)

    async def _validate(
        self,
        ctx: TaskContext,
        cont: _Continuation,
        proposal: ActionProposal,
        binding: CapabilityBinding,
    ) -> ValidationResult:
        validators = self._registry.validators_for(proposal.contract_id)
        if not validators:
            return ValidationResult(
                status=ValidationStatus.UNKNOWN,
                findings=(
                    Finding(
                        rule_id="KERNEL-NO-VALIDATOR",
                        rule_version="1",
                        status=ValidationStatus.UNKNOWN,
                        message="no validator registered for capability",
                    ),
                ),
                rule_bundle_version="none",
                validator_id="kernel",
            )
        item = ValidationInput(proposal=proposal, observations=tuple(cont.observations.values()))
        results: list[ValidationResult] = []
        for validator in validators:
            try:
                results.append(await validator.validate(ctx, item))
            except Exception as exc:  # engine failure blocks the write (MVP §11)
                results.append(
                    ValidationResult(
                        status=ValidationStatus.ERROR,
                        findings=(
                            Finding(
                                rule_id="KERNEL-VALIDATOR-ERROR",
                                rule_version="1",
                                status=ValidationStatus.ERROR,
                                message=type(exc).__name__,
                            ),
                        ),
                        rule_bundle_version="error",
                        validator_id=validator.validator_id,
                    )
                )
        order = [ValidationStatus.ERROR, ValidationStatus.FAIL, ValidationStatus.UNKNOWN]
        status = next(
            (s for s in order if any(r.status is s for r in results)), ValidationStatus.PASS
        )
        return ValidationResult(
            status=status,
            findings=tuple(f for r in results for f in r.findings),
            rule_bundle_version="+".join(sorted(r.rule_bundle_version for r in results)),
            validator_id="+".join(sorted(r.validator_id for r in results)),
        )

    async def _transition(
        self,
        action: ActionRecord,
        to: ActionState,
        event: tuple[RunEventType, dict[str, Any]] | None = None,
    ) -> ActionRecord:
        if to not in ALLOWED_ACTION_TRANSITIONS[action.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal transition {action.state}->{to}")
        updated = action.model_copy(update={"state": to, "revision": action.revision + 1})
        events: list[EventSpec] = []
        if event is not None:
            events.append((event[0], event[1], action.action_id))
        return await self._store.put_action(updated, action.revision, events)

    # ------------------------------------------------------------- approvals
    async def pending_approval(self, tenant_id: str, run_id: str) -> ApprovalPresentation:
        run = await self._store.get_run(tenant_id, run_id)
        cont = await self._load_cont(run.tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL or cont.pending_action_id is None:
            raise KernelError(ErrorCode.NOT_FOUND, "no pending approval")
        action = await self._store.get_action(tenant_id, cont.pending_action_id)
        assert cont.approval_requested_at is not None
        return presentation_for(
            action,
            run_revision=run.revision,
            canonical_proposal=cont.canonical_proposal,
            findings=cont.last_validation.findings if cont.last_validation else (),
            expires_at=cont.approval_requested_at + self._approval_ttl,
        )

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
        if run.revision != expected_run_revision:
            raise KernelError(ErrorCode.CONFLICT, "run changed; reload before deciding")
        cont = await self._load_cont(run.tenant_id, run_id)
        if run.state is not RunState.WAITING_APPROVAL or cont.pending_action_id != action_id:
            raise KernelError(ErrorCode.CONFLICT, "action is not awaiting approval")
        action = await self._store.get_action(actor.tenant_id, action_id)
        if action.digest != action_digest:
            raise KernelError(ErrorCode.APPROVAL_STALE, "digest does not match pending action")
        now = self._clock()
        assert cont.approval_requested_at is not None
        if now > cont.approval_requested_at + self._approval_ttl:
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.APPROVAL_DECIDED, {"decision": "expired"}),
            )
            cont.pending_action_id = None
            run = await self._store.get_run(actor.tenant_id, run_id)
            await self._set_run_state(run, RunState.FAILED, "approval expired")
            raise KernelError(ErrorCode.APPROVAL_STALE, "approval window expired")

        record = ApprovalRecord(
            approval_id=new_id("apr"),
            tenant_id=actor.tenant_id,
            run_id=run_id,
            action_id=action_id,
            action_digest=action_digest,
            actor_id=actor.principal_id,
            decision=decision,
            policy_version=self._policy.evaluate(
                cont.ctx, self._registry.descriptor(action.contract_id), action.connection_id
            ).policy_version,
            issued_at=now,
            expires_at=now + self._approval_ttl,
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
        )
        if decision is ApprovalDecision.REJECTED:
            await self._transition(action, ActionState.BLOCKED)
            cont.pending_action_id = None
            run = await self._store.get_run(actor.tenant_id, run_id)
            return await self._set_run_state(run, RunState.FAILED, "rejected by approver")
        action = await self._transition(action, ActionState.APPROVED)
        return await self._dispatch(cont, action, record)

    # -------------------------------------------------------------- dispatch
    async def _dispatch(
        self, cont: _Continuation, action: ActionRecord, approval: ApprovalRecord
    ) -> RunRecord:
        ctx = cont.ctx
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        stale_reason = await self._staleness(cont, action)
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)  # reads advanced revision
        if stale_reason is None and self._clock() > approval.expires_at:
            stale_reason = "approval expired before dispatch"
        if stale_reason is not None:
            await self._transition(
                action,
                ActionState.BLOCKED,
                (RunEventType.VALIDATION_COMPLETED, {"status": "STALE", "reason": stale_reason}),
            )
            cont.pending_action_id = None
            if cont.repairs >= ctx.budgets.max_validation_repairs:
                return await self._set_run_state(run, RunState.FAILED, stale_reason)
            cont.repairs += 1
            run = await self._set_run_state(run, RunState.RUNNING, stale_reason)
            stale = Finding(
                rule_id="KERNEL-STALE",
                rule_version="1",
                status=ValidationStatus.FAIL,
                message=stale_reason,
            )
            return await self._drive(
                run,
                DriverInput(
                    task=run.task, observations=tuple(cont.observations.values()), findings=(stale,)
                ),
            )

        reserved = action.model_copy(
            update={"state": ActionState.RESERVED, "revision": action.revision + 1}
        )
        try:
            action = await self._store.reserve_operation(
                reserved,
                action.revision,
                [
                    (
                        RunEventType.ACTION_RESERVED,
                        {"logical_operation_id": action.logical_operation_id},
                        action.action_id,
                    )
                ],
            )
        except DuplicateOperation:
            await self._transition(action, ActionState.BLOCKED)
            return await self._set_run_state(run, RunState.FAILED, "operation already reserved")
        cont.writes += 1
        action = await self._transition(
            action, ActionState.DISPATCHING, (RunEventType.ACTION_DISPATCHING, {"attempt": 1})
        )
        binding = self._registry.resolve(action.contract_id, action.connection_id)
        executor = self._registry.executor_for(binding)
        started = self._clock()
        try:
            async with self._store.writer_lock(ctx.tenant_id, action.connection_id):
                receipt = await executor.execute(ctx, binding, action, 1)
        except KnownNoEffectError as exc:
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                attempt=1,
                status=ReceiptStatus.FAILED,
                sanitized_error=exc.code,
                started_at=started,
                finished_at=self._clock(),
            )
        except Exception as exc:  # ambiguous: the provider may have committed
            receipt = ExecutionReceipt(
                action_id=action.action_id,
                attempt=1,
                status=ReceiptStatus.UNKNOWN,
                sanitized_error=type(exc).__name__,
                started_at=started,
                finished_at=self._clock(),
            )
        return await self._apply_receipt(cont, action, receipt)

    async def _staleness(self, cont: _Continuation, action: ActionRecord) -> str | None:
        ctx = cont.ctx
        try:
            connection = self._connections.usable(ctx, action.connection_id)
        except KernelError as exc:
            return f"connection unavailable: {exc.code}"
        if connection.version != action.connection_version:
            return "connection changed since approval"
        descriptor = self._registry.descriptor(action.contract_id)
        if not self._policy.evaluate(ctx, descriptor, action.connection_id).permitted:
            return "policy no longer permits the action"
        for request_id, request in cont.reads.items():
            fresh = await self._gateway_read(cont, request, count_budget=False)
            before: EvidenceRef = cont.observations[request_id].evidence
            if fresh.evidence.revision != before.revision:
                cont.observations[request_id] = fresh
                return f"material source changed: {request.contract_id}"
        return None

    async def _apply_receipt(
        self, cont: _Continuation, action: ActionRecord, receipt: ExecutionReceipt
    ) -> RunRecord:
        ctx = cont.ctx
        target = {
            ReceiptStatus.COMMITTED: ActionState.COMMITTED,
            ReceiptStatus.FAILED: ActionState.FAILED,
            ReceiptStatus.UNKNOWN: ActionState.UNKNOWN,
        }[receipt.status]
        if target not in ALLOWED_ACTION_TRANSITIONS[action.state]:
            raise KernelError(ErrorCode.CONFLICT, f"illegal transition {action.state}->{target}")
        event_type = (
            RunEventType.ACTION_UNKNOWN
            if target is ActionState.UNKNOWN
            else RunEventType.ACTION_RECEIPT_RECORDED
        )
        action = await self._store.record_receipt(
            receipt,
            action.model_copy(update={"state": target, "revision": action.revision + 1}),
            action.revision,
            [(event_type, receipt.model_dump(mode="json"), action.action_id)],
        )
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if target is ActionState.UNKNOWN:
            return await self._set_run_state(
                run,
                RunState.NEEDS_RECONCILIATION,
                "write outcome unknown; reconcile before any retry",
            )
        if target is ActionState.FAILED:
            cont.pending_action_id = None
            return await self._set_run_state(run, RunState.FAILED, "provider rejected the write")
        run = await self._set_run_state(run, RunState.VERIFYING)
        return await self._verify(cont, action, receipt)

    async def _verify(
        self, cont: _Continuation, action: ActionRecord, receipt: ExecutionReceipt
    ) -> RunRecord:
        ctx = cont.ctx
        verifier = self._registry.verifier_for(action.contract_id)
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if verifier is None:
            return await self._set_run_state(run, RunState.VERIFYING, "no verifier registered")
        reader = _GatewayReader(self, cont, action.connection_id)
        try:
            report = await verifier.verify(ctx, action, receipt, reader)
        except Exception as exc:  # verification unavailable: keep unresolved, never retry write
            report = OutcomeReport(
                run_id=ctx.run_id,
                action_id=action.action_id,
                status=OutcomeStatus.UNKNOWN,
                checks=(),
                verifier_id=verifier.verifier_id,
                verifier_version="?",
                reported_at=self._clock(),
            )
            await self._store.record_outcome(
                ctx.tenant_id,
                report,
                None,
                None,
                [
                    (
                        RunEventType.OUTCOME_REPORTED,
                        {"status": "UNKNOWN", "error": type(exc).__name__},
                        action.action_id,
                    )
                ],
            )
            run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
            return await self._set_run_state(run, RunState.VERIFYING, "verification unavailable")
        target = (
            ActionState.VERIFIED
            if report.status is OutcomeStatus.VERIFIED
            else ActionState.VERIFICATION_FAILED
        )
        if report.status is OutcomeStatus.UNKNOWN:
            await self._store.record_outcome(
                ctx.tenant_id,
                report,
                None,
                None,
                [(RunEventType.OUTCOME_REPORTED, report.model_dump(mode="json"), action.action_id)],
            )
            run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
            return await self._set_run_state(run, RunState.VERIFYING, "verification inconclusive")
        current = await self._store.get_action(ctx.tenant_id, action.action_id)
        await self._store.record_outcome(
            ctx.tenant_id,
            report,
            current.model_copy(update={"state": target, "revision": current.revision + 1}),
            current.revision,
            [(RunEventType.OUTCOME_REPORTED, report.model_dump(mode="json"), action.action_id)],
        )
        cont.pending_action_id = None
        run = await self._store.get_run(ctx.tenant_id, ctx.run_id)
        if target is ActionState.VERIFICATION_FAILED:
            return await self._set_run_state(run, RunState.FAILED, "outcome verification failed")
        final = await self._driver.advance(
            ctx,
            DriverInput(
                task=run.task,
                observations=tuple(cont.observations.values()),
                action_result={"status": "VERIFIED", "external_refs": list(receipt.external_refs)},
            ),
        )
        if isinstance(final, FinalAnswer):
            run = await self._store.update_run(
                run.model_copy(update={"revision": run.revision + 1}),
                run.revision,
                [(RunEventType.MESSAGE_FINAL, {"text": final.text}, None)],
            )
        return await self._set_run_state(run, RunState.SUCCEEDED, "outcome verified")

    # --------------------------------------------------------- reconciliation
    async def reconcile(self, operator: Principal, run_id: str) -> RunRecord:
        """Read-only reconciliation of UNKNOWN actions. Never re-sends a write."""
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
                run, RunState.NEEDS_RECONCILIATION, "cancel requested; effect must be reconciled"
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
        return await self._set_run_state(run, RunState.CANCELLED, "cancelled before dispatch")

    # --------------------------------------------------------------- recovery
    async def recover(self) -> list[RunRecord]:
        """Startup recovery (MVP design §9 crash rules). Never sends a write.

        - DISPATCHING: the call may have executed -> UNKNOWN, reconcile later.
        - APPROVED/RESERVED without dispatch: blocked; a new approval is required.
        - COMMITTED while VERIFYING: re-run the independent read-back.
        - RUNNING with no pending effect: the driver turn was lost -> FAILED.
        """
        recovered: list[RunRecord] = []
        for run in await self._store.list_unfinished_runs():
            actions = await self._store.list_actions(run.tenant_id, run.run_id)
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
                recovered.append(await self._apply_receipt(cont, action, receipt))
            elif undispatched:
                for action in undispatched:
                    await self._transition(action, ActionState.BLOCKED)
                if cont is not None:
                    cont.pending_action_id = None
                run = await self._store.get_run(run.tenant_id, run.run_id)
                recovered.append(
                    await self._set_run_state(
                        run, RunState.FAILED, "interrupted before dispatch; approve a new run"
                    )
                )
            elif committed and cont is not None and run.state is RunState.VERIFYING:
                receipts = await self._store.list_receipts(run.tenant_id, committed[0].action_id)
                recovered.append(await self._verify(cont, committed[0], receipts[-1]))
            elif run.state in {RunState.RUNNING, RunState.CREATED}:
                recovered.append(
                    await self._set_run_state(
                        run, RunState.FAILED, "interrupted during driver turn"
                    )
                )
        return recovered
