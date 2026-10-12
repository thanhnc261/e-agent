"""Bridge commands called through Odoo 19 JSON-2 by the e-agent Odoo adapter.

Every method checks the integration group and works in the caller's current
company. Write commands are idempotent per operation key: same key + same
payload digest returns the stored result; a different digest is a conflict.
"""

import datetime
import re

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

    def _check_target(self):
        """Fail closed inside the same ERP transaction as the scoped read or mutation."""
        self._check()
        expected = self.env.context.get("e_agent_target")
        if not isinstance(expected, dict) or not all(
            expected.get(k) for k in ("database", "company_id", "sandbox_marker", "bridge_version")
        ):
            raise UserError("E_AGENT_TARGET_REQUIRED: explicit synthetic sandbox identity required")
        module = self.env["ir.module.module"].sudo().search([("name", "=", "e_agent_bridge")])
        actual = {
            "database": self.env.cr.dbname,
            "company_id": str(self.env.company.id),
            "sandbox_marker": self.env["ir.config_parameter"].sudo().get_param(MARKER),
            "bridge_version": module.latest_version,
        }
        if actual != expected:
            raise UserError("E_AGENT_TARGET_MISMATCH: sandbox identity changed")

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
            "requested_date": fields.Date.to_string(line.date_planned.date()) if line else None,
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
            "database": self.env.cr.dbname,
            "company_id": str(self.env.company.id),
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
        self._check_target()
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
        self._check_target()
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
        self._check_target()
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
        self._check_target()
        op = self._operation(namespace, operation_key)
        if not op:
            return {"found": False, "orders": []}
        orders = []
        if op.result_model == "purchase.order" and op.result_id:
            po = self.env["purchase.order"].browse(op.result_id).exists()
            if po:
                orders.append(self._po_view(po))
        return {
            "found": True,
            "payload_digest": op.payload_digest,
            "command": op.command,
            "orders": orders,
        }

    # ------------------------------------------------------------- writes
    @api.model
    def create_draft_purchase_order(self, namespace, operation_key, payload_digest, payload):
        """Reserve the operation key and create ONE draft PO in the same transaction."""
        self._check_target()
        existing = self._operation(namespace, operation_key)
        if existing:
            if (
                existing.payload_digest != payload_digest
                or existing.command != "create_draft_purchase_order"
            ):
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
        self._check_target()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError("E_AGENT_FORBIDDEN: sandbox tools need an administrator")
        if not self.env["ir.config_parameter"].sudo().get_param(MARKER):
            raise UserError("E_AGENT_NOT_SANDBOX: e_agent.sandbox_marker is not set")

    def _fixture(self, namespace, *, create=False):
        if not isinstance(namespace, str) or not re.fullmatch(
            r"e-agent-[A-Za-z0-9_-]{1,80}", namespace
        ):
            raise UserError("E_AGENT_INVALID: explicit e-agent synthetic namespace required")
        fixture = (
            self.env["e_agent.fixture"]
            .sudo()
            .search(
                [("namespace", "=", namespace), ("company_id", "=", self.env.company.id)], limit=1
            )
        )
        if fixture:
            return fixture
        if not create:
            raise UserError("E_AGENT_RESET_REFUSED: no owned fixture inventory")
        collisions = [
            ("res.partner", [("ref", "=like", namespace + ":%")]),
            ("product.product", [("default_code", "=like", namespace + ":%")]),
            ("e_agent.demand", [("namespace", "=", namespace)]),
            ("sale.order", [("client_order_ref", "=", namespace)]),
            ("account.move", [("ref", "=", namespace)]),
            ("purchase.order", [("origin", "=", f"e-agent-seed:{namespace}")]),
        ]
        if any(
            self.env[model].sudo().with_context(active_test=False).search(domain, limit=1)
            for model, domain in collisions
        ):
            raise UserError("E_AGENT_RESET_REFUSED: namespace has unowned records")
        return (
            self.env["e_agent.fixture"]
            .sudo()
            .create({"namespace": namespace, "company_id": self.env.company.id})
        )

    def _seed_lookup(self, fixture, model, domain):
        rows = self.env[model].with_context(active_test=False).search(domain, limit=2)
        owned = (fixture.inventory or {}).get(model, [])
        if len(rows) > 1 or any(row.id not in owned for row in rows):
            raise UserError("E_AGENT_RESET_REFUSED: seed would adopt an unowned record")
        return rows

    def _remember_fixture(self, fixture, records, references=None):
        inventory = dict(fixture.inventory or {})
        for model, rows in records.items():
            inventory[model] = sorted(set(inventory.get(model, [])) | set(rows.ids))
        values = {"inventory": inventory}
        if references is not None:
            values["references"] = {**(fixture.references or {}), **references}
        fixture.write(values)

    def _fixture_remaining(self, fixture):
        return {
            model: self.env[model].sudo().with_context(active_test=False).browse(ids).exists().ids
            for model, ids in (fixture.inventory or {}).items()
        }

    @api.model
    def sandbox_seed(self, namespace, scenario="valid"):
        """Idempotently create the synthetic procurement fixture (MVP design §2)."""
        self._require_sandbox()
        fixture = self._fixture(namespace, create=True)
        company = self.env.company
        partner = self.env["res.partner"]
        approved = self._seed_lookup(
            fixture, "res.partner", [("ref", "=", f"{namespace}:approved-co")]
        ) or partner.create(
            {"name": "E-Agent Approved Co", "ref": f"{namespace}:approved-co", "is_company": True}
        )
        unvetted = self._seed_lookup(
            fixture, "res.partner", [("ref", "=", f"{namespace}:unvetted-co")]
        ) or partner.create(
            {"name": "E-Agent Unvetted Co", "ref": f"{namespace}:unvetted-co", "is_company": True}
        )
        product = self._seed_lookup(
            fixture, "product.product", [("default_code", "=", f"{namespace}:widget-a")]
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
        (approved | unvetted).write({"active": True})
        tmpl = product.product_tmpl_id
        tmpl.active = True
        self.env["product.supplierinfo"].browse(
            (fixture.inventory or {}).get("product.supplierinfo", [])
        ).exists().unlink()
        sellers = self.env["product.supplierinfo"].create(
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
        prior_moves = self.env["stock.move"].search([("product_id", "=", product.id)])
        prior_quants = self.env["stock.quant"].search([("product_id", "=", product.id)])
        available = {"zero-shortage": 12.0}.get(scenario, 5.0)
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        owned_quants = (fixture.inventory or {}).get("stock.quant", [])
        if any(
            quant.location_id == warehouse.lot_stock_id and quant.id not in owned_quants
            for quant in prior_quants
        ):
            raise UserError("E_AGENT_RESET_REFUSED: seed would change an unowned stock quant")
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": product.id,
                "location_id": warehouse.lot_stock_id.id,
                "inventory_quantity": available,
            }
        ).action_apply_inventory()
        demand = self._seed_lookup(
            fixture, "e_agent.demand", [("namespace", "=", namespace), ("name", "=", "D-001")]
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
        references = {
            "demand_ref": _ref(demand),
            "product_ref": _ref(product),
            "approved_supplier_ref": _ref(approved),
            "unvetted_supplier_ref": _ref(unvetted),
        }
        self._remember_fixture(
            fixture,
            {
                "res.partner": approved | unvetted,
                "product.product": product,
                "product.template": tmpl,
                "product.supplierinfo": sellers,
                "e_agent.demand": demand,
                "stock.quant": self.env["stock.quant"].search([("product_id", "=", product.id)])
                - prior_quants,
                "stock.move": self.env["stock.move"].search([("product_id", "=", product.id)])
                - prior_moves,
            },
            references,
        )
        return references

    @api.model
    def sandbox_reset(self, namespace):
        """Reset owned synthetic effects and report retained audit/source records."""
        self._require_sandbox()
        fixture = self._fixture(namespace)
        ops = (
            self.env["e_agent.operation"]
            .sudo()
            .search([("namespace", "=", namespace), ("company_id", "=", self.env.company.id)])
        )
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
        inventory = fixture.inventory or {}
        quants = self.env["stock.quant"].browse(inventory.get("stock.quant", [])).exists()
        internal = quants.filtered(lambda q: q.location_id.usage == "internal")
        if internal:
            internal.with_context(inventory_mode=True).write({"inventory_quantity": 0})
            internal.action_apply_inventory()
        for model in ("e_agent.demand", "product.supplierinfo"):
            self.env[model].browse(inventory.get(model, [])).exists().unlink()
        for model in ("product.template", "res.partner", "crm.team", "utm.source"):
            records = (
                self.env[model]
                .with_context(active_test=False)
                .browse(inventory.get(model, []))
                .exists()
            )
            if "active" in records._fields:
                records.write({"active": False})
        fixture.references = {}
        return {
            "removed_orders": removed,
            "owned_inventory": inventory,
            "remaining_records": self._fixture_remaining(fixture),
            "retention": "cancelled audit records and archived synthetic sources retained",
        }
