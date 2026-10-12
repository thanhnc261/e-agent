"""Administrator-only ownership inventory for synthetic sandbox setup."""

from odoo import fields, models


class EAgentFixture(models.Model):
    _name = "e_agent.fixture"
    _description = "Owned e-agent synthetic fixture inventory"

    namespace = fields.Char(required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    inventory = fields.Json(default=dict)
    references = fields.Json(default=dict)

    _fixture_unique = models.Constraint(
        "UNIQUE(namespace, company_id)", "This synthetic namespace is already owned."
    )
