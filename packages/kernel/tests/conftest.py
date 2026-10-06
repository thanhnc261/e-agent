"""A tiny NON-ERP fixture domain ("notes") used to prove the kernel is domain-neutral.

Nothing here imports e_agent.erp: the kernel must run its full lifecycle with only
this domain installed (MVP design §13, domain neutrality gate).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from e_agent.contracts.action import ActionRecord
from e_agent.contracts.capability import CapabilityBinding, CapabilityDescriptor, EffectKind
from e_agent.contracts.common import new_id, utc_now
from e_agent.contracts.connection import ConnectionDescriptor, ConnectionOwnership
from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.outcome import OutcomeCheck, OutcomeReport, OutcomeStatus
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.contracts.validation import Finding, ValidationResult, ValidationStatus
from e_agent.kernel.connections import ConnectionCatalog
from e_agent.kernel.coordinator import RunCoordinator
from e_agent.kernel.memory_store import InMemoryRunStore
from e_agent.kernel.policy import DefaultPolicy
from e_agent.kernel.registry import PluginRegistry
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.manifest import BindingTemplate
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    Observation,
    PluginContribution,
    ProposeAction,
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
CREATE = CapabilityDescriptor(
    contract_id="notes.note.create.v1",
    effect=EffectKind.WRITE,
    input_schema_id="c",
    output_schema_id="r",
)
BINDINGS = (
    BindingTemplate(binding_id="notes-mem.read", contract_id=READ.contract_id),
    BindingTemplate(binding_id="notes-mem.create", contract_id=CREATE.contract_id),
)
TENANT = "tenant-a"
CONN = "conn-notes"


@dataclass
class NotesBackend:
    revision: int = 1
    notes: dict[str, dict[str, str]] = field(default_factory=dict)
    create_calls: int = 0
    fail_mode: str | None = None  # None | "timeout" | "reject" | "timeout-no-commit"

    def supports(self, binding: CapabilityBinding) -> bool:
        return binding.plugin_id == "notes-fixture"

    async def read(
        self, ctx: TaskContext, binding: CapabilityBinding, request: ReadRequest
    ) -> Observation:
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
        self.notes.setdefault(key, {"key": key, "text": str(action.arguments["text"])})
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

    def supports(self, contract_id: str) -> bool:
        return contract_id == CREATE.contract_id

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
            rule_bundle_version="notes@1",
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
    store: InMemoryRunStore
    backend: NotesBackend
    validator: NotesValidator
    verifier: NotesVerifier
    driver: NotesDriver
    connections: ConnectionCatalog
    clock: Clock
    requester: Principal
    approver: Principal
    scope: frozenset[str]


def principal(pid: str, roles: set[str], tenant: str = TENANT) -> Principal:
    return Principal(principal_id=pid, tenant_id=tenant, roles=frozenset(roles))


@pytest.fixture
def make_kernel() -> Callable[..., Kernel]:
    def _make(
        texts: list[str] | None = None,
        *,
        budgets: Budgets | None = None,
        connections: list[ConnectionDescriptor] | None = None,
        binding_connections: dict[str, tuple[str, ...]] | None = None,
    ) -> Kernel:
        backend, validator, verifier = NotesBackend(), NotesValidator(), NotesVerifier()
        driver = NotesDriver(texts=list(texts or ["standup notes"]))
        registry = PluginRegistry(binding_connections or {b.binding_id: (CONN,) for b in BINDINGS})
        registry.register(
            plugin_id="notes-fixture",
            plugin_version="0.1.0",
            declared_capabilities=(READ, CREATE),
            binding_templates=BINDINGS,
            contribution=PluginContribution(
                capabilities=(READ, CREATE),
                validators=(validator,),
                executors=(backend,),
                verifiers=(verifier,),
            ),
        )
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
        clock, store = Clock(), InMemoryRunStore()
        coordinator = RunCoordinator(
            store=store,
            registry=registry,
            connections=catalog,
            policy=DefaultPolicy(),
            driver=driver,
            clock=clock,
            budgets=budgets,
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
