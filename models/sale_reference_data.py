from odoo import fields, models


class SalePaymentDuration(models.Model):
    _name = "sale.payment.duration"
    _description = "Payment Duration"
    _order = "sequence, name, id"

    name = fields.Char(string="Payment Duration", required=True, translate=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)

    _name_unique = models.Constraint(
        "unique(name)",
        "Payment Duration name must be unique.",
    )


class SaleFinancialYear(models.Model):
    _name = "sale.financial.year"
    _description = "Financial Year"
    _order = "name, id"

    name = fields.Char(string="Year", required=True)
    active = fields.Boolean(string="Active", default=True)

    _name_unique = models.Constraint(
        "unique(name)",
        "Financial year must be unique.",
    )
