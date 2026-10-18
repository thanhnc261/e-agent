"""Narrow ports between the kernel and plugins (HLD §6, MVP design §5).

Ports exchange portable records only. A plugin never receives a raw provider
client, a database session or the ability to issue approvals.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.capability import CapabilityBinding, CapabilityDescriptor
from e_agent.contracts.context import TaskContext
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.outcome import OutcomeReport
from e_agent.contracts.plan import ActionProposal
from e_agent.contracts.receipt import ExecutionReceipt
from e_agent.contracts.task import TaskDefinition
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
    user_input: str | None = None
    observations: tuple[Observation, ...] = ()
    findings: tuple[Finding, ...] = ()
    action_result: Mapping[str, Any] | None = None
    # request_id -> "<code>: <safe_message>" for reads the provider rejected (ADR 0022).
    # An observation for the same request id supersedes an error.
    read_errors: Mapping[str, str] = field(default_factory=dict)
    # The run's tool set, as contract ids, when its task definition fixes one (D6, ADR 0028):
    # the driver offers only these tools on this turn. None offers every tool, as today. The
    # kernel refuses anything outside the set; this field only shapes what the model sees.
    allowed_capabilities: tuple[str, ...] | None = None


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
class SafeTextSink(Protocol):
    """Transient public answer text only; no thinking, tool arguments or durable events."""

    async def emit(self, ctx: TaskContext, text: str, *, new_message: bool = False) -> None: ...


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
        receipt: ExecutionReceipt | None,
        reader: ScopedReader,
    ) -> OutcomeReport:
        """``receipt`` is None for structured answers (EffectKind.ANSWER)."""
        ...


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
    credentials: Any = None
    """CredentialResolver scoped to this plugin's integration (e_agent.sdk.auth)."""


@dataclass(frozen=True)
class TaskPreset:
    """A named demo task a domain pack offers: its prompt and the refs it names.

    ``prompt`` is the task text with every default ref written out. Rendering
    replaces a default with an override by plain text replacement, one override
    after another, so an override equal to another ref's default is replaced again
    by a later one. Phase 2 extends presets into task definitions.
    """

    kind: str
    prompt: str
    default_refs: Mapping[str, str] = field(default_factory=dict)
    """Ref name to default value, in the order overrides are applied."""
    help: str = ""

    def __post_init__(self) -> None:
        for name, value in self.default_refs.items():
            if not value:
                raise ValueError(f"task preset {self.kind!r}: empty default for {name!r}")

    def __eq__(self, other: object) -> bool:
        # Overrides apply in default-ref order, so two presets differing only in that
        # order render differently and are not equal (a dict comparison ignores order).
        if not isinstance(other, TaskPreset):
            return NotImplemented
        return (self.kind, self.prompt, tuple(self.default_refs.items()), self.help) == (
            other.kind,
            other.prompt,
            tuple(other.default_refs.items()),
            other.help,
        )

    def render(self, overrides: Iterable[tuple[str, str]] = ()) -> str:
        """The prompt after each ``(ref name, value)`` in turn; unknown names are ignored."""
        text = self.prompt
        for name, value in overrides:
            if name in self.default_refs:
                text = text.replace(self.default_refs[name], value)
        return text


@dataclass(frozen=True)
class DriverRequest:
    """The profile's driver arguments, handed to a contributed driver factory."""

    connection_id: str
    mode: str
    task_kind: str
    refs: Mapping[str, str] = field(default_factory=dict)
    """The task preset's default refs, in its order, with the profile's refs over them."""


class DriverFactory(Protocol):
    def __call__(self, request: DriverRequest) -> AgentDriver: ...


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
    task_presets: tuple[TaskPreset, ...] = ()
    """Demo tasks the pack offers; a profile's ``driver.task_kind`` names one."""
    task_definitions: tuple[TaskDefinition, ...] = ()
    """Task definitions (ADR 0028), as the manifest's ``provides_task_definitions`` names
    them. A definition's ``task_id`` is its preset's ``kind`` (D8)."""
    driver_factories: Mapping[str, DriverFactory] = field(default_factory=dict)
    """Driver factories keyed by the profile's ``driver.kind`` (ADR 0026)."""
    diagnostics: Callable[[], Mapping[str, Any]] | None = None
    """Counters a provider reports for fixture runs and tests, such as how many writes
    reached it. Never business data, and never read by the kernel's run logic."""


class PluginFactory(Protocol):
    def __call__(self, services: PluginServices) -> PluginContribution: ...
