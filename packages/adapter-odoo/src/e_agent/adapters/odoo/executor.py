"""ActionExecutor for Odoo 19 through the e_agent_bridge addon.

Maps provider-neutral capability calls to narrow bridge commands. Provider
refs (``odoo/<model>/<id>``) are opaque to the kernel and domain; amounts and
quantities leave this adapter as canonical decimal strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from e_agent.contracts.action import ActionRecord
from e_agent.contracts.capability import CapabilityBinding
from e_agent.contracts.common import format_decimal, new_id, utc_now
from e_agent.contracts.context import TaskContext
from e_agent.contracts.evidence import Completeness, EvidenceRef
from e_agent.contracts.receipt import ExecutionReceipt, ReceiptStatus
from e_agent.erp.crm import CONTACT_READ, CREATE_LEAD, LEAD_READ, TEAMS_READ
from e_agent.erp.crm.api import CreateLead
from e_agent.erp.inventory import AVAILABILITY_READ
from e_agent.erp.procurement import (
    AMEND_DRAFT_RFQ,
    CREATE_DRAFT_PO,
    DEMAND_READ,
    DRAFT_RFQ_READ,
    OFFERS_READ,
    PURCHASE_ORDER_READ,
)
from e_agent.erp.procurement.api import AmendDraftRfq, DraftPurchaseOrder
from e_agent.erp.receivables import OPEN_INVOICES_READ
from e_agent.erp.sales import (
    CREATE_DRAFT_QUOTATION,
    OPEN_ORDERS_READ,
    PRICING_READ,
    QUOTATION_READ,
)
from e_agent.erp.sales.api import DraftQuotation
from e_agent.sdk.auth import CredentialResolver
from e_agent.sdk.errors import KnownNoEffectError
from e_agent.sdk.ports import Observation, ReadRequest

from .client import OdooJson2Client, OdooRejected

PLUGIN_ID = "odoo19"
BRIDGE = "e_agent.bridge"


def dec(value: Any) -> str:
    """Odoo floats -> canonical decimal strings (via repr, never binary float math)."""
    return format_decimal(Decimal(str(value)))


class OdooExecutor:
    def __init__(
        self, client: OdooJson2Client, credentials: CredentialResolver, namespace: str
    ) -> None:
        self._client = client
        self._credentials = credentials
        self._namespace = namespace

    def supports(self, binding: CapabilityBinding) -> bool:
        return binding.plugin_id == PLUGIN_ID

    async def _call(self, ctx: TaskContext, connection_id: str, method: str, **kw: Any) -> Any:
        auth = await self._credentials.context_for(ctx, connection_id)
        return await self._client.call(auth, BRIDGE, method, **kw)

    def _evidence(
        self,
        ctx: TaskContext,
        source: str,
        locator: str,
        revision: str | None,
        complete: bool = True,
    ) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=new_id("ev"),
            tenant_id=ctx.tenant_id,
            source=f"odoo19:{source}",
            locator=locator,
            revision=revision,
            observed_at=utc_now(),
            scope=ctx.tenant_id,
            environment="live",
            completeness=Completeness.COMPLETE if complete else Completeness.UNKNOWN,
        )

    async def read(
        self, ctx: TaskContext, binding: CapabilityBinding, request: ReadRequest
    ) -> Observation:
        args = request.arguments
        cid = binding.connection_id
        data: dict[str, Any]
        try:
            if request.contract_id == DEMAND_READ:
                raw = await self._call(ctx, cid, "read_demand", demand_ref=args["demand_ref"])
                data = (
                    {}
                    if not raw["found"]
                    else {
                        "demand_ref": raw["demand_ref"],
                        "product_ref": raw["product_ref"],
                        "quantity": dec(raw["quantity"]),
                        "unit": raw["unit"],
                        "requested_date": raw["requested_date"],
                        "budget": dec(raw["budget"]),
                        "currency": raw["currency"],
                    }
                )
                ev = self._evidence(
                    ctx,
                    "e_agent.demand",
                    str(args["demand_ref"]),
                    raw.get("revision"),
                    raw["found"],
                )
            elif request.contract_id == AVAILABILITY_READ:
                raw = await self._call(
                    ctx, cid, "read_availability", product_ref=args["product_ref"]
                )
                data = (
                    {}
                    if not raw["found"]
                    else {
                        "product_ref": raw["product_ref"],
                        "available": dec(raw["available"]),
                        "inbound": dec(raw["inbound"]),
                        "unit": raw["unit"],
                    }
                )
                ev = self._evidence(
                    ctx, "stock.quant", str(args["product_ref"]), raw.get("revision"), raw["found"]
                )
            elif request.contract_id == OFFERS_READ:
                raw = await self._call(ctx, cid, "read_offers", product_ref=args["product_ref"])
                data = {
                    "product_ref": raw.get("product_ref", args["product_ref"]),
                    "offers": [{**o, "unit_price": dec(o["unit_price"])} for o in raw["offers"]],
                }
                ev = self._evidence(
                    ctx,
                    "product.supplierinfo",
                    str(args["product_ref"]),
                    raw.get("revision"),
                    raw["found"],
                )
            elif request.contract_id == PURCHASE_ORDER_READ:
                raw = await self._call(
                    ctx,
                    cid,
                    "read_operation",
                    namespace=self._namespace,
                    operation_key=args["operation_key"],
                )
                data = {"orders": [self._order(o, args["operation_key"]) for o in raw["orders"]]}
                ev = self._evidence(
                    ctx, "purchase.order", str(args["operation_key"]), str(len(raw["orders"]))
                )
            else:
                data, ev = await self._read_more(ctx, cid, request.contract_id, args)
        except (KeyError, TypeError) as exc:
            raise KnownNoEffectError("INVALID_ARGUMENTS", f"missing {exc}") from exc
        except OdooRejected as exc:
            raise KnownNoEffectError(exc.code, exc.safe_message) from exc
        return Observation(
            request_id=request.request_id, contract_id=request.contract_id, data=data, evidence=ev
        )

    async def _read_more(
        self, ctx: TaskContext, cid: str, contract_id: str, args: Mapping[str, Any]
    ) -> tuple[dict[str, Any], EvidenceRef]:
        """ERP-04..08 reads. Odoo floats leave as canonical decimal strings."""
        if contract_id == DRAFT_RFQ_READ:
            raw = await self._call(
                ctx, cid, "read_draft_rfq", purchase_order_ref=args["purchase_order_ref"]
            )
            data = (
                {}
                if not raw["found"]
                else {
                    k: (dec(v) if k in {"quantity", "unit_price"} else v)
                    for k, v in raw.items()
                    if k != "found"
                }
            )
            rev = raw.get("revision")
            return data, self._evidence(
                ctx, "purchase.order", str(args["purchase_order_ref"]), rev, raw["found"]
            )
        if contract_id == PRICING_READ:
            raw = await self._call(
                ctx,
                cid,
                "read_pricing",
                customer_ref=args["customer_ref"],
                product_ref=args["product_ref"],
            )
            data = (
                {}
                if not raw["found"]
                else {
                    **{k: v for k, v in raw.items() if k != "found"},
                    "list_price": dec(raw["list_price"]),
                }
            )
            loc = f"{args['customer_ref']}|{args['product_ref']}"
            return data, self._evidence(ctx, "product.pricelist", loc, None, raw["found"])
        if contract_id in (QUOTATION_READ, LEAD_READ):
            key = str(args["operation_key"])
            raw = await self._call(
                ctx, cid, "read_operation", namespace=self._namespace, operation_key=key
            )
            if contract_id == QUOTATION_READ:
                rows = [
                    {
                        **q,
                        "operation_key": key,
                        **{f: dec(q[f]) for f in ("quantity", "unit_price", "subtotal")},
                    }
                    for q in raw.get("quotations", [])
                ]
                return {"quotations": rows}, self._evidence(ctx, "sale.order", key, str(len(rows)))
            leads = [
                {**ld, "operation_key": key, "expected_revenue": dec(ld["expected_revenue"])}
                for ld in raw.get("leads", [])
            ]
            return {"leads": leads}, self._evidence(ctx, "crm.lead", key, str(len(leads)))
        if contract_id == OPEN_ORDERS_READ:
            raw = await self._call(ctx, cid, "read_open_orders", as_of=str(args["as_of"]))
            data = {"as_of": raw["as_of"], "orders": raw["orders"]}
            return data, self._evidence(
                ctx, "sale.order", f"open@{raw['as_of']}", None, raw["complete"]
            )
        if contract_id == CONTACT_READ:
            raw = await self._call(ctx, cid, "read_contact", contact_ref=args["contact_ref"])
            data = {} if not raw["found"] else {k: v for k, v in raw.items() if k != "found"}
            return data, self._evidence(
                ctx, "res.partner", str(args["contact_ref"]), None, raw["found"]
            )
        if contract_id == TEAMS_READ:
            raw = await self._call(ctx, cid, "read_teams")
            return raw, self._evidence(ctx, "crm.team", "teams", None)
        if contract_id == OPEN_INVOICES_READ:
            raw = await self._call(ctx, cid, "read_open_invoices", as_of=str(args["as_of"]))
            data = {
                "as_of": raw["as_of"],
                "company": raw["company"],
                "invoices": [{**i, "residual": dec(i["residual"])} for i in raw["invoices"]],
            }
            return data, self._evidence(
                ctx, "account.move", f"open@{raw['as_of']}", None, raw["complete"]
            )
        raise KnownNoEffectError("UNSUPPORTED", "unsupported read")

    @staticmethod
    def _order(o: Mapping[str, Any], operation_key: str) -> dict[str, Any]:
        return {
            "external_ref": o["external_ref"],
            "purchase_order_ref": o.get("purchase_order_ref"),
            "requested_date": o.get("requested_date"),
            "operation_key": operation_key,
            "state": o["state"],
            "product_ref": o["product_ref"],
            "supplier_ref": o["supplier_ref"],
            "quantity": dec(o["quantity"]),
            "unit": o["unit"],
            "currency": o["currency"],
            "unit_price": dec(o["unit_price"]),
            "subtotal": dec(o["subtotal"]),
        }

    def _command(self, action: ActionRecord) -> tuple[str, dict[str, Any]]:
        """Map a write capability to one narrow bridge command and its payload."""
        cid = action.contract_id
        if cid == CREATE_DRAFT_PO:
            po = DraftPurchaseOrder.model_validate(action.arguments)
            return "create_draft_purchase_order", {
                "product_ref": po.product_ref,
                "supplier_ref": po.supplier_ref,
                "offer_ref": po.offer_ref,
                "quantity": po.quantity,
                "unit_price": po.unit_price,
                "requested_date": po.requested_date.isoformat(),
            }
        if cid == AMEND_DRAFT_RFQ:
            amend = AmendDraftRfq.model_validate(action.arguments)
            return "amend_draft_purchase_order", amend.model_dump(mode="json")
        if cid == CREATE_DRAFT_QUOTATION:
            q = DraftQuotation.model_validate(action.arguments)
            return "create_draft_quotation", {
                "customer_ref": q.customer_ref,
                "product_ref": q.product_ref,
                "quantity": q.quantity,
                "unit_price": q.unit_price,
            }
        if cid == CREATE_LEAD:
            return "create_lead", CreateLead.model_validate(action.arguments).model_dump(
                mode="json"
            )
        raise KnownNoEffectError("UNSUPPORTED", "unsupported write")

    @staticmethod
    def _result_refs(raw: Mapping[str, Any]) -> tuple[str, ...]:
        rows = [*raw.get("orders", []), *raw.get("quotations", []), *raw.get("leads", [])]
        return tuple(r["external_ref"] for r in rows)

    async def execute(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord, attempt: int
    ) -> ExecutionReceipt:
        command, payload = self._command(action)
        started = utc_now()
        try:
            raw = await self._call(
                ctx,
                binding.connection_id,
                command,
                namespace=self._namespace,
                operation_key=action.logical_operation_id,
                payload_digest=action.digest,
                payload=payload,
            )
        except OdooRejected as exc:  # authoritative: nothing committed
            raise KnownNoEffectError(exc.code, exc.safe_message) from exc
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=attempt,
            status=ReceiptStatus.COMMITTED,
            external_refs=self._result_refs(raw),
            provider_correlation=f"{self._namespace}:{action.logical_operation_id}",
            started_at=started,
            finished_at=utc_now(),
        )

    async def reconcile(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord
    ) -> ExecutionReceipt | None:
        raw = await self._call(
            ctx,
            binding.connection_id,
            "read_operation",
            namespace=self._namespace,
            operation_key=action.logical_operation_id,
        )
        if not raw["found"] or raw["payload_digest"] != action.digest:
            return None
        refs = self._result_refs(raw)
        if not refs:
            return None
        now = utc_now()
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=1,
            status=ReceiptStatus.COMMITTED,
            external_refs=refs,
            provider_correlation=f"{self._namespace}:{action.logical_operation_id}",
            started_at=now,
            finished_at=now,
        )

    async def sandbox_info(self, ctx: TaskContext, connection_id: str) -> dict[str, Any]:
        info: dict[str, Any] = await self._call(ctx, connection_id, "sandbox_info")
        return info
