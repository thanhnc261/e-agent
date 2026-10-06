"""In-memory fake ERP executor with an operation ledger (fixture only).

Mirrors the bridge semantics of ADR 0005: one call reserves the operation key
and creates the draft atomically; same key + same digest returns the existing
result; same key + different digest is a known no-effect conflict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.capability import CapabilityBinding
from e_agent.contracts.common import format_decimal, new_id, utc_now
from e_agent.contracts.context import TaskContext
from e_agent.contracts.evidence import EvidenceRef
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.manifest import BindingTemplate
from e_agent.sdk.ports import Observation, ReadRequest

from ..inventory import AVAILABILITY_READ
from ..procurement import CREATE_DRAFT_PO, DEMAND_READ, OFFERS_READ, PURCHASE_ORDER_READ
from ..procurement.api import DraftPurchaseOrder
from .scenarios import FixtureScenario

PLUGIN_ID = "fixture-erp"
BINDINGS = (
    BindingTemplate(binding_id="fixture-erp.inventory.availability", contract_id=AVAILABILITY_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.demand", contract_id=DEMAND_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.offers", contract_id=OFFERS_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.po-create", contract_id=CREATE_DRAFT_PO),
    BindingTemplate(binding_id="fixture-erp.procurement.po-read", contract_id=PURCHASE_ORDER_READ),
)


@dataclass
class _Order:
    external_ref: str
    operation_key: str
    payload_digest: str
    args: DraftPurchaseOrder
    state: str = "draft"


@dataclass
class FakeErp:
    scenario: FixtureScenario
    lose_response_after_commit: bool = False
    stock_revision: int = 1
    orders: dict[str, _Order] = field(default_factory=dict)
    create_calls: int = 0

    def supports(self, binding: CapabilityBinding) -> bool:
        return binding.plugin_id == PLUGIN_ID

    def _evidence(self, ctx: TaskContext, source: str, locator: str, revision: str) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=new_id("ev"),
            tenant_id=ctx.tenant_id,
            source=f"fixture-erp:{source}",
            locator=locator,
            revision=revision,
            observed_at=utc_now(),
            scope=ctx.tenant_id,
            environment="fixture",
        )

    async def read(
        self, ctx: TaskContext, binding: CapabilityBinding, request: ReadRequest
    ) -> Observation:
        s = self.scenario
        data: dict[str, Any]
        if request.contract_id == AVAILABILITY_READ:
            data = {
                "product_ref": s.product_ref,
                "available": s.available,
                "inbound": s.inbound,
                "unit": s.unit,
            }
            ev = self._evidence(ctx, "stock", s.product_ref, f"stock:{self.stock_revision}")
        elif request.contract_id == DEMAND_READ:
            data = {
                "demand_ref": s.demand_ref,
                "product_ref": s.product_ref,
                "quantity": s.demand_quantity,
                "unit": s.unit,
                "requested_date": s.requested_date.isoformat(),
                "budget": s.budget,
                "currency": s.currency,
            }
            ev = self._evidence(ctx, "demand", s.demand_ref, "demand:1")
        elif request.contract_id == OFFERS_READ:
            data = {
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
            ev = self._evidence(ctx, "offers", s.product_ref, "offers:1")
        elif request.contract_id == PURCHASE_ORDER_READ:
            key = str(request.arguments["operation_key"])
            orders = [o for o in self.orders.values() if o.operation_key == key]
            data = {"orders": [self._view(o) for o in orders]}
            ev = self._evidence(ctx, "purchase-orders", key, f"po:{len(self.orders)}")
        else:
            raise KnownNoEffectError("UNSUPPORTED", "unsupported read")
        return Observation(
            request_id=request.request_id, contract_id=request.contract_id, data=data, evidence=ev
        )

    @staticmethod
    def _view(order: _Order) -> dict[str, str]:
        a = order.args
        return {
            "external_ref": order.external_ref,
            "operation_key": order.operation_key,
            "state": order.state,
            "product_ref": a.product_ref,
            "supplier_ref": a.supplier_ref,
            "quantity": a.quantity,
            "unit": a.unit,
            "currency": a.currency,
            "unit_price": a.unit_price,
            "subtotal": a.subtotal,
        }

    async def execute(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord, attempt: int
    ) -> ExecutionReceipt:
        if action.contract_id != CREATE_DRAFT_PO:
            raise KnownNoEffectError("UNSUPPORTED", "unsupported write")
        self.create_calls += 1
        started = utc_now()
        key = action.logical_operation_id
        existing = self.orders.get(key)
        if existing is not None and existing.payload_digest != action.digest:
            raise KnownNoEffectError("CONFLICT", "operation key reused with different payload")
        if existing is None:
            args = DraftPurchaseOrder.model_validate(action.arguments)
            subtotal = Decimal(args.quantity) * Decimal(args.unit_price)
            if format_decimal(subtotal) != args.subtotal:
                raise KnownNoEffectError("INVALID", "subtotal mismatch")
            existing = _Order(
                external_ref=f"PO/FIXTURE/{len(self.orders) + 1:04d}",
                operation_key=key,
                payload_digest=action.digest,
                args=args,
            )
            self.orders[key] = existing  # "commit"
            if self.lose_response_after_commit:
                self.lose_response_after_commit = False
                raise TimeoutError("response lost after commit")
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=attempt,
            status=ReceiptStatus.COMMITTED,
            external_refs=(existing.external_ref,),
            provider_correlation=key,
            started_at=started,
            finished_at=utc_now(),
        )

    async def reconcile(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord
    ) -> ExecutionReceipt | None:
        order = self.orders.get(action.logical_operation_id)
        if order is None or order.payload_digest != action.digest:
            return None
        now = utc_now()
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=1,
            status=ReceiptStatus.COMMITTED,
            external_refs=(order.external_ref,),
            provider_correlation=order.operation_key,
            started_at=now,
            finished_at=now,
        )
