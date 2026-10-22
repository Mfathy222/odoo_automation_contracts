from odoo import api, fields, models

SIJIL_COMPANY_ID = 2

class ZofirmOneAudit(models.Model):
    _name = "zofirm.one.audit"
    _description = "One Audit Upload Queue"
    _order = "sequence, id"

    sequence = fields.Integer(string="التسلسل")
    customer_name = fields.Char(string="اسم العميل", required=True)
    customer_code = fields.Char(string="رمز العميل")
    period_end = fields.Date(string="نهاية الفترة")
    contract_no = fields.Char(string="رقم العقد")
    fees_amount = fields.Float(string="الأجور")
    vat_amount = fields.Float(string="مجموع الضريبة")

    contract_template = fields.Selection(
        [
            ("engagement_audit", "خطاب الارتباط مراجعة"),
            ("agreed_4400", "تقرير الإجراءات المتفق عليها 4400"),
            ("bookkeeping", "خدمات مسك الدفاتر"),
            ("tax_zakat", "عقد الزكاة والضريبة"),
            ("international_standards", "عقد وفق المعايير الدولية"),
        ],
        string="نماذج العقد",
        required=True,
        default="engagement_audit",
    )

    attachment_ids = fields.Many2many(
        "ir.attachment",
        "zofirm_one_audit_ir_attachment_rel",
        "one_audit_id",
        "attachment_id",
        string="PDF",
        help="ارفع ملفات PDF الخاصة بهذا السطر",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("sequence"):
                vals["sequence"] = (self.search([], order="sequence desc", limit=1).sequence or 0) + 1
        return super().create(vals_list)
    
    
    @api.model
    def get_one_audit_ui_info(self):
        return {
            "visible": self.env.company.id != SIJIL_COMPANY_ID,
            "count": self.search_count([]) if self.env.company.id != SIJIL_COMPANY_ID else 0,
        }