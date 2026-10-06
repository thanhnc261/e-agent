from odoo import fields, models


class EAgentDemand(models.Model):
    """Synthetic procurement demand for the sandbox (not an Odoo-native concept)."""

    _name = "e_agent.demand"
    _description = "e-agent synthetic procurement demand (sandbox fixture)"

    name = fields.Char(required=True, index=True)
    namespace = fields.Char(required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float(required=True, digits="Product Unit")
    requested_date = fields.Date(required=True)
    budget = fields.Float(required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
