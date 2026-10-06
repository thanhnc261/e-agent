"""Narrow ports between the kernel and plugins (HLD §6, MVP design §5).

Ports exchange portable records only. A plugin never receives a raw provider
client, a database session or the ability to issue approvals.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.capability import CapabilityBinding, CapabilityDescriptor
from e_agent.contracts.context import TaskContext
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.validation import Finding, ValidationResult

# ---- Agent driver -----------------------------------------------------------


@dataclass(frozen=True)
class ReadRequest:
    request_id: str
    contract_id: str
    connection_id: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class Observation:
    """Authorized, redacted result of a read, returned to the driver."""

    request_id: str
    contract_id: str
    data: Mapping[str, Any]
    evidence: EvidenceRef


@dataclass(frozen=True)
class DriverInput:
    task: str
    observations: tuple[Observation, ...] = ()
    findings: tuple[Finding, ...] = ()
    action_result: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RequestReads:
    reads: tuple[ReadRequest, ...]


@dataclass(frozen=True)
class ProposeAction:
    proposal: ActionProposal


@dataclass(frozen=True)
class FinalAnswer:
    text: str


@dataclass(frozen=True)
class AskClarification:
    question: str


DriverStep = RequestReads | ProposeAction | FinalAnswer | AskClarification


@runtime_checkable
class AgentDriver(Protocol):
    """Model interaction. Returns proposals; never executes effects or approves."""

    driver_id: str

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep: ...


# ---- Capabilities, validation, execution, verification ----------------------


@runtime_checkable
class CapabilityProvider(Protocol):
    def capabilities(self) -> tuple[CapabilityDescriptor, ...]: ...


@dataclass(frozen=True)
class ValidationInput:
    proposal: ActionProposal
    observations: tuple[Observation, ...]


@runtime_checkable
class PlanValidator(Protocol):
    validator_id: str

    def supports(self, contract_id: str) -> bool: ...

    async def validate(self, ctx: TaskContext, item: ValidationInput) -> ValidationResult: ...


@runtime_checkable
class ActionExecutor(Protocol):
    """Executes admitted invocations for one binding. Writes carry an operation key."""

    def supports(self, binding: CapabilityBinding) -> bool: ...

    async def read(
        self, ctx: TaskContext, binding: CapabilityBinding, request: ReadRequest
    ) -> Observation: ...

    async def execute(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord, attempt: int
    ) -> ExecutionReceipt: ...

    async def reconcile(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord
    ) -> ExecutionReceipt | None: ...


@runtime_checkable
class ScopedReader(Protocol):
    """Authorized read port handed to verifiers; it cannot write or approve."""

    async def read(self, contract_id: str, arguments: Mapping[str, Any]) -> Observation: ...


@runtime_checkable
class OutcomeVerifier(Protocol):
    verifier_id: str

    def supports(self, contract_id: str) -> bool: ...

    async def verify(
        self,
        ctx: TaskContext,
        action: ActionRecord,
        receipt: ExecutionReceipt,
        reader: ScopedReader,
    ) -> OutcomeReport: ...


# ---- Policy -----------------------------------------------------------------


@dataclass(frozen=True)
class PolicyDecision:
    permitted: bool
    requires_approval: bool
    policy_version: str
    reasons: tuple[str, ...] = ()
    obligations: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class PolicyEvaluator(Protocol):
    def evaluate(
        self, ctx: TaskContext, descriptor: CapabilityDescriptor, connection_id: str
    ) -> PolicyDecision: ...


# ---- Plugin factory -----------------------------------------------------------


@dataclass(frozen=True)
class PluginServices:
    """Scoped services the host gives a plugin at initialization."""

    settings: Mapping[str, Any]


@dataclass
class PluginContribution:
    """What an initialized plugin contributes to the registry."""

    capabilities: tuple[CapabilityDescriptor, ...] = ()
    validators: tuple[PlanValidator, ...] = ()
    executors: tuple[ActionExecutor, ...] = ()
    verifiers: tuple[OutcomeVerifier, ...] = ()
    drivers: tuple[AgentDriver, ...] = ()
    input_schemas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    """JSON Schemas keyed by CapabilityDescriptor.input_schema_id (tool parameters)."""
    agent_guidance: str = ""
    """Domain task guidance for drivers. Explanatory only: rules are enforced by validators."""
    dataset_builders: tuple[Any, ...] = ()
    """ValidationDatasetBuilder instances (see e_agent.sdk.validation)."""


class PluginFactory(Protocol):
    def __call__(self, services: PluginServices) -> PluginContribution: ...
