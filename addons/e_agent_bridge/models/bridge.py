"""Bridge commands called through Odoo 19 JSON-2 by the e-agent Odoo adapter.

Every method checks the integration group and works in the caller's current
company. Write commands are idempotent per operation key: same key + same
payload digest returns the stored result; a different digest is a conflict.
"""

import datetime

import psycopg2
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

GROUP = "e_agent_bridge.group_e_agent_integration"
MARKER = "e_agent.sandbox_marker"


def _ref(record):
    return f"odoo/{record._name}/{record.id}"


class EAgentBridge(models.AbstractModel):
    _name = "e_agent.bridge"
    _description = "e-agent bridge commands"

    # ------------------------------------------------------------ helpers
    def _check(self):
        if not self.env.user.has_group(GROUP):
            raise AccessError("E_AGENT_FORBIDDEN: user is not an e-agent integration user")

    def _id(self, ref, model):
        prefix = f"odoo/{model}/"
        if not isinstance(ref, str) or not ref.startswith(prefix):
            raise UserError(f"E_AGENT_INVALID_REF: expected {prefix}<id>")
        try:
            return int(ref[len(prefix) :])
        except ValueError as exc:
            raise UserError("E_AGENT_INVALID_REF") from exc

    def _operation(self, namespace, operation_key):
        return (
            self.env["e_agent.operation"]
            .sudo()
            .search(
                [
                    ("namespace", "=", namespace),
                    ("company_id", "=", self.env.company.id),
                    ("operation_key", "=", operation_key),
                ],
                limit=1,
            )
        )

    def _po_view(self, po):
        line = po.order_line[:1]
        return {
            "external_ref": po.name,
            "purchase_order_ref": _ref(po),
            "state": "draft" if po.state == "draft" else po.state,
            "product_ref": _ref(line.product_id) if line else None,
            "supplier_ref": _ref(po.partner_id),
            "quantity": line.product_qty if line else 0.0,
            "unit": line.product_uom_id.name if line else None,
            "currency": po.currency_id.name,
            "unit_price": line.price_unit if line else 0.0,
            "subtotal": line.price_subtotal if line else 0.0,
            "line_count": len(po.order_line),
        }

    # -------------------------------------------------------------- reads
    @api.model
    @api.readonly
    def sandbox_info(self):
        self._check()
        param = self.env["ir.config_parameter"].sudo().get_param(MARKER)
        module = self.env["ir.module.module"].sudo().search([("name", "=", "e_agent_bridge")])
        return {
            "sandbox_marker": param or None,
            "bridge_version": module.latest_version,
            "company": self.env.company.name,
            "server_version": self.env["ir.module.module"]
            .sudo()
            .search([("name", "=", "base")])
            .latest_version,
        }

    @api.model
    @api.readonly
    def read_demand(self, demand_ref):
        self._check()
        demand = self.env["e_agent.demand"].search(
            [
                ("id", "=", self._id(demand_ref, "e_agent.demand")),
                ("company_id", "=", self.env.company.id),
            ]
        )
        if not demand:
            return {"found": False}
        return {
            "found": True,
            "demand_ref": _ref(demand),
            "product_ref": _ref(demand.product_id),
            "quantity": demand.quantity,
            "unit": demand.product_id.uom_id.name,
            "requested_date": fields.Date.to_string(demand.requested_date),
            "budget": demand.budget,
            "currency": demand.currency_id.name,
            "revision": fields.Datetime.to_string(demand.write_date),
        }

    @api.model
    @api.readonly
    def read_availability(self, product_ref):
        self._check()
        product = self.env["product.product"].browse(self._id(product_ref, "product.product"))
        product = product.with_company(self.env.company).exists()
        if not product:
            return {"found": False}
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("company_id", "=", self.env.company.id),
                ("location_id.usage", "=", "internal"),
            ]
        )
        return {
            "found": True,
            "product_ref": _ref(product),
            "available": product.qty_available,
            "inbound": product.incoming_qty,
            "unit": product.uom_id.name,
            "revision": max([fields.Datetime.to_string(q.write_date) for q in quants] or ["none"]),
        }

    @api.model
    @api.readonly
    def read_offers(self, product_ref):
        self._check()
        product = self.env["product.product"].browse(self._id(product_ref, "product.product"))
        product = product.exists()
        if not product:
            return {"found": False, "offers": []}
        today = fields.Date.context_today(self)
        infos = product.product_tmpl_id.seller_ids.filtered(
            lambda s: s.company_id in (self.env.company, self.env["res.company"])
        )
        offers = [
            {
                "offer_ref": _ref(s),
                "supplier_ref": _ref(s.partner_id),
                "product_ref": _ref(product),
                "unit_price": s.price,
                "currency": s.currency_id.name,
                "unit": s.product_uom_id.name or product.uom_id.name,
                "approved": bool(s.e_agent_approved),
                "delivery_date": fields.Date.to_string(today + datetime.timedelta(days=s.delay)),
            }
            for s in infos
        ]
        revision = max([fields.Datetime.to_string(s.write_date) for s in infos] or ["none"])
        return {"found": True, "product_ref": _ref(product), "offers": offers, "revision": revision}

    @api.model
    @api.readonly
    def read_operation(self, namespace, operation_key):
        """Reconciliation and verification read-back: by operation key, never fuzzy."""
        self._check()
        op = self._operation(namespace, operation_key)
        if not op:
            return {"found": False, "orders": []}
        orders = []
        if op.result_model == "purchase.order" and op.result_id:
            po = self.env["purchase.order"].browse(op.result_id).exists()
            if po:
                orders.append(self._po_view(po))
        return {"found": True, "payload_digest": op.payload_digest, "orders": orders}

    # ------------------------------------------------------------- writes
    @api.model
    def create_draft_purchase_order(self, namespace, operation_key, payload_digest, payload):
        """Reserve the operation key and create ONE draft PO in the same transaction."""
        self._check()
        existing = self._operation(namespace, operation_key)
        if existing:
            if existing.payload_digest != payload_digest:
                raise UserError("E_AGENT_CONFLICT: operation key reused with a different payload")
            return {"status": "existing", **self.read_operation(namespace, operation_key)}
        try:
            with self.env.cr.savepoint():
                op = (
                    self.env["e_agent.operation"]
                    .sudo()
                    .create(
                        {
                            "namespace": namespace,
                            "company_id": self.env.company.id,
                            "operation_key": operation_key,
                            "payload_digest": payload_digest,
                            "command": "create_draft_purchase_order",
                        }
                    )
                )
                op.flush_recordset()
        except psycopg2.errors.UniqueViolation as exc:
            raise UserError("E_AGENT_DUPLICATE_IN_FLIGHT: retry reconciliation") from exc

        product = (
            self.env["product.product"]
            .browse(self._id(payload["product_ref"], "product.product"))
            .exists()
        )
        partner = (
            self.env["res.partner"]
            .browse(self._id(payload["supplier_ref"], "res.partner"))
            .exists()
        )
        offer = (
            self.env["product.supplierinfo"]
            .browse(self._id(payload["offer_ref"], "product.supplierinfo"))
            .exists()
        )
        quantity = float(payload["quantity"])
        if not (product and partner and offer):
            raise UserError("E_AGENT_INVALID: unknown product, supplier or offer")
        if offer.partner_id != partner or offer.product_tmpl_id != product.product_tmpl_id:
            raise UserError("E_AGENT_INVALID: offer does not match supplier and product")
        if quantity <= 0:
            raise UserError("E_AGENT_INVALID: quantity must be positive")
        planned = fields.Datetime.to_datetime(payload["requested_date"])
        po = self.env["purchase.order"].create(
            {
                "partner_id": partner.id,
                "company_id": self.env.company.id,
                "origin": f"e-agent:{namespace}:{operation_key}",
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_qty": quantity,
                            "product_uom_id": product.uom_id.id,
                            "price_unit": float(payload["unit_price"]),
                            "date_planned": planned,
                            "tax_ids": [(6, 0, [])],
                        },
                    )
                ],
            }
        )
        if po.state != "draft":
            raise UserError("E_AGENT_INVALID: purchase order left draft state")
        op.write({"result_model": "purchase.order", "result_id": po.id})
        return {"status": "created", **self.read_operation(namespace, operation_key)}

    # ------------------------------------------------------- sandbox tools
    def _require_sandbox(self):
        self._check()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError("E_AGENT_FORBIDDEN: sandbox tools need an administrator")
        if not self.env["ir.config_parameter"].sudo().get_param(MARKER):
            raise UserError("E_AGENT_NOT_SANDBOX: e_agent.sandbox_marker is not set")

    @api.model
    def sandbox_seed(self, namespace, scenario="valid"):
        """Idempotently create the synthetic procurement fixture (MVP design §2)."""
        self._require_sandbox()
        company = self.env.company
        partner = self.env["res.partner"]
        approved = partner.search(
            [("ref", "=", f"{namespace}:approved-co")], limit=1
        ) or partner.create(
            {"name": "E-Agent Approved Co", "ref": f"{namespace}:approved-co", "is_company": True}
        )
        unvetted = partner.search(
            [("ref", "=", f"{namespace}:unvetted-co")], limit=1
        ) or partner.create(
            {"name": "E-Agent Unvetted Co", "ref": f"{namespace}:unvetted-co", "is_company": True}
        )
        product = self.env["product.product"].search(
            [("default_code", "=", f"{namespace}:widget-a")], limit=1
        )
        if not product:
            product = self.env["product.product"].create(
                {
                    "name": "E-Agent Widget A",
                    "default_code": f"{namespace}:widget-a",
                    "type": "consu",
                    "is_storable": True,
                    "supplier_taxes_id": [(6, 0, [])],
                    "taxes_id": [(6, 0, [])],
                }
            )
        tmpl = product.product_tmpl_id
        tmpl.seller_ids.unlink()
        self.env["product.supplierinfo"].create(
            [
                {
                    "partner_id": approved.id,
                    "product_tmpl_id": tmpl.id,
                    "price": 100.0,
                    "delay": 7,
                    "e_agent_approved": True,
                    "company_id": company.id,
                },
                {
                    "partner_id": unvetted.id,
                    "product_tmpl_id": tmpl.id,
                    "price": 80.0,
                    "delay": 5,
                    "e_agent_approved": False,
                    "company_id": company.id,
                },
            ]
        )
        available = {"zero-shortage": 12.0}.get(scenario, 5.0)
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": product.id,
                "location_id": warehouse.lot_stock_id.id,
                "inventory_quantity": available,
            }
        ).action_apply_inventory()
        demand = self.env["e_agent.demand"].search(
            [("namespace", "=", namespace), ("name", "=", "D-001")], limit=1
        )
        values = {
            "name": "D-001",
            "namespace": namespace,
            "product_id": product.id,
            "quantity": 12.0,
            "budget": {"over-budget": 500.0}.get(scenario, 1000.0),
            "requested_date": fields.Date.context_today(self) + datetime.timedelta(days=14),
        }
        demand = (
            demand.write(values) and demand if demand else self.env["e_agent.demand"].create(values)
        )
        return {
            "demand_ref": _ref(demand),
            "product_ref": _ref(product),
            "approved_supplier_ref": _ref(approved),
            "unvetted_supplier_ref": _ref(unvetted),
        }

    @api.model
    def sandbox_reset(self, namespace):
        """Remove draft POs and ledger rows created in this namespace only."""
        self._require_sandbox()
        ops = self.env["e_agent.operation"].sudo().search([("namespace", "=", namespace)])
        pos = (
            self.env["purchase.order"]
            .browse([o.result_id for o in ops if o.result_model == "purchase.order"])
            .exists()
        )
        drafts = pos.filtered(lambda p: p.state in ("draft", "cancel"))
        if drafts != pos:
            raise UserError("E_AGENT_RESET_REFUSED: non-draft order in namespace")
        removed = len(drafts)
        drafts.filtered(lambda p: p.state == "draft").button_cancel()  # Odoo 19: cancel first
        drafts.unlink()
        ops.unlink()
        return {"removed_orders": removed}
