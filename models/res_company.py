from odoo import fields, models  # type: ignore


class ResCompany(models.Model):
    _inherit = "res.company"


    sijil_sales_email_from = fields.Char(
        string="Default Sales/Contract FROM",
        help="Email address used as the FROM for outgoing quotation and "
            "contract-signature emails on this company. "
            "Example: 'Sijil Sales <sales@sijilacc.com>'. "
            "Leave blank to use Odoo's default (current user / company).",
    )
    sijil_sales_email_cc = fields.Char(
        string="Default Sales/Contract CC",
        help="Comma-separated email addresses added as CC on outgoing "
            "quotation and contract-signature emails. Example: "
            "'info@sijilacc.com'. Leave blank to disable.",
    )
    sijil_sales_mail_server_id = fields.Many2one(
        comodel_name="ir.mail_server",
        string="Outgoing Mail Server",
        help="Outgoing SMTP server used for quotation and contract-signature "
            "emails on this company. Pin it explicitly so emails do not "
            "fall through to another matching server. Leave blank to let "
            "Odoo pick by from_filter / priority.",
    )


    sijil_contract_approval_user_ids = fields.Many2many(
    comodel_name="res.users",
    relation="sijil_contract_approval_res_users_rel",
    column1="company_id",
    column2="user_id",
    string="Contract Approval",
    help=(
        "Users selected here will receive and approve all contract approval "
        "requests for this company."
    ),
)