"""A tiny NON-ERP fixture domain ("notes") used to prove the kernel is domain-neutral.

Nothing here imports a plugin (e_agent.plugins.*): the kernel must run its full lifecycle with only
this domain installed (MVP design §13, domain neutrality gate).
"""

from __future__ import annotations

import importlib
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from e_agent.contracts.action import ActionRecord
from e_agent.contracts.capability import (
    CapabilityBinding,
    CapabilityDescriptor,
    EffectKind,
    Idempotency,
    Reversibility,
    Risk,
)
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.features import Features
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionPlan, ActionProposal, LineageRef, PlannedStep
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.contracts.task import AcceptanceSpec, RequiredEffect, TaskDefinition
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.kernel.policy import DefaultPolicy
from e_agent.kernel.registry import PluginRegistry
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.manifest import BindingTemplate, TaskDeclaration
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    Observation,
    PluginContribution,
    ProposeAction,
    ProposePlan,
    ReadRequest,
    RequestReads,
    ScopedReader,
    ValidationInput,
)

READ = CapabilityDescriptor(
    contract_id="notes.note.read.v1",
    effect=EffectKind.READ,
    input_schema_id="q",
    output_schema_id="n",
)
# The notes domain declares its effects explicitly (ADR 0029, DR-08).
CREATE = CapabilityDescriptor(
    contract_id="notes.note.create.v1",
    effect=EffectKind.WRITE,
    input_schema_id="c",
    output_schema_id="r",
    risk=Risk.WRITE_LOW,
    reversibility=Reversibility.IRREVERSIBLE,
)
BINDINGS = (
    BindingTemplate(binding_id="notes-mem.read", contract_id=READ.contract_id),
    # NotesBackend keeps one note per logical operation id.
    BindingTemplate(
        binding_id="notes-mem.create",
        contract_id=CREATE.contract_id,
        idempotency=Idempotency.PROVIDER_KEY,
    ),
)
# The notes domain's task definition: the core is tested without ERP (ADR 0028, DR-08).
NOTES_TASK = TaskDefinition(
    task_id="standup-note",
    version="1",
    title="Write a standup note",
    goal_template="write standup note",
    capabilities=(READ.contract_id, CREATE.contract_id),
    acceptance=AcceptanceSpec(required_effects=(RequiredEffect(contract_id=CREATE.contract_id),)),
)
TENANT = "tenant-a"
CONN = "conn-notes"

# -- the two-step notes plan (Task 2c.7, ADR 0025): genericity without ERP -----------------
PIN = CapabilityDescriptor(
    contract_id="notes.note.pin.v1",
    effect=EffectKind.WRITE,
    input_schema_id="p",
    output_schema_id="r",
    risk=Risk.WRITE_HIGH,
    reversibility=Reversibility.COMPENSABLE,
    compensating_contract_id="notes.note.unpin.v1",
)
"""An opt-in second write, so a plan can mix risks (`make_kernel(with_pin=True)`)."""
PIN_BINDING = BindingTemplate(binding_id="notes-mem.pin", contract_id=PIN.contract_id)
NOTE_INPUT = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "parent": {"type": "string"}},
    "required": ["text"],
}
"""The create input schema the two-step plan needs: lineage types a placeholder by it."""
PLAN_BUDGETS = Budgets(max_admitted_writes=2)
FIRST, FOLLOW_UP = "first", "follow-up"


def two_step_plan(connection_id: str = CONN, *, path: str = "/key") -> ActionPlan:
    """Write a note, then a follow-up note whose ``parent`` is the first note's verified key
    (`NotesVerifier` reports the read-back note), copied through a lineage placeholder."""
    return ActionPlan(
        plan_id="driver-chosen",
        task_id="driver-chosen",
        task_version="0",
        steps=(
            PlannedStep(
                step_id=FIRST,
                proposal=ActionProposal(
                    contract_id=CREATE.contract_id,
                    connection_id=connection_id,
                    arguments={"text": "standup notes"},
                ),
            ),
            PlannedStep(
                step_id=FOLLOW_UP,
                proposal=ActionProposal(
                    contract_id=CREATE.contract_id,
                    connection_id=connection_id,
                    arguments={"text": "follow-up", "parent": LineageRef(step_id=FIRST, path=path)},
                ),
                depends_on=(FIRST,),
            ),
        ),
    )


@dataclass
class NotesPlanDriver:
    """Reads, then proposes ``plan`` once; answers after the verified result."""

    plan: ActionPlan = field(default_factory=two_step_plan)
    connection_id: str = CONN
    driver_id: str = "notes-plan-driver"
    calls: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        self.seen.append(step_input)
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            return RequestReads(
                reads=(
                    ReadRequest(
                        request_id="r1",
                        contract_id=READ.contract_id,
                        connection_id=self.connection_id,
                        arguments={},
                    ),
                )
            )
        return ProposePlan(plan=self.plan)


@dataclass
class MetadataDriver:
    """Reads on ``connection_id``, then proposes one note carrying nested ``metadata`` on
    ``propose_on``; answers after the verified result (Task 2c.8b)."""

    connection_id: str = CONN
    propose_on: str = CONN
    driver_id: str = "notes-metadata-driver"
    calls: int = 0
    seen: list[DriverInput] = field(default_factory=list)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            read = ReadRequest(
                request_id="r1",
                contract_id=READ.contract_id,
                connection_id=self.connection_id,
                arguments={},
            )
            return RequestReads(reads=(read,))
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=CREATE.contract_id,
                connection_id=self.propose_on,
                arguments={"text": "standup notes", "metadata": {"value": "approved"}},
            )
        )


@dataclass
class NotesBackend:
    revision: int = 1
    notes: dict[str, dict[str, str]] = field(default_factory=dict)
    create_calls: int = 0
    read_calls: int = 0
    # None | "timeout" | "reject" | "timeout-no-commit"
    # | "read-reject" | "read-reject-once" | "read-auth"
    fail_mode: str | None = None

    def supports(self, binding: CapabilityBinding) -> bool:
        return binding.plugin_id == "notes-fixture"

    async def read(
        self, ctx: TaskContext, binding: CapabilityBinding, request: ReadRequest
    ) -> Observation:
        self.read_calls += 1
        if self.fail_mode == "read-auth":
            raise KnownNoEffectError(
                "AUTH_REQUIRED", "credentials unavailable before provider call"
            )
        if self.fail_mode == "read-reject" or (
            self.fail_mode == "read-reject-once" and self.read_calls == 1
        ):
            raise KnownNoEffectError("E_AGENT_INVALID_REF", "Odoo rejected the request")
        key = request.arguments.get("operation_key")
        data: dict[str, Any] = (
            {"notes": [n for n in self.notes.values() if n["key"] == key]}
            if key
            else {"topic": "standup", "count": str(len(self.notes))}
        )
        ev = EvidenceRef(
            evidence_id=new_id("ev"),
            tenant_id=ctx.tenant_id,
            source="notes",
            locator="all",
            revision=f"rev:{self.revision}",
            observed_at=utc_now(),
            scope=ctx.tenant_id,
        )
        return Observation(
            request_id=request.request_id, contract_id=request.contract_id, data=data, evidence=ev
        )

    async def execute(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord, attempt: int
    ) -> ExecutionReceipt:
        self.create_calls += 1
        if self.fail_mode == "reject":
            raise KnownNoEffectError("INVALID", "rejected")
        if self.fail_mode == "timeout-no-commit":
            raise TimeoutError
        key = action.logical_operation_id
        note = {"key": key, "text": str(action.arguments["text"])}
        if "parent" in action.arguments:
            note["parent"] = str(action.arguments["parent"])
        self.notes.setdefault(key, note)
        if self.fail_mode == "timeout":
            raise TimeoutError
        now = utc_now()
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=attempt,
            status=ReceiptStatus.COMMITTED,
            external_refs=(f"note:{key}",),
            started_at=now,
            finished_at=now,
        )

    async def reconcile(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord
    ) -> ExecutionReceipt | None:
        if action.logical_operation_id not in self.notes:
            return None
        now = utc_now()
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=1,
            status=ReceiptStatus.COMMITTED,
            external_refs=(f"note:{action.logical_operation_id}",),
            started_at=now,
            finished_at=now,
        )


class NotesValidator:
    validator_id = "notes-rules"

    def __init__(self) -> None:
        self.explode = False
        self.bundle = "notes@1"

    def supports(self, contract_id: str) -> bool:
        return contract_id in {CREATE.contract_id, PIN.contract_id}

    async def validate(self, ctx: TaskContext, item: ValidationInput) -> ValidationResult:
        if self.explode:
            raise RuntimeError("engine down")
        ok = bool(str(item.proposal.arguments.get("text", "")).strip())
        status = ValidationStatus.PASS if ok else ValidationStatus.FAIL
        return ValidationResult(
            status=status,
            findings=(
                Finding(
                    rule_id="NOTE-001",
                    rule_version="1",
                    status=status,
                    message="text must be non-empty",
                ),
            ),
            rule_bundle_version=self.bundle,
            validator_id=self.validator_id,
        )


class NotesVerifier:
    verifier_id = "notes-verifier"

    def __init__(self) -> None:
        self.tamper = False

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE.contract_id

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt,
        reader: ScopedReader,
    ) -> OutcomeReport:
        obs = await reader.read(READ.contract_id, {"operation_key": action.logical_operation_id})
        notes = list(obs.data["notes"])
        expected = "tampered" if self.tamper else str(action.arguments["text"])
        ok = len(notes) == 1 and notes[0]["text"] == expected
        return OutcomeReport(
            run_id=ctx.run_id,
            action_id=action.action_id,
            status=OutcomeStatus.VERIFIED if ok else OutcomeStatus.FAILED,
            checks=(OutcomeCheck(name="note", passed=ok, expected=expected, observed=str(notes)),),
            verifier_id=self.verifier_id,
            verifier_version="1",
            reported_at=utc_now(),
            verified_values=dict(notes[0]) if len(notes) == 1 else None,  # the read-back
        )


@dataclass
class NotesDriver:
    texts: list[str]
    connection_id: str = CONN
    driver_id: str = "notes-driver"
    calls: int = 0

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        self.calls += 1
        if step_input.action_result is not None:
            return FinalAnswer(text="done")
        if not step_input.observations:
            return RequestReads(
                reads=(
                    ReadRequest(
                        request_id="r1",
                        contract_id=READ.contract_id,
                        connection_id=self.connection_id,
                        arguments={},
                    ),
                )
            )
        text = self.texts.pop(0) if self.texts else ""
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=CREATE.contract_id,
                connection_id=self.connection_id,
                arguments={"text": text},
            )
        )


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@dataclass
class Kernel:
    coordinator: RunCoordinator
    store: Any
    backend: NotesBackend
    validator: NotesValidator
    verifier: NotesVerifier
    driver: Any
    connections: ConnectionCatalog
    clock: Clock
    requester: Principal
    approver: Principal
    scope: frozenset[str]


def principal(pid: str, roles: set[str], tenant: str = TENANT) -> Principal:
    return Principal(principal_id=pid, tenant_id=tenant, roles=frozenset(roles))


@pytest.fixture
async def run_store() -> AsyncIterator[Any]:
    """In-memory by default; E_AGENT_TEST_STORE=postgres re-runs the whole kernel
    suite against the PostgreSQL adapter (DSN from E_AGENT_TEST_PG_DSN)."""
    if os.environ.get("E_AGENT_TEST_STORE") != "postgres":
        yield InMemoryRunStore()
        return
    pg = importlib.import_module("e_agent.adapters.postgres")
    dsn = os.environ["E_AGENT_TEST_PG_DSN"]
    await pg.apply_migrations(dsn)
    store = await pg.PostgresRunStore.open(dsn)
    await store.truncate_for_tests()
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
def make_kernel(run_store: Any) -> Callable[..., Kernel]:
    def _make(
        texts: list[str] | None = None,
        *,
        budgets: Budgets | None = None,
        connections: list[ConnectionDescriptor] | None = None,
        binding_connections: dict[str, tuple[str, ...]] | None = None,
        allow_self_approval: bool = False,
        features: Features | None = None,
        task: TaskDefinition = NOTES_TASK,
        approval_ttl: timedelta | None = None,
        driver: Any = None,
        input_schemas: dict[str, dict[str, Any]] | None = None,
        with_pin: bool = False,
    ) -> Kernel:
        backend, validator, verifier = NotesBackend(), NotesValidator(), NotesVerifier()
        driver = driver or NotesDriver(texts=list(texts or ["standup notes"]))
        capabilities = (READ, CREATE, PIN) if with_pin else (READ, CREATE)
        bindings = (*BINDINGS, PIN_BINDING) if with_pin else BINDINGS
        registry = PluginRegistry(binding_connections or {b.binding_id: (CONN,) for b in bindings})
        registry.register(
            plugin_id="notes-fixture",
            plugin_version="0.1.0",
            declared_capabilities=capabilities,
            binding_templates=bindings,
            declared_task_definitions=(
                TaskDeclaration(task_id=task.task_id, version=task.version),
            ),
            contribution=PluginContribution(
                capabilities=capabilities,
                validators=(validator,),
                executors=(backend,),
                verifiers=(verifier,),
                task_definitions=(task,),
                input_schemas=input_schemas or {},
            ),
        )
        registry.admit_task_definitions()
        catalog = ConnectionCatalog(
            connections
            or [
                ConnectionDescriptor(
                    tenant_id=TENANT,
                    connection_id=CONN,
                    version=1,
                    integration_id="notes-mem",
                    ownership=ConnectionOwnership.TENANT_SHARED,
                    provider_subject="svc",
                )
            ]
        )
        clock, store = Clock(), run_store
        coordinator = RunCoordinator(
            store=store,
            registry=registry,
            connections=catalog,
            policy=DefaultPolicy(),
            driver=driver,
            clock=clock,
            budgets=budgets,
            allow_self_approval=allow_self_approval,
            features=features,
            **({} if approval_ttl is None else {"approval_ttl": approval_ttl}),
        )
        return Kernel(
            coordinator,
            store,
            backend,
            validator,
            verifier,
            driver,
            catalog,
            clock,
            principal("alice", {"requester"}),
            principal("bob", {"approver"}),
            frozenset({CONN}),
        )

    return _make


async def run_resume_work(
    store: Any, coordinator: RunCoordinator, owner: str = "resume-test"
) -> Any:
    """Claim the one queued ``resume`` item and run it under its claim, as the server
    worker does (ADR 0025 amendment); afterwards no other work is queued for it."""
    claim = await store.claim_work(owner)
    assert claim is not None and claim.kind == "resume", claim
    async with store.work_scope(claim):
        run = await coordinator.resume_plan(claim.tenant_id, claim.run_id)
        await store.finish_work(claim)
    return run
