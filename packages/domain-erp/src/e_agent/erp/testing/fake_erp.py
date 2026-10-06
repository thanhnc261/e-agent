"""In-memory fake ERP executor with an operation ledger (fixture only).

Mirrors the bridge semantics of ADR 0005: one call reserves the operation key
and creates the draft atomically; same key + same digest returns the existing
result; same key + different digest is a known no-effect conflict.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
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

from ..crm import CONTACT_READ, CREATE_LEAD, LEAD_READ, TEAMS_READ
from ..crm.api import CreateLead
from ..inventory import AVAILABILITY_READ
from ..procurement import (
    AMEND_DRAFT_RFQ,
    CREATE_DRAFT_PO,
    DEMAND_READ,
    DRAFT_RFQ_READ,
    OFFERS_READ,
    PURCHASE_ORDER_READ,
)
from ..procurement.api import AmendDraftRfq, DraftPurchaseOrder
from ..receivables import OPEN_INVOICES_READ
from ..sales import CREATE_DRAFT_QUOTATION, OPEN_ORDERS_READ, PRICING_READ, QUOTATION_READ
from ..sales.api import DraftQuotation
from .scenarios import FixtureRfq, FixtureScenario

PLUGIN_ID = "fixture-erp"
BINDINGS = (
    BindingTemplate(binding_id="fixture-erp.inventory.availability", contract_id=AVAILABILITY_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.demand", contract_id=DEMAND_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.offers", contract_id=OFFERS_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.po-create", contract_id=CREATE_DRAFT_PO),
    BindingTemplate(binding_id="fixture-erp.procurement.po-read", contract_id=PURCHASE_ORDER_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.rfq-read", contract_id=DRAFT_RFQ_READ),
    BindingTemplate(binding_id="fixture-erp.procurement.rfq-amend", contract_id=AMEND_DRAFT_RFQ),
    BindingTemplate(binding_id="fixture-erp.sales.pricing", contract_id=PRICING_READ),
    BindingTemplate(
        binding_id="fixture-erp.sales.quotation-create", contract_id=CREATE_DRAFT_QUOTATION
    ),
    BindingTemplate(binding_id="fixture-erp.sales.quotation-read", contract_id=QUOTATION_READ),
    BindingTemplate(binding_id="fixture-erp.sales.open-orders", contract_id=OPEN_ORDERS_READ),
    BindingTemplate(binding_id="fixture-erp.crm.contact", contract_id=CONTACT_READ),
    BindingTemplate(binding_id="fixture-erp.crm.teams", contract_id=TEAMS_READ),
    BindingTemplate(binding_id="fixture-erp.crm.lead-create", contract_id=CREATE_LEAD),
    BindingTemplate(binding_id="fixture-erp.crm.lead-read", contract_id=LEAD_READ),
    BindingTemplate(
        binding_id="fixture-erp.receivables.open-invoices", contract_id=OPEN_INVOICES_READ
    ),
)
WRITES = (CREATE_DRAFT_PO, AMEND_DRAFT_RFQ, CREATE_DRAFT_QUOTATION, CREATE_LEAD)


@dataclass
class _Op:
    """Ledger row for ERP-04/05/07 writes: key -> digest and the record it produced."""

    payload_digest: str
    contract_id: str
    external_ref: str
    record: dict[str, Any]


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
    ledger: dict[str, _Op] = field(default_factory=dict)
    rfq: FixtureRfq | None = None
    rfq_revision: int = 1

    def __post_init__(self) -> None:
        self.rfq = replace(self.scenario.rfq)

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
            op = self.ledger.get(key)
            if op is not None and op.contract_id == AMEND_DRAFT_RFQ:
                data = {"orders": [self._rfq_order_view(key)]}
        else:
            data, ev = self._read_more(ctx, request)
        return Observation(
            request_id=request.request_id, contract_id=request.contract_id, data=data, evidence=ev
        )

    def _rfq_view(self) -> dict[str, Any]:
        r = self.rfq
        assert r is not None
        return {
            "purchase_order_ref": r.purchase_order_ref,
            "external_ref": r.external_ref,
            "state": r.state,
            "revision": r.revision,
            "supplier_ref": r.supplier_ref,
            "product_ref": r.product_ref,
            "quantity": r.quantity,
            "unit": self.scenario.unit,
            "unit_price": r.unit_price,
            "currency": self.scenario.currency,
            "requested_date": r.requested_date.isoformat(),
        }

    def _rfq_order_view(self, key: str) -> dict[str, Any]:
        r = self.rfq
        assert r is not None
        return {
            "external_ref": r.external_ref,
            "purchase_order_ref": r.purchase_order_ref,
            "operation_key": key,
            "state": r.state,
            "product_ref": r.product_ref,
            "supplier_ref": r.supplier_ref,
            "quantity": r.quantity,
            "unit": self.scenario.unit,
            "currency": self.scenario.currency,
            "unit_price": r.unit_price,
            "subtotal": format_decimal(Decimal(r.quantity) * Decimal(r.unit_price)),
            "requested_date": r.requested_date.isoformat(),
        }

    def _read_more(
        self, ctx: TaskContext, request: ReadRequest
    ) -> tuple[dict[str, Any], EvidenceRef]:
        s, args, cid = self.scenario, request.arguments, request.contract_id
        if cid == DRAFT_RFQ_READ:
            assert self.rfq is not None
            found = args.get("purchase_order_ref") == self.rfq.purchase_order_ref
            return (self._rfq_view() if found else {}), self._evidence(
                ctx, "rfq", str(args.get("purchase_order_ref")), self.rfq.revision
            )
        if cid == PRICING_READ:
            customer, product = str(args["customer_ref"]), str(args["product_ref"])
            if customer not in s.customers or product != s.product_ref:
                return {}, self._evidence(ctx, "pricing", f"{customer}|{product}", "pricing:1")
            data = {
                "customer_ref": customer,
                "customer_name": customer.split(":", 1)[-1].title(),
                "customer_active": s.customers[customer],
                "product_ref": product,
                "product_saleable": s.product_saleable,
                "list_price": s.list_price,
                "currency": s.currency,
                "unit": s.unit,
            }
            return data, self._evidence(ctx, "pricing", f"{customer}|{product}", "pricing:1")
        if cid == QUOTATION_READ:
            key = str(args["operation_key"])
            op = self.ledger.get(key)
            quotes = [op.record] if op and op.contract_id == CREATE_DRAFT_QUOTATION else []
            return {"quotations": quotes}, self._evidence(ctx, "quotations", key, str(len(quotes)))
        if cid == OPEN_ORDERS_READ:
            as_of = date.fromisoformat(str(args["as_of"]))
            return {"as_of": as_of.isoformat(), "orders": s.orders}, self._evidence(
                ctx, "sale-orders", as_of.isoformat(), "orders:1"
            )
        if cid == CONTACT_READ:
            ref = str(args["contact_ref"])
            data = (
                {}
                if ref not in s.contacts
                else {
                    "contact_ref": ref,
                    "name": ref.split(":", 1)[-1].title(),
                    "active": s.contacts[ref],
                }
            )
            return data, self._evidence(ctx, "contacts", ref, "contact:1")
        if cid == TEAMS_READ:
            data = {
                "teams": [
                    {"team_ref": t, "name": t.split(":", 1)[-1], "member_refs": m}
                    for t, m in s.teams.items()
                ],
                "sources": [{"source_ref": x, "name": x.split(":", 1)[-1]} for x in s.sources],
            }
            return data, self._evidence(ctx, "teams", "all", "teams:1")
        if cid == LEAD_READ:
            key = str(args["operation_key"])
            op = self.ledger.get(key)
            leads = [op.record] if op and op.contract_id == CREATE_LEAD else []
            return {"leads": leads}, self._evidence(ctx, "leads", key, str(len(leads)))
        if cid == OPEN_INVOICES_READ:
            as_of = date.fromisoformat(str(args["as_of"]))
            open_ = [i for i in s.invoices if Decimal(i["residual"]) > 0]
            data = {"as_of": as_of.isoformat(), "company": "Fixture Co", "invoices": open_}
            return data, self._evidence(ctx, "invoices", as_of.isoformat(), "invoices:1")
        raise KnownNoEffectError("UNSUPPORTED", "unsupported read")

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
        if action.contract_id not in WRITES:
            raise KnownNoEffectError("UNSUPPORTED", "unsupported write")
        self.create_calls += 1
        if action.contract_id != CREATE_DRAFT_PO:
            return self._execute_ledgered(action, attempt)
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

    def _execute_ledgered(self, action: ActionRecord, attempt: int) -> ExecutionReceipt:
        """ERP-04/05/07: reserve the key and apply the change in one step (like the bridge)."""
        started = utc_now()
        key = action.logical_operation_id
        existing = self.ledger.get(key)
        if existing is not None and existing.payload_digest != action.digest:
            raise KnownNoEffectError("CONFLICT", "operation key reused with different payload")
        if existing is None:
            existing = self._apply(action)
            self.ledger[key] = existing
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

    def _apply(self, action: ActionRecord) -> _Op:
        key, digest = action.logical_operation_id, action.digest
        if action.contract_id == AMEND_DRAFT_RFQ:
            a = AmendDraftRfq.model_validate(action.arguments)
            r = self.rfq
            if r is None or a.purchase_order_ref != r.purchase_order_ref:
                raise KnownNoEffectError("INVALID", "unknown RFQ")
            if r.state != "draft":
                raise KnownNoEffectError("INVALID", "only draft RFQs can be amended")
            if a.expected_revision != r.revision:
                raise KnownNoEffectError("STALE", "RFQ changed since it was read")
            self.rfq_revision += 1
            self.rfq = replace(
                r,
                quantity=a.quantity,
                requested_date=a.requested_date,
                revision=f"rev-{self.rfq_revision}",
            )
            return _Op(digest, action.contract_id, r.external_ref, {})
        if action.contract_id == CREATE_DRAFT_QUOTATION:
            q = DraftQuotation.model_validate(action.arguments)
            if (
                not self.scenario.customers.get(q.customer_ref)
                or not self.scenario.product_saleable
            ):
                raise KnownNoEffectError("INVALID", "customer or product cannot be quoted")
            ref = f"S/FIXTURE/Q{len(self.ledger) + 1:04d}"
            record = {
                **q.model_dump(mode="json"),
                "external_ref": ref,
                "operation_key": key,
                "state": "draft",
                "sent": False,
            }
            return _Op(digest, action.contract_id, ref, record)
        lead = CreateLead.model_validate(action.arguments)
        ref = f"LEAD/FIXTURE/{len(self.ledger) + 1:04d}"
        record = {**lead.model_dump(mode="json"), "external_ref": ref, "operation_key": key}
        return _Op(digest, action.contract_id, ref, record)

    async def reconcile(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord
    ) -> ExecutionReceipt | None:
        op = self.ledger.get(action.logical_operation_id)
        if op is not None:
            if op.payload_digest != action.digest:
                return None
            now = utc_now()
            return ExecutionReceipt(
                action_id=action.action_id,
                attempt=1,
                status=ReceiptStatus.COMMITTED,
                external_refs=(op.external_ref,),
                provider_correlation=action.logical_operation_id,
                started_at=now,
                finished_at=now,
            )
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
