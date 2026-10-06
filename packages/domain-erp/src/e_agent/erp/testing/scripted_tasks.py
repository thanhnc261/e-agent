"""Scripted, deterministic driver for ERP-04..08 (no model; fixture and live smoke).

Mirrors ScriptedProcurementDriver: read first, then propose; ``invalid-then-repair``
makes the first proposal break one named rule, ``wrong-answer-then-correct``
makes the first answer fail verification.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from e_agent.contracts.common import format_decimal
from e_agent.contracts.context import TaskContext
from e_agent.contracts.plan import ActionProposal
from e_agent.sdk.ports import (
    DriverInput,
    DriverStep,
    FinalAnswer,
    Observation,
    ProposeAction,
    ReadRequest,
    RequestReads,
)

from ..crm import CONTACT_READ, CREATE_LEAD, TEAMS_READ
from ..procurement import AMEND_DRAFT_RFQ, DRAFT_RFQ_READ
from ..receivables import OPEN_INVOICES_READ, OVERDUE_INVOICES_ANSWER
from ..receivables.api import OpenInvoices
from ..receivables.overdue import overdue
from ..sales import CREATE_DRAFT_QUOTATION, LATE_ORDERS_ANSWER, OPEN_ORDERS_READ, PRICING_READ
from ..sales.api import OpenOrders
from ..sales.late_orders import late_orders
from .scripted_driver import ScriptedProcurementDriver

PROCUREMENT_KINDS = {"draft-po", "shortage", "recommend"}
TASK_KINDS = PROCUREMENT_KINDS | {
    "amend-rfq",
    "quotation",
    "late-orders",
    "crm-lead",
    "overdue-invoices",
}
DEFAULT_REFS = {
    "rfq_ref": "rfq:po-100",
    "customer_ref": "customer:acme",
    "product_ref": "product:widget-a",
    "contact_ref": "contact:jane",
    "team_ref": "team:direct",
    "owner_ref": "user:alice",
    "other_owner_ref": "user:carol",
    "source_ref": "source:website",
    "as_of": "2026-10-06",
}


@dataclass
class ScriptedErpDriver:
    connection_id: str
    mode: str = "valid"
    task_kind: str = "draft-po"
    demand_ref: str = "demand:d-001"
    product_ref: str = "product:widget-a"
    refs: Mapping[str, str] = field(default_factory=dict)
    driver_id: str = "scripted-erp-driver"
    _attempts: dict[str, int] = field(default_factory=dict)
    _procurement: ScriptedProcurementDriver | None = None

    def __post_init__(self) -> None:
        if self.task_kind not in TASK_KINDS:
            raise ValueError(f"unknown task kind {self.task_kind!r}")
        self._procurement = ScriptedProcurementDriver(
            connection_id=self.connection_id,
            mode=self.mode,
            task_kind=self.task_kind if self.task_kind in PROCUREMENT_KINDS else "draft-po",
            demand_ref=self.demand_ref,
            product_ref=self.product_ref,
        )

    def ref(self, name: str) -> str:
        return {**DEFAULT_REFS, **self.refs}[name]

    def _read(self, *reads: tuple[str, str, dict[str, Any]]) -> RequestReads:
        return RequestReads(
            reads=tuple(
                ReadRequest(
                    request_id=rid,
                    contract_id=cid,
                    connection_id=self.connection_id,
                    arguments=args,
                )
                for rid, cid, args in reads
            )
        )

    def _propose(
        self, contract_id: str, arguments: dict[str, Any], effect: str = ""
    ) -> ProposeAction:
        return ProposeAction(
            proposal=ActionProposal(
                contract_id=contract_id,
                connection_id=self.connection_id,
                arguments=arguments,
                expected_effects=(effect,) if effect else (),
            )
        )

    def _bad_first(self, ctx: TaskContext) -> bool:
        attempt = self._attempts.get(ctx.run_id, 0)
        self._attempts[ctx.run_id] = attempt + 1
        if self.mode == "always-invalid":
            return True
        return self.mode in {"invalid-then-repair", "wrong-answer-then-correct"} and attempt == 0

    @staticmethod
    def _data(observations: tuple[Observation, ...], contract_id: str) -> Mapping[str, Any] | None:
        return next((o.data for o in observations if o.contract_id == contract_id and o.data), None)

    async def advance(self, ctx: TaskContext, step_input: DriverInput) -> DriverStep:
        if self.task_kind in PROCUREMENT_KINDS:
            assert self._procurement is not None
            return await self._procurement.advance(ctx, step_input)
        if step_input.action_result is not None:
            refs = ", ".join(step_input.action_result.get("external_refs", []))
            return FinalAnswer(text=f"Done and verified by the host. {refs}".strip())
        obs = step_input.observations
        step: DriverStep = getattr(self, "_" + self.task_kind.replace("-", "_"))(ctx, obs)
        return step

    # -- ERP-04 ----------------------------------------------------------------
    def _amend_rfq(self, ctx: TaskContext, obs: tuple[Observation, ...]) -> DriverStep:
        rfq = self._data(obs, DRAFT_RFQ_READ)
        if not obs:
            return self._read(
                ("r-rfq", DRAFT_RFQ_READ, {"purchase_order_ref": self.ref("rfq_ref")})
            )
        if rfq is None:
            return FinalAnswer(text="The RFQ could not be read; nothing was changed.")
        stale = self._bad_first(ctx)
        return self._propose(
            AMEND_DRAFT_RFQ,
            {
                "purchase_order_ref": rfq["purchase_order_ref"],
                "expected_revision": "stale-revision" if stale else rfq["revision"],
                "quantity": format_decimal(Decimal(rfq["quantity"]) + 5),
                "requested_date": rfq["requested_date"],
            },
            "draft RFQ quantity changed",
        )

    # -- ERP-05 ----------------------------------------------------------------
    def _quotation(self, ctx: TaskContext, obs: tuple[Observation, ...]) -> DriverStep:
        if not obs:
            args = {
                "customer_ref": self.ref("customer_ref"),
                "product_ref": self.ref("product_ref"),
            }
            return self._read(("r-pricing", PRICING_READ, args))
        p = self._data(obs, PRICING_READ)
        if p is None:
            return FinalAnswer(text="Pricing could not be read; no quotation proposed.")
        price = Decimal(p["list_price"]) - (10 if self._bad_first(ctx) else 0)
        qty = Decimal(3)
        return self._propose(
            CREATE_DRAFT_QUOTATION,
            {
                "customer_ref": p["customer_ref"],
                "product_ref": p["product_ref"],
                "quantity": format_decimal(qty),
                "unit": p["unit"],
                "unit_price": format_decimal(price),
                "currency": p["currency"],
                "subtotal": format_decimal(qty * price),
            },
            "one draft quotation",
        )

    # -- ERP-06 ----------------------------------------------------------------
    def _late_orders(self, ctx: TaskContext, obs: tuple[Observation, ...]) -> DriverStep:
        if not obs:
            return self._read(("r-orders", OPEN_ORDERS_READ, {"as_of": self.ref("as_of")}))
        data = self._data(obs, OPEN_ORDERS_READ)
        if data is None:
            return FinalAnswer(text="Orders could not be read.")
        late = late_orders(OpenOrders.model_validate(data))
        if self._bad_first(ctx):
            late = late[:-1]
        return self._propose(
            LATE_ORDERS_ANSWER,
            {
                "as_of": data["as_of"],
                "late_order_refs": late,
                "summary": f"{len(late)} late orders",
            },
        )

    # -- ERP-07 ----------------------------------------------------------------
    def _crm_lead(self, ctx: TaskContext, obs: tuple[Observation, ...]) -> DriverStep:
        if not obs:
            return self._read(
                ("r-contact", CONTACT_READ, {"contact_ref": self.ref("contact_ref")}),
                ("r-teams", TEAMS_READ, {}),
            )
        owner = self.ref("other_owner_ref") if self._bad_first(ctx) else self.ref("owner_ref")
        return self._propose(
            CREATE_LEAD,
            {
                "name": "Widget restock opportunity",
                "contact_ref": self.ref("contact_ref"),
                "team_ref": self.ref("team_ref"),
                "owner_ref": owner,
                "source_ref": self.ref("source_ref"),
                "expected_revenue": "1500",
            },
            "one new lead",
        )

    # -- ERP-08 ----------------------------------------------------------------
    def _overdue_invoices(self, ctx: TaskContext, obs: tuple[Observation, ...]) -> DriverStep:
        if not obs:
            return self._read(("r-invoices", OPEN_INVOICES_READ, {"as_of": self.ref("as_of")}))
        data = self._data(obs, OPEN_INVOICES_READ)
        if data is None:
            return FinalAnswer(text="Invoices could not be read.")
        refs, totals = overdue(OpenInvoices.model_validate(data))
        rows = [t.model_dump() for t in totals]
        if self._bad_first(ctx) and rows:
            rows[0] = {**rows[0], "total": format_decimal(Decimal(rows[0]["total"]) + 1)}
        return self._propose(
            OVERDUE_INVOICES_ANSWER,
            {
                "as_of": data["as_of"],
                "overdue_invoice_refs": refs,
                "totals": rows,
                "summary": f"{len(refs)} overdue",
            },
        )
