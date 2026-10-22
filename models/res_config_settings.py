from odoo import fields, models  # type: ignore


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sijil_sales_email_from = fields.Char(
        related="company_id.sijil_sales_email_from",
        readonly=False,
    )

    sijil_sales_email_cc = fields.Char(
        related="company_id.sijil_sales_email_cc",
        readonly=False,
    )

    sijil_sales_mail_server_id = fields.Many2one(
        related="company_id.sijil_sales_mail_server_id",
        readonly=False,
    )

    sijil_contract_approval_user_ids = fields.Many2many(
        related="company_id.sijil_contract_approval_user_ids",
        readonly=False,
    )