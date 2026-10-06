from odoo import fields, models


class EAgentOperation(models.Model):
    """Operation ledger: one row per (namespace, company, operation key)."""

    _name = "e_agent.operation"
    _description = "e-agent operation ledger"
    _order = "id"

    namespace = fields.Char(required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    operation_key = fields.Char(required=True)
    payload_digest = fields.Char(required=True)
    command = fields.Char(required=True)
    result_model = fields.Char()
    result_id = fields.Integer()

    _operation_unique = models.Constraint(
        "UNIQUE(namespace, company_id, operation_key)",
        "This e-agent operation key was already used.",
    )
