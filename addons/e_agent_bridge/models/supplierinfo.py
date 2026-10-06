from odoo import fields, models


class SupplierInfo(models.Model):
    _inherit = "product.supplierinfo"

    e_agent_approved = fields.Boolean(
        string="Approved for e-agent procurement",
        help="Sandbox fixture flag: Odoo has no native approved-offer status.",
    )
