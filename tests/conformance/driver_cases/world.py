"""The host side of a conformance case: synthetic ERP fixture data, the ERP tool specs and
a small host loop that stands in for the kernel's driver turn.

The data is the simulator's ``valid`` scenario (``e_agent.plugins.erp.simulator.scenarios``)
in the shapes the fixture ERP returns (``fake_erp.FakeErp.read``). The tool specs are the
ones the server offers on the fixture profile (`tool_specs`), so both drivers propose the same
contracts on the same connection. Evidence ids are deterministic (`evidence_id`), so an
authored recording can name a read's evidence by its call id. A context pack is built by the
kernel's own assembler on a local route, as the kernel builds it under
``context_assembler: on``. No store, network, model or ERP is used.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from e_agent.adapters.pydantic_ai import ToolSpec
from e_agent.contracts.capability import EffectKind
from e_agent.contracts.context import Budgets, Principal, TaskContext
from e_agent.contracts.context_pack import ContextPack, ContextPolicy
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.progress import BudgetsUsed, ProgressLedger, TaskRefState
from e_agent.contracts.validation import Finding, ValidationStatus
from e_agent.kernel.context import assemble
from e_agent.plugins.erp.domain.inventory import AVAILABILITY_READ
from e_agent.plugins.erp.domain.procurement import (
    CREATE_DRAFT_PO,
    DEMAND_READ,
    OFFERS_READ,
    SHORTAGE_ANSWER,
)
from e_agent.plugins.erp.domain.testing.scripted_tasks import ScriptedErpDriver
from e_agent.plugins.erp.simulator import fixture_profile_path
from e_agent.plugins.erp.simulator.scenarios import SCENARIOS
from e_agent.sdk.ports import (
    AgentDriver,
    DriverInput,
    DriverStep,
    GroundingOffer,
    Observation,
    ProposeAction,
    ProposePlan,
    ReadRequest,
    RequestReads,
)
from e_agent.server.bootstrap import build_runtime, tool_specs
from e_agent.server.profile import load_profile

TENANT = "tenant-conformance"
NOW = datetime(2026, 10, 20, tzinfo=UTC)
DRAFT_PO_TASK = "Restock product:widget-a for demand:d-001 by creating a draft purchase order."
SHORTAGE_TASK = "Calculate the shortage of product:widget-a for demand:d-001."
SHORTAGE_TOOLS = (DEMAND_READ, AVAILABILITY_READ, SHORTAGE_ANSWER)
"""A tool set narrower than the shortage task definition's: it leaves out the offers read."""
VERIFIED = {"status": "VERIFIED", "external_refs": ["PO/FIXTURE/0001"]}
LOCAL = {"data_boundary": "local", "data_boundary_basis": "verified"}
__all__ = [
    "AVAILABILITY_READ",
    "CREATE_DRAFT_PO",
    "DEMAND_READ",
    "OFFERS_READ",
    "SHORTAGE_ANSWER",
]


@dataclasses.dataclass(frozen=True)
class World:
    """The ERP tool specs and connection both drivers are built on."""

    specs: tuple[ToolSpec, ...]
    guidance: tuple[str, ...]
    connection_id: str

    @property
    def effects(self) -> dict[str, EffectKind]:
        return {spec.contract_id: spec.effect for spec in self.specs}


_WORLD: World | None = None


async def erp_world() -> World:
    """The fixture profile's tool specs and guidance, as `build_driver` builds them."""
    global _WORLD
    if _WORLD is None:
        profile = load_profile(fixture_profile_path())
        captured: dict[str, Any] = {}

        def capture(registry: Any) -> AgentDriver:
            captured["specs"] = tuple(tool_specs(registry, profile))
            captured["guidance"] = tuple(registry.agent_guidance)
            return ScriptedErpDriver(connection_id=profile.connections[0].connection_id)

        await build_runtime(profile, driver_factory=capture)
        _WORLD = World(
            specs=captured["specs"],
            guidance=captured["guidance"],
            connection_id=profile.connections[0].connection_id,
        )
    return _WORLD


def ctx(run_id: str, **budgets: int) -> TaskContext:
    return TaskContext(
        run_id=run_id,
        tenant_id=TENANT,
        principal=Principal(principal_id="p-conformance", tenant_id=TENANT, roles=frozenset()),
        resource_scope=frozenset({"conn-fixture-erp"}),
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
        budgets=Budgets(**budgets),
    )


def evidence_id(request_id: str) -> str:
    """The evidence id the host gives the observation of read ``request_id``."""
    return f"ev-{request_id}"


def _data(contract_id: str) -> dict[str, Any]:
    s = SCENARIOS["valid"]
    if contract_id == AVAILABILITY_READ:
        return {
            "product_ref": s.product_ref,
            "available": s.available,
            "inbound": s.inbound,
            "unit": s.unit,
        }
    if contract_id == DEMAND_READ:
        return {
            "demand_ref": s.demand_ref,
            "product_ref": s.product_ref,
            "quantity": s.demand_quantity,
            "unit": s.unit,
            "requested_date": s.requested_date.isoformat(),
            "budget": s.budget,
            "currency": s.currency,
        }
    if contract_id == OFFERS_READ:
        return {
            "product_ref": s.product_ref,
            "offers": [
                {
                    "offer_ref": o.offer_ref,
                    "supplier_ref": o.supplier_ref,
                    "product_ref": s.product_ref,
                    "unit_price": o.unit_price,
                    "currency": s.currency,
                    "unit": s.unit,
                    "approved": o.approved,
                    "delivery_date": o.delivery_date.isoformat(),
                }
                for o in s.offers
            ],
        }
    raise AssertionError(f"the conformance host has no fixture data for {contract_id}")


def observe(read: ReadRequest) -> Observation:
    return Observation(
        request_id=read.request_id,
        contract_id=read.contract_id,
        data=_data(read.contract_id),
        evidence=EvidenceRef(
            evidence_id=evidence_id(read.request_id),
            tenant_id=TENANT,
            source="fixture-erp:conformance",
            locator=f"loc:{read.request_id}",
            revision="1",
            observed_at=NOW,
            scope=TENANT,
            environment="fixture",
        ),
    )


def finding(message: str = "the offer's supplier is not approved") -> Finding:
    return Finding(
        rule_id="PR-003",
        rule_version="1",
        status=ValidationStatus.FAIL,
        message=message,
        expected="an approved supplier",
        observed="supplier:unvetted-co",
    )


def _ledger(turns: int) -> ProgressLedger:
    return ProgressLedger(
        run_id="run-conformance",
        goal="conformance",
        task_ref=None,
        task_ref_state=TaskRefState.NONE,
        facts=(),
        done=(),
        pending=(),
        open_findings=(),
        rules_evaluated=(),
        repair_turns=(),
        budgets_used=BudgetsUsed(
            reads_recorded=0,
            failed_validations=0,
            admitted_writes=0,
            driver_turns=turns,
            model_tokens="unknown",
        ),
    )


@dataclasses.dataclass
class Host:
    """The kernel's side of a run, reduced to what a driver sees: the next `DriverInput`.

    It records the reads a step requests (each read returns on the turn after it was asked),
    whether a write is pending, and the packs it built. ``packed`` renders every turn from a
    pack; ``handed`` changes the observations the driver is handed after the pack was built
    from the real ones (a case uses it to tell what the driver read from)."""

    task: str
    allowed: tuple[str, ...] | None = None
    grounding: GroundingOffer = GroundingOffer.OFF
    packed: bool = False
    handed: Callable[[Observation], Observation] | None = None
    observations: list[Observation] = dataclasses.field(default_factory=list)
    returned_on: dict[str, int] = dataclasses.field(default_factory=dict)
    packs: list[ContextPack] = dataclasses.field(default_factory=list)
    turn: int = 0
    pending: bool = False

    def input(
        self,
        *,
        findings: Sequence[Finding] = (),
        action_result: Mapping[str, Any] | None = None,
        user_input: str | None = None,
        pack_turn: int | None = None,
        deferred_pending: bool | None = None,
    ) -> DriverInput:
        observations = tuple(self.observations)
        pack = None
        if self.packed:
            pending = self.pending and action_result is None
            pack = assemble(
                ContextPolicy(),
                _ledger(self.turn + 1),
                observations,
                {},
                findings,
                lambda _contract: {},
                LOCAL,
                tool_set=self.allowed or (),
                turn=self.turn if pack_turn is None else pack_turn,
                observation_turns=self.returned_on,
                deferred_pending=pending if deferred_pending is None else deferred_pending,
            )
            self.packs.append(pack)
        if self.handed is not None:
            observations = tuple(self.handed(o) for o in observations)
        return DriverInput(
            task=self.task,
            user_input=user_input,
            observations=observations,
            findings=tuple(findings),
            action_result=action_result,
            allowed_capabilities=self.allowed,
            context=pack,
            grounding=self.grounding,
        )

    def record(self, step: DriverStep) -> DriverStep:
        self.turn += 1
        if isinstance(step, RequestReads):
            for read in step.reads:
                self.observations.append(observe(read))
                self.returned_on[read.request_id] = self.turn
        self.pending = isinstance(step, ProposeAction | ProposePlan)
        return step

    @property
    def evidence_ids(self) -> set[str]:
        return {o.evidence.evidence_id for o in self.observations}


async def advance(driver: AgentDriver, run: TaskContext, host: Host, **kw: Any) -> DriverStep:
    """One driver turn on the host's next input."""
    return host.record(await driver.advance(run, host.input(**kw)))


async def to_proposal(
    driver: AgentDriver, run: TaskContext, host: Host, *, max_turns: int = 6
) -> list[DriverStep]:
    """Turns from the task until the first step that is not a read request."""
    steps = [await advance(driver, run, host)]
    while isinstance(steps[-1], RequestReads):
        assert len(steps) < max_turns, f"no proposal after {max_turns} turns: {steps}"
        steps.append(await advance(driver, run, host))
    return steps


def emitted_contracts(steps: Sequence[DriverStep]) -> list[str]:
    """Every contract id the steps request or propose."""
    found: list[str] = []
    for step in steps:
        if isinstance(step, RequestReads):
            found.extend(read.contract_id for read in step.reads)
        elif isinstance(step, ProposeAction):
            found.append(step.proposal.contract_id)
        elif isinstance(step, ProposePlan):
            found.extend(s.proposal.contract_id for s in step.plan.steps)
    return found


def shape(step: DriverStep) -> Any:
    """A comparable form of a step: its kind and everything a host acts on."""
    if isinstance(step, RequestReads):
        return ("reads", [(r.request_id, r.contract_id, dict(r.arguments)) for r in step.reads])
    if isinstance(step, ProposeAction):
        return ("propose", step.proposal.model_dump(mode="json"))
    if isinstance(step, ProposePlan):
        return ("plan", step.plan.model_dump(mode="json"))
    return (type(step).__name__, dataclasses.asdict(step))
