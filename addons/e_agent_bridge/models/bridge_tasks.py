"""Bridge commands for ERP-04..08 (same rules as bridge.py: narrow, company-scoped,
one transaction per write, idempotent per operation key, draft-only effects)."""

import datetime
import hashlib

import psycopg2
from odoo import api, fields, models
from odoo.exceptions import UserError

from .bridge import _ref


def _date(value):
    return fields.Date.to_string(value.date() if isinstance(value, datetime.datetime) else value)


DELIVERY = {"full": "delivered", False: "delivered", "partial": "partial", "started": "partial"}


class EAgentBridgeTasks(models.AbstractModel):
    _inherit = "e_agent.bridge"

    # ------------------------------------------------------------ ledger
    def _reserve(self, namespace, operation_key, payload_digest, command):
        """Reserve the key in this transaction, or return the existing row (or conflict)."""
        existing = self._operation(namespace, operation_key)
        if existing:
            if existing.payload_digest != payload_digest:
                raise UserError("E_AGENT_CONFLICT: operation key reused with a different payload")
            return existing, False
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
                            "command": command,
                        }
                    )
                )
                op.flush_recordset()
        except psycopg2.errors.UniqueViolation as exc:
            raise UserError("E_AGENT_DUPLICATE_IN_FLIGHT: retry reconciliation") from exc
        return op, True

    @api.model
    @api.readonly
    def read_operation(self, namespace, operation_key):
        result = super().read_operation(namespace, operation_key)
        op = self._operation(namespace, operation_key)
        if not op or not op.result_id:
            return {**result, "quotations": [], "leads": []}
        record = (
            self.env[op.result_model].browse(op.result_id).exists() if op.result_model else None
        )
        result["quotations"] = (
            [self._quotation_view(record)] if record and op.result_model == "sale.order" else []
        )
        result["leads"] = (
            [self._lead_view(record)] if record and op.result_model == "crm.lead" else []
        )
        return result

    # ------------------------------------------------------- ERP-04 RFQ amend
    def _rfq(self, purchase_order_ref):
        po = self.env["purchase.order"].search(
            [
                ("id", "=", self._id(purchase_order_ref, "purchase.order")),
                ("company_id", "=", self.env.company.id),
            ]
        )
        return po

    @staticmethod
    def _revision(po):
        line = po.order_line[:1]
        basis = "|".join(
            str(v)
            for v in (
                po.write_date and po.write_date.isoformat(),
                po.state,
                line.product_qty,
                line.date_planned,
                line.price_unit,
                len(po.order_line),
            )
        )
        return hashlib.sha256(basis.encode()).hexdigest()[:16]

    @api.model
    @api.readonly
    def read_draft_rfq(self, purchase_order_ref):
        self._check()
        po = self._rfq(purchase_order_ref)
        if not po or len(po.order_line) != 1:
            return {"found": False}
        line = po.order_line
        return {
            "found": True,
            "purchase_order_ref": _ref(po),
            "external_ref": po.name,
            "state": po.state,
            "revision": self._revision(po),
            "supplier_ref": _ref(po.partner_id),
            "product_ref": _ref(line.product_id),
            "quantity": line.product_qty,
            "unit": line.product_uom_id.name,
            "unit_price": line.price_unit,
            "currency": po.currency_id.name,
            "requested_date": _date(line.date_planned),
        }

    @api.model
    def amend_draft_purchase_order(self, namespace, operation_key, payload_digest, payload):
        """Change quantity/date of a one-line draft RFQ at the revision that was read."""
        self._check()
        op, created = self._reserve(
            namespace, operation_key, payload_digest, "amend_draft_purchase_order"
        )
        if not created:
            return {"status": "existing", **self.read_operation(namespace, operation_key)}
        po = self._rfq(payload["purchase_order_ref"])
        if not po or len(po.order_line) != 1:
            raise UserError("E_AGENT_INVALID: unknown RFQ or not a single-line RFQ")
        if po.state != "draft":
            raise UserError("E_AGENT_INVALID: only draft RFQs can be amended")
        if self._revision(po) != payload["expected_revision"]:
            raise UserError("E_AGENT_STALE: the RFQ changed since it was read")
        quantity = float(payload["quantity"])
        if quantity <= 0:
            raise UserError("E_AGENT_INVALID: quantity must be positive")
        line = po.order_line
        po.write(
            {
                "order_line": [
                    (
                        1,
                        line.id,
                        {
                            "product_qty": quantity,
                            "date_planned": fields.Datetime.to_datetime(payload["requested_date"]),
                        },
                    )
                ]
            }
        )
        op.write({"result_model": "purchase.order", "result_id": po.id})
        return {"status": "created", **self.read_operation(namespace, operation_key)}

    # ------------------------------------------------------- ERP-05 quotation
    @api.model
    @api.readonly
    def read_pricing(self, customer_ref, product_ref):
        self._check()
        partner = (
            self.env["res.partner"]
            .with_context(active_test=False)
            .browse(self._id(customer_ref, "res.partner"))
            .exists()
        )
        product = (
            self.env["product.product"]
            .with_context(active_test=False)
            .browse(self._id(product_ref, "product.product"))
            .exists()
        )
        if not partner or not product:
            return {"found": False}
        return {
            "found": True,
            "customer_ref": _ref(partner),
            "customer_name": partner.display_name,
            "customer_active": bool(partner.active),
            "product_ref": _ref(product),
            "product_saleable": bool(product.active and product.sale_ok),
            "list_price": product.lst_price,
            "currency": self.env.company.currency_id.name,
            "unit": product.uom_id.name,
        }

    def _quotation_view(self, so):
        line = so.order_line[:1]
        return {
            "external_ref": so.name,
            "state": "draft" if so.state == "draft" else so.state,
            "sent": so.state == "sent",
            "customer_ref": _ref(so.partner_id),
            "product_ref": _ref(line.product_id) if line else None,
            "quantity": line.product_uom_qty if line else 0.0,
            "unit": line.product_uom_id.name if line else None,
            "unit_price": line.price_unit if line else 0.0,
            "currency": so.currency_id.name,
            "subtotal": line.price_subtotal if line else 0.0,
        }

    @api.model
    def create_draft_quotation(self, namespace, operation_key, payload_digest, payload):
        """One draft quotation; never confirmed, emailed or delivered."""
        self._check()
        op, created = self._reserve(
            namespace, operation_key, payload_digest, "create_draft_quotation"
        )
        if not created:
            return {"status": "existing", **self.read_operation(namespace, operation_key)}
        partner = (
            self.env["res.partner"]
            .browse(self._id(payload["customer_ref"], "res.partner"))
            .exists()
        )
        product = (
            self.env["product.product"]
            .browse(self._id(payload["product_ref"], "product.product"))
            .exists()
        )
        if not partner or not partner.active:
            raise UserError("E_AGENT_INVALID: customer is unknown or archived")
        if not product or not product.sale_ok:
            raise UserError("E_AGENT_INVALID: product cannot be sold")
        quantity = float(payload["quantity"])
        if quantity <= 0:
            raise UserError("E_AGENT_INVALID: quantity must be positive")
        so = self.env["sale.order"].create(
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
                            "product_uom_qty": quantity,
                            "price_unit": float(payload["unit_price"]),
                            "tax_ids": [(6, 0, [])],
                        },
                    )
                ],
            }
        )
        if so.state != "draft":
            raise UserError("E_AGENT_INVALID: quotation left draft state")
        op.write({"result_model": "sale.order", "result_id": so.id})
        return {"status": "created", **self.read_operation(namespace, operation_key)}

    # ---------------------------------------------------- ERP-06 late orders
    @api.model
    @api.readonly
    def read_open_orders(self, as_of):
        self._check()
        orders = self.env["sale.order"].search(
            [("state", "=", "sale"), ("company_id", "=", self.env.company.id)],
            order="id",
            limit=500,
        )
        rows = []
        for so in orders:
            promised = so.commitment_date or so.expected_date
            if not promised:
                continue
            rows.append(
                {
                    "order_ref": _ref(so),
                    "external_ref": so.name,
                    "customer_ref": _ref(so.partner_id),
                    "promised_date": _date(promised),
                    "delivery_status": DELIVERY.get(so.delivery_status, "pending"),
                }
            )
        return {"as_of": as_of, "orders": rows, "complete": len(orders) < 500}

    # ------------------------------------------------------------ ERP-07 lead
    @api.model
    @api.readonly
    def read_contact(self, contact_ref):
        self._check()
        partner = (
            self.env["res.partner"]
            .with_context(active_test=False)
            .browse(self._id(contact_ref, "res.partner"))
            .exists()
        )
        if not partner:
            return {"found": False}
        return {
            "found": True,
            "contact_ref": _ref(partner),
            "name": partner.display_name,
            "active": bool(partner.active),
        }

    @api.model
    @api.readonly
    def read_teams(self):
        self._check()
        teams = self.env["crm.team"].search(
            [("company_id", "in", [self.env.company.id, False])], limit=100
        )
        sources = self.env["utm.source"].search([], order="id desc", limit=100)
        return {
            "teams": [
                {
                    "team_ref": _ref(t),
                    "name": t.name,
                    "member_refs": [_ref(u) for u in t.member_ids],
                }
                for t in teams
            ],
            "sources": [{"source_ref": _ref(s), "name": s.name} for s in sources],
        }

    def _lead_view(self, lead):
        return {
            "external_ref": f"LEAD/{lead.id}",
            "name": lead.name,
            "contact_ref": _ref(lead.partner_id) if lead.partner_id else None,
            "team_ref": _ref(lead.team_id) if lead.team_id else None,
            "owner_ref": _ref(lead.user_id) if lead.user_id else None,
            "source_ref": _ref(lead.source_id) if lead.source_id else None,
            "expected_revenue": lead.expected_revenue,
        }

    @api.model
    def create_lead(self, namespace, operation_key, payload_digest, payload):
        """One new lead; the ledger makes a repeated command return the same lead."""
        self._check()
        op, created = self._reserve(namespace, operation_key, payload_digest, "create_lead")
        if not created:
            return {"status": "existing", **self.read_operation(namespace, operation_key)}
        partner = (
            self.env["res.partner"].browse(self._id(payload["contact_ref"], "res.partner")).exists()
        )
        team = self.env["crm.team"].browse(self._id(payload["team_ref"], "crm.team")).exists()
        user = self.env["res.users"].browse(self._id(payload["owner_ref"], "res.users")).exists()
        if not partner or not partner.active:
            raise UserError("E_AGENT_INVALID: contact is unknown or archived")
        if not team or user not in team.member_ids:
            raise UserError("E_AGENT_INVALID: owner is not a member of the team")
        source = self.env["utm.source"]
        if payload.get("source_ref"):
            source = source.browse(self._id(payload["source_ref"], "utm.source")).exists()
            if not source:
                raise UserError("E_AGENT_INVALID: unknown lead source")
        revenue = float(payload["expected_revenue"])
        if revenue < 0:
            raise UserError("E_AGENT_INVALID: expected revenue cannot be negative")
        lead = self.env["crm.lead"].create(
            {
                "name": payload["name"],
                "type": "opportunity",
                "partner_id": partner.id,
                "team_id": team.id,
                "user_id": user.id,
                "source_id": source.id or False,
                "expected_revenue": revenue,
                "company_id": self.env.company.id,
            }
        )
        op.write({"result_model": "crm.lead", "result_id": lead.id})
        return {"status": "created", **self.read_operation(namespace, operation_key)}

    # ------------------------------------------------- ERP-08 open invoices
    @api.model
    @api.readonly
    def read_open_invoices(self, as_of):
        self._check()
        moves = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
                ("company_id", "=", self.env.company.id),
            ],
            order="id",
            limit=1000,
        )
        return {
            "as_of": as_of,
            "company": self.env.company.name,
            "complete": len(moves) < 1000,
            "invoices": [
                {
                    "invoice_ref": _ref(m),
                    "external_ref": m.name,
                    "customer_ref": _ref(m.partner_id),
                    "due_date": _date(m.invoice_date_due),
                    "residual": m.amount_residual,
                    "currency": m.currency_id.name,
                }
                for m in moves
            ],
        }

    # ------------------------------------------------------- sandbox tools
    @api.model
    def sandbox_seed_tasks(self, namespace):
        """Synthetic data for ERP-04..08 in this namespace (sandbox only, admin only).

        Posting the seeded invoices is sandbox setup by the administrator; the
        e-agent capabilities themselves never post, pay or confirm anything.
        """
        self._require_sandbox()
        today = fields.Date.context_today(self)
        company = self.env.company
        base = self.sandbox_seed(namespace)
        product = self.env["product.product"].browse(
            self._id(base["product_ref"], "product.product")
        )
        product.write({"sale_ok": True, "list_price": 150.0})
        Partner = self.env["res.partner"].with_context(active_test=False)

        def partner(key, name, active=True):
            found = Partner.search([("ref", "=", f"{namespace}:{key}")], limit=1)
            found = found or Partner.create(
                {"name": name, "ref": f"{namespace}:{key}", "is_company": True}
            )
            found.active = active
            return found

        customer = partner("customer", "E-Agent Customer")
        archived_customer = partner("archived-customer", "E-Agent Archived Customer", active=False)
        contact = partner("lead-contact", "E-Agent Lead Contact")
        archived_contact = partner("old-contact", "E-Agent Old Contact", active=False)
        unsaleable = self.env["product.product"].search(
            [("default_code", "=", f"{namespace}:gadget-x")], limit=1
        )
        unsaleable = unsaleable or self.env["product.product"].create(
            {
                "name": "E-Agent Gadget X",
                "default_code": f"{namespace}:gadget-x",
                "type": "consu",
                "sale_ok": False,
                "taxes_id": [(6, 0, [])],
            }
        )
        supplier = self.env["res.partner"].browse(
            self._id(base["approved_supplier_ref"], "res.partner")
        )

        def rfq(confirm):
            po = self.env["purchase.order"].create(
                {
                    "partner_id": supplier.id,
                    "company_id": company.id,
                    "origin": f"e-agent-seed:{namespace}",
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": product.id,
                                "product_qty": 10.0,
                                "price_unit": 100.0,
                                "date_planned": fields.Datetime.now() + datetime.timedelta(days=20),
                                "tax_ids": [(6, 0, [])],
                            },
                        )
                    ],
                }
            )
            if confirm:
                po.button_confirm()
            return po

        draft_rfq, confirmed_rfq = rfq(False), rfq(True)

        def order(days, deliver):
            so = self.env["sale.order"].create(
                {
                    "partner_id": customer.id,
                    "client_order_ref": namespace,
                    "commitment_date": fields.Datetime.now() + datetime.timedelta(days=days),
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": product.id,
                                "product_uom_qty": 1.0,
                                "price_unit": 150.0,
                                "tax_ids": [(6, 0, [])],
                            },
                        )
                    ],
                }
            )
            so.action_confirm()
            if deliver:
                for picking in so.picking_ids:
                    for move in picking.move_ids:
                        move.quantity = move.product_uom_qty
                        move.picked = True
                    picking.button_validate()
            return so

        late, future, delivered = order(-5, False), order(5, False), order(-3, True)

        team = self.env["crm.team"].search([("name", "=", f"E-Agent Direct {namespace}")], limit=1)
        admin = self.env.ref("base.user_admin")
        team = team or self.env["crm.team"].create(
            {
                "name": f"E-Agent Direct {namespace}",
                "member_ids": [(6, 0, [admin.id])],
                "company_id": company.id,
            }
        )
        outsider = self.env["res.users"].search([("login", "=", "e-agent-integration")], limit=1)
        source = self.env["utm.source"].search([("name", "=", f"E-Agent Web {namespace}")], limit=1)
        source = source or self.env["utm.source"].create({"name": f"E-Agent Web {namespace}"})

        def invoice(due_days, amount):
            move = self.env["account.move"].create(
                {
                    "move_type": "out_invoice",
                    "partner_id": customer.id,
                    "ref": namespace,
                    "invoice_date": today - datetime.timedelta(days=40),
                    "invoice_date_due": today + datetime.timedelta(days=due_days),
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": product.id,
                                "quantity": 1.0,
                                "price_unit": amount,
                                "tax_ids": [(6, 0, [])],
                            },
                        )
                    ],
                }
            )
            move.action_post()
            move.invoice_date_due = today + datetime.timedelta(days=due_days)
            return move

        overdue, not_due = invoice(-10, 500.0), invoice(10, 300.0)
        return {
            **base,
            "as_of": fields.Date.to_string(today),
            "rfq_ref": _ref(draft_rfq),
            "confirmed_rfq_ref": _ref(confirmed_rfq),
            "customer_ref": _ref(customer),
            "archived_customer_ref": _ref(archived_customer),
            "unsaleable_product_ref": _ref(unsaleable),
            "late_order_ref": _ref(late),
            "future_order_ref": _ref(future),
            "delivered_order_ref": _ref(delivered),
            "delivered_status": delivered.delivery_status,
            "contact_ref": _ref(contact),
            "archived_contact_ref": _ref(archived_contact),
            "team_ref": _ref(team),
            "owner_ref": _ref(admin),
            "other_owner_ref": _ref(outsider) if outsider else None,
            "source_ref": _ref(source),
            "overdue_invoice_ref": _ref(overdue),
            "not_due_invoice_ref": _ref(not_due),
        }

    @api.model
    def sandbox_reset(self, namespace):
        """Also undo ERP-04..08 seeds and results in this namespace only."""
        self._require_sandbox()
        ops = self.env["e_agent.operation"].sudo().search([("namespace", "=", namespace)])
        for op in ops.filtered(
            lambda o: o.result_model in ("sale.order", "crm.lead") and o.result_id
        ):
            record = self.env[op.result_model].browse(op.result_id).exists()
            if (
                record
                and op.result_model == "sale.order"
                and record.state not in ("draft", "cancel")
            ):
                raise UserError("E_AGENT_RESET_REFUSED: non-draft quotation in namespace")
            record.unlink()
        seeded_pos = self.env["purchase.order"].search(
            [("origin", "=", f"e-agent-seed:{namespace}")]
        )
        amended = set(
            ops.filtered(lambda o: o.result_model == "purchase.order").mapped("result_id")
        )
        for po in seeded_pos:
            if po.state != "cancel":
                po.button_cancel()
            if po.id not in amended:
                po.unlink()
        for so in self.env["sale.order"].search([("client_order_ref", "=", namespace)]):
            so.with_context(disable_cancel_warning=True)._action_cancel()
        for move in self.env["account.move"].search(
            [("ref", "=", namespace), ("move_type", "=", "out_invoice")]
        ):
            move.button_draft()
            move.button_cancel()
        return super().sandbox_reset(namespace)
