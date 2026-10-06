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
from e_agent.erp.inventory import AVAILABILITY_READ
from e_agent.erp.procurement import (
    CREATE_DRAFT_PO,
    DEMAND_READ,
    OFFERS_READ,
    PURCHASE_ORDER_READ,
)
from e_agent.erp.procurement.api import DraftPurchaseOrder
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
                raise KnownNoEffectError("UNSUPPORTED", "unsupported read")
        except (KeyError, TypeError) as exc:
            raise KnownNoEffectError("INVALID_ARGUMENTS", f"missing {exc}") from exc
        except OdooRejected as exc:
            raise KnownNoEffectError(exc.code, exc.safe_message) from exc
        return Observation(
            request_id=request.request_id, contract_id=request.contract_id, data=data, evidence=ev
        )

    @staticmethod
    def _order(o: Mapping[str, Any], operation_key: str) -> dict[str, Any]:
        return {
            "external_ref": o["external_ref"],
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

    async def execute(
        self, ctx: TaskContext, binding: CapabilityBinding, action: ActionRecord, attempt: int
    ) -> ExecutionReceipt:
        if action.contract_id != CREATE_DRAFT_PO:
            raise KnownNoEffectError("UNSUPPORTED", "unsupported write")
        po = DraftPurchaseOrder.model_validate(action.arguments)
        started = utc_now()
        try:
            raw = await self._call(
                ctx,
                binding.connection_id,
                "create_draft_purchase_order",
                namespace=self._namespace,
                operation_key=action.logical_operation_id,
                payload_digest=action.digest,
                payload={
                    "product_ref": po.product_ref,
                    "supplier_ref": po.supplier_ref,
                    "offer_ref": po.offer_ref,
                    "quantity": po.quantity,
                    "unit_price": po.unit_price,
                    "requested_date": po.requested_date.isoformat(),
                },
            )
        except OdooRejected as exc:  # authoritative: nothing committed
            raise KnownNoEffectError(exc.code, exc.safe_message) from exc
        refs = tuple(o["external_ref"] for o in raw["orders"])
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=attempt,
            status=ReceiptStatus.COMMITTED,
            external_refs=refs,
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
        if not raw["found"] or raw["payload_digest"] != action.digest or not raw["orders"]:
            return None
        now = utc_now()
        return ExecutionReceipt(
            action_id=action.action_id,
            attempt=1,
            status=ReceiptStatus.COMMITTED,
            external_refs=tuple(o["external_ref"] for o in raw["orders"]),
            provider_correlation=f"{self._namespace}:{action.logical_operation_id}",
            started_at=now,
            finished_at=now,
        )

    async def sandbox_info(self, ctx: TaskContext, connection_id: str) -> dict[str, Any]:
        info: dict[str, Any] = await self._call(ctx, connection_id, "sandbox_info")
        return info
