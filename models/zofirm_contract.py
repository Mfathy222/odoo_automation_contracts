from odoo import api, fields, models, _  
from odoo.exceptions import ValidationError, UserError 
from dateutil.relativedelta import relativedelta
import base64


SIJIL_COMPANY_ID = 2


# Defines the contract model and manages contract data, reporting, documents, and signature workflows.
class zofirmContract(models.Model):
    _name = "zofirm.contract"
    _description = "Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    
    signature = fields.Selection([('Yes', 'Yes'), ('No', 'No')], 
    string='Signed',
    store=True,
    tracking=True,
    )
    
    show_description = fields.Boolean(
    string="Show Description",
    default=False,
    tracking=True,
    )
    
    show_Quarterly = fields.Boolean(
    string="Show Quarterly Financial",
    default=False,
    tracking=True,
    )

    is_sijil_company = fields.Boolean(
        string="Is Sijil Company",
        compute="_compute_is_sijil_company",
        store=False,
    )

    # Determines whether each contract belongs to the configured Sijil company.
    @api.depends("company_id")
    def _compute_is_sijil_company(self):
        for rec in self:
            rec.is_sijil_company = rec.company_id.id == SIJIL_COMPANY_ID


    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        index=True,
    )
    
    contract_name = fields.Char(
        string="Contract Name",
        compute="_compute_contract_name",
        store=True,
    )

    end_date_number = fields.Char(
        string="1Audit",
        tracking=True,
        copy=False,
    )
    
    is_audit_contract_template = fields.Boolean(
    string="Is Audit Contract Template",
    compute="_compute_is_audit_contract_template",
    store=False,
)


    # Determines whether the selected PDF template is the audit contract report.
    @api.depends("pdf_template_id")
    def _compute_is_audit_contract_template(self):
        audit_report = self.env.ref(
            "zofirm_contract.action_report_zofirm_contract",
            raise_if_not_found=False,
        )

        for rec in self:
            rec.is_audit_contract_template = bool(
                audit_report
                and rec.pdf_template_id
                and rec.pdf_template_id.id == audit_report.id
            )


    # Normalizes the audit number by removing surrounding whitespace when it changes.
    @api.onchange("end_date_number")
    def _onchange_end_date_number_strip(self):
        for rec in self:
            if rec.end_date_number:
                rec.end_date_number = rec.end_date_number.strip()


    # Ensures that the audit number is unique across contract records.
    @api.constrains("end_date_number")
    def _check_unique_end_date_number(self):
        for rec in self:
            if not rec.end_date_number:
                continue

            audit_number = rec.end_date_number.strip()

            if not audit_number:
                continue

            duplicate = self.search(
                [
                    ("end_date_number", "=", audit_number),
                    ("id", "!=", rec.id),
                ],
                limit=1,
            )

            if duplicate:
                raise ValidationError(
                    _(
                        ".مستخدم بالفعل في عقد آخر ولا يمكن تكراره Audit (%s)رقم "
                    )
                    % audit_number
                )
    
    # Builds the Arabic text for one unit of a contract duration.
    def _sijil_ar_duration_part(self, number, one, two, plural):
        if not number:
            return False
        if number == 1:
            return one
        if number == 2:
            return two
        if 3 <= number <= 10:
            return "%s %s" % (number, plural)
        return "%s %s" % (number, one.split()[0])


    # Builds the complete Arabic duration text between the contract start and end dates.
    def _sijil_duration_text_ar(self, start_date, end_date):
        start = fields.Date.to_date(start_date)
        end = fields.Date.to_date(end_date)

        if not start or not end or end < start:
            return "......"

        duration = relativedelta(end + relativedelta(days=1), start)

        parts = []

        year_text = self._sijil_ar_duration_part(
            duration.years,
            "سنة واحدة",
            "سنتان",
            "سنوات",
        )
        month_text = self._sijil_ar_duration_part(
            duration.months,
            "شهر واحد",
            "شهران",
            "أشهر",
        )
        day_text = self._sijil_ar_duration_part(
            duration.days,
            "يوم واحد",
            "يومان",
            "أيام",
        )

        for item in (year_text, month_text, day_text):
            if item:
                parts.append(item)

        return " و ".join(parts) or "يوم واحد"
    
    # Computes the contract display name from the customer and contract type.
    @api.depends("partner_id", "contract_type")
    def _compute_contract_name(self):
        for rec in self:
            partner = rec.partner_id
            if partner:
                partner_name = (partner.commercial_company_name or partner.name) or ""
            else:
                partner_name = ""

            if not partner_name:
                rec.contract_name = False
                continue

            if rec.contract_type == "sijil_maintenance_contract":
                rec.contract_name = _("عقد صيانة شركة %s") % partner_name
            else:
                rec.contract_name = _("عقد شركة %s") % partner_name

    
    company_id = fields.Many2one(
        "res.company",
        related="quotation_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    
    company_active_name = fields.Char(
        string='Active Company', compute='_compute_company_active_name', store=False, readonly=True)
    
    signed_request_count = fields.Integer(
        string="Signature",
        compute="_compute_signed_request_count",
    )
    
    
    
    unsigned_template_count = fields.Integer(
        string="Templates",
        compute="_compute_unsigned_template_count",
    )
    
    
    
    tag_ids = fields.Many2many(
        "res.partner.category",
        "zofirm_contract_res_partner_category_rel",
        "contract_id",
        "category_id",
        string="Tags",
    )

    # Copies customer tags to the contract when the quotation changes.
    @api.onchange("quotation_id")
    def _onchange_quotation_id_set_tags(self):
        for rec in self:
            if rec.partner_id and not rec.tag_ids:
                rec.tag_ids = rec.partner_id.category_id
            
            
            
    

    # Returns the signature templates linked to the current contract.
    def _get_linked_sign_templates(self):
        self.ensure_one()
        SignTemplate = self.env["sign.template"].sudo()

        if "sijil_contract_id" in SignTemplate._fields:
            return SignTemplate.search(
                [("sijil_contract_id", "=", self.id)],
                order="id desc",
            )

        if "zofirm_contract_id" in SignTemplate._fields:
            return SignTemplate.search(
                [("zofirm_contract_id", "=", self.id)],
                order="id desc",
            )

        return SignTemplate.browse()

    # Returns the identifiers of linked signature templates that have completed requests.
    def _get_signed_template_ids(self):
        self.ensure_one()
        templates = self._get_linked_sign_templates()
        if not templates:
            return set()

        signed_requests = self.env["sign.request"].sudo().search([
            ("template_id", "in", templates.ids),
            ("state", "in", ("signed", "completed")),
        ])
        return set(signed_requests.mapped("template_id").ids)

    # Computes the number of linked signature templates that are not yet signed.
    def _compute_unsigned_template_count(self):
        for rec in self:
            templates = rec._get_linked_sign_templates()
            if not templates:
                rec.unsigned_template_count = 0
                continue

            signed_template_ids = rec._get_signed_template_ids()
            rec.unsigned_template_count = len(
                templates.filtered(lambda t: t.id not in signed_template_ids)
            )


    # Opens the signature templates linked to the current contract.
    def action_view_contract_templates(self):
        self.ensure_one()

        templates = self._get_linked_sign_templates()
        if not templates:
            return {"type": "ir.actions.act_window_close"}

        action = self.env["ir.actions.actions"].sudo()._for_xml_id("sign.sign_template_action")
        if not action:
            return {"type": "ir.actions.act_window_close"}

        action.update({
            "name": _("Templates"),
            "domain": [("id", "in", templates.ids)],
            "res_id": False,
            "target": "current",
            "context": dict(self.env.context),
        })
        return action
    # Returns the signature templates linked to the current contract.
    def _get_linked_sign_templates(self):
        self.ensure_one()
        SignTemplate = self.env["sign.template"].sudo()

        if "sijil_contract_id" in SignTemplate._fields:
            return SignTemplate.search(
                [("sijil_contract_id", "=", self.id)],
                order="id desc",
            )

        if "zofirm_contract_id" in SignTemplate._fields:
            return SignTemplate.search(
                [("zofirm_contract_id", "=", self.id)],
                order="id desc",
            )

        return SignTemplate.browse()


    # Returns signature requests associated with the contract templates or current request.
    def _get_linked_sign_requests(self):
        self.ensure_one()
        templates = self._get_linked_sign_templates()
        Request = self.env["sign.request"].sudo()

        if templates:
            return Request.search(
                [("template_id", "in", templates.ids)],
                order="id desc",
            )

        if self.sign_request_id:
            return self.sign_request_id.sudo()

        return Request.browse()
    
    
    
    


    # Returns contract signature requests that are partially or fully signed.
    def _get_signed_sign_requests(self):
        self.ensure_one()

        # Checks whether a signature request is partially or fully signed.
        def _is_partially_or_fully_signed(req):
            if req.state in ("signed", "completed"):
                return True

            return any(
                item.state in ("signed", "completed")
                for item in req.request_item_ids
            )

        return self._get_linked_sign_requests().filtered(_is_partially_or_fully_signed)

    # Computes the number of partially or fully signed contract requests.
    @api.depends("sign_request_id", "sign_request_id.state")
    def _compute_signed_request_count(self):
        for rec in self:
            rec.signed_request_count = len(rec._get_signed_sign_requests())


    # Opens the signed document record or list associated with the contract.
    def action_view_contract_signature_record(self):
        self.ensure_one()

        requests = self._get_signed_sign_requests()
        if not requests:
            return {"type": "ir.actions.act_window_close"}

        if len(requests) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Signed Document"),
                "res_model": "sign.request",
                "view_mode": "form",
                "res_id": requests.id,
                "target": "current",
                "context": dict(self.env.context),
            }

        action = self.env["ir.actions.act_window"].sudo().search(
            [("res_model", "=", "sign.request")],
            limit=1,
        )
        if not action:
            return {"type": "ir.actions.act_window_close"}

        res = action.read()[0]
        res.update(
            {
                "name": _("Signed Documents"),
                "domain": [("id", "in", requests.ids)],
                "res_id": False,
                "view_mode": "list,form",
                "target": "current",
                "context": dict(self.env.context),
            }
        )
        return res
    
    # Adjusts the generated contract view according to the active company.
    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)

        if view_type == 'list' and self.env.company.id == SIJIL_COMPANY_ID:
            for node in arch.xpath("//field[@name='start_date'] | //field[@name='end_date']"):
                node.set("column_invisible", "1")

        return arch, view



    # Opens the current signature request when it is signed or completed.
    def action_view_current_sign_request(self):
        self.ensure_one()

        req = self.sign_request_id
        if not req or req.state not in ("signed", "completed"):
            return {"type": "ir.actions.act_window_close"}

        return {
            "type": "ir.actions.act_window",
            "name": _("Signed Document"),
            "res_model": "sign.request",
            "view_mode": "form",
            "res_id": req.id,
            "target": "current",
            "context": dict(self.env.context),
        }

    # Computes the active company name displayed on the contract.
    @api.depends_context('allowed_company_ids')
    def _compute_company_active_name(self):
        active_company_name = self.env.company.name or ''
        for rec in self:
            rec.company_active_name = active_company_name
            
    quotation_id = fields.Many2one(
        "sale.order",
        string="Quotation",
        required=True,
        domain=[("state", "in", ["draft", "sent", "sale"])],
        tracking=True,
    )
    start_date = fields.Date(string="Start Date", tracking=True)
    start_hijiry_date = fields.Char(
        string="Contract Start Date (Hijri)", size=50, tracking=True)
    
    end_date = fields.Date(string="End Date", tracking=True)

    
    partner_id = fields.Many2one(
        "res.partner", related="quotation_id.partner_id", store=True, readonly=True
    )

    currency_id = fields.Many2one(
        "res.currency", related="quotation_id.currency_id", store=True, readonly=True
    )

    contract_type = fields.Selection(
        [
            ("sijil_contract", "Sijillacc contract"),
            ("sijil_maintenance_contract", "Sijillacc maintenance contract"),
            ("zofirm_contract", "Zofirm contract"),
        ],
        string="Contract Type",
        default="sijil_contract",
        tracking=True,
        copy=False,
    )

    order_line_ids = fields.One2many(
        "sale.order.line",
        related="quotation_id.order_line",
        string="Items",
        readonly=True,
    )

    selected_order_line_ids = fields.Many2many(
        "sale.order.line",
        "zofirm_contract_selected_sale_order_line_rel",
        "contract_id",
        "sale_line_id",
        string="Selected Quotation Lines",
        help="Used for Sijillacc maintenance contracts to include only selected quotation products/services.",
        copy=False,
    )

    selected_amount_untaxed = fields.Monetary(
        string="Selected Untaxed Amount",
        currency_field="currency_id",
        compute="_compute_selected_amounts",
        store=True,
    )

    selected_amount_tax = fields.Monetary(
        string="Selected Tax",
        currency_field="currency_id",
        compute="_compute_selected_amounts",
        store=True,
    )

    selected_amount_total = fields.Monetary(
        string="Selected Total",
        currency_field="currency_id",
        compute="_compute_selected_amounts",
        store=True,
    )

    # Computes untaxed, tax, and total amounts from selected or available contract lines.
    @api.depends(
        "selected_order_line_ids.price_subtotal",
        "selected_order_line_ids.price_tax",
        "contract_type",
        "order_line_ids.price_subtotal",
        "order_line_ids.price_tax",
    )
    def _compute_selected_amounts(self):
        for rec in self:
            lines = rec.selected_order_line_ids if rec.selected_order_line_ids else rec.order_line_ids
            rec.selected_amount_untaxed = sum(lines.mapped("price_subtotal"))
            rec.selected_amount_tax = sum(lines.mapped("price_tax"))
            rec.selected_amount_total = rec.selected_amount_untaxed + rec.selected_amount_tax
   


    amount_untaxed = fields.Monetary(
        related="quotation_id.amount_untaxed",
        currency_field="currency_id",
        readonly=True,
    )
    amount_tax = fields.Monetary(
        related="quotation_id.amount_tax", currency_field="currency_id", readonly=True
    )
    amount_total = fields.Monetary(
        related="quotation_id.amount_total", currency_field="currency_id", readonly=True
    )
    
# ------------------
    pdf_template_id = fields.Many2one(
        'ir.actions.report',
        string='PDF Template',
        domain="[('report_type', '=', 'qweb-pdf'), ('model', 'in', ['zofirm.contract','sale.order'])]",
        default=lambda self: self._default_pdf_template(),
        help="Select which PDF report template to use for Preview/Print.", readonly=True
    )

    # Resolves the default report XML identifier for the company and contract type.
    @api.model
    def _get_pdf_template_xmlid(self, company, contract_type=False):
        if company and company.id == SIJIL_COMPANY_ID:
            if contract_type == "sijil_maintenance_contract":
                return "zofirm_contract.action_report_sijil_maintenance_contract"
            return "zofirm_contract.action_report_contract"

        return "zofirm_contract.action_report_zofirm_contract"


    # Returns the default report action for a given company and contract type.
    @api.model
    def _default_pdf_template_by_company(self, company, contract_type=False):
        report_xmlid = self._get_pdf_template_xmlid(company, contract_type=contract_type)
        rep = self.env.ref(report_xmlid, raise_if_not_found=False)
        return rep.id if rep else False

    # Returns the default PDF template for the active company.
    @api.model
    def _default_pdf_template(self):
        return self._default_pdf_template_by_company(self.env.company)


    # Initializes default contract values when a new record is created.
    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'pdf_template_id' in fields_list and not vals.get('pdf_template_id'):
            vals['pdf_template_id'] = self._default_pdf_template()
        return vals

    # Updates the PDF template when the quotation or contract type changes.
    @api.onchange("quotation_id", "contract_type")
    def _onchange_quotation_id_set_template(self):
        for rec in self:
            company = rec.quotation_id.company_id or rec.env.company
            rec.pdf_template_id = rec._default_pdf_template_by_company(
                company,
                contract_type=rec.contract_type,
            )

    # Updates the PDF template when the company or contract type changes.
    @api.onchange("company_id", "contract_type")
    def _onchange_company_id_set_template(self):
        for rec in self:
            company = rec.company_id or rec.env.company
            rec.pdf_template_id = rec._default_pdf_template_by_company(
                company,
                contract_type=rec.contract_type,
            )
    
    # Creates contract records with the appropriate report template and sequence.
    @api.model_create_multi
    def create(self, vals_list):
        SaleOrder = self.env["sale.order"]

        for vals in vals_list:
            quotation = (
                SaleOrder.browse(vals.get("quotation_id")).exists()
                if vals.get("quotation_id")
                else False
            )
            company = quotation.company_id if quotation else self.env.company
            contract_type = vals.get("contract_type") or "sijil_contract"

            if not vals.get("pdf_template_id"):
                vals["pdf_template_id"] = self._default_pdf_template_by_company(
                    company,
                    contract_type=contract_type,
                )

            if not vals.get("name") or vals.get("name") == _("New"):
                if company.id == SIJIL_COMPANY_ID:
                    if contract_type == "sijil_maintenance_contract":
                        seq_code = "sijil.maintenance.contract"
                    else:
                        seq_code = "sijil.contract"
                else:
                    seq_code = "zofirm.contract"

                vals["name"] = self.env["ir.sequence"].next_by_code(seq_code) or "/"

        return super().create(vals_list)

    
    
    contract_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Contract Attachment",
        help="Attach the contract PDF or document you want to send to Documents.",
    )

    # Ensures that the contract end date is not earlier than the start date.
    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_("End Date must be on or after Start Date."))
            
    # Resolves the recordset that must be passed to the selected report.
    def _get_report_target_record(self, report_action):
        """Return the recordset that must be given to the report, according to its model."""
        self.ensure_one()
        if not report_action or not report_action.exists():
            raise UserError(
                _(
                    "The selected PDF Template no longer exists. Please select a valid one."
                )
            )

        if report_action.model == "sale.order":
            if not self.quotation_id:
                raise UserError(_("No quotation is linked to this contract."))
            return self.quotation_id

        if report_action.model == "zofirm.contract":
            return self

        raise UserError(
            _("This PDF template is defined on model '%s' which is not supported here.")
            % (report_action.model or "unknown")
        )
    
    # Opens the selected contract report in HTML preview mode.
    def action_preview(self):
        self.ensure_one()

        preview_ctx = {
            "zofirm_preview_contract_id": self.id,
            "zofirm_preview_quotation_id": self.quotation_id.id if self.quotation_id else False,
        }

        if self.pdf_template_id:
            report_action = self.pdf_template_id.with_context(**preview_ctx)
            target = self._get_report_target_record(report_action)
            action = report_action.report_action(target)
            action["report_type"] = "qweb-html"
            return action

        if self.quotation_id:
            report_action = self.env.ref(
                "sale.action_report_saleorder", raise_if_not_found=False
            )
            if report_action:
                action = report_action.with_context(**preview_ctx).report_action(
                    self.quotation_id
                )
                action["report_type"] = "qweb-html"
                return action
        return False

    # Validates and generates the contract before opening the Sadq sending wizard.
    def action_send_to_sadq_wizard(self):
        self.ensure_one()       
        self.action_send_contract()

        return {
            'name': _('Send to Sadq'),
            'type': 'ir.actions.act_window',
            'res_model': 'sadq.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'active_id': self.id,
                'active_model': 'zofirm.contract',
            }
        }
        
        
    
    # Validates the contract, generates its PDF, and stores it in Documents.
    def action_send_contract(self):
        for record in self:
            if not record.partner_id:
                raise UserError(_("Please select a Customer first."))
            if not record.pdf_template_id:
                raise UserError(_("Please select a PDF Template first."))
            if not record.pdf_template_id.exists():
                raise UserError(
                    _(
                        "The selected PDF Template no longer exists. Please select a valid one."
                    )
                )


            record._validate_required_fields_before_contract_output()

            target = record._get_report_target_record(record.pdf_template_id)

            pdf_content, _content_type = record.pdf_template_id._render_qweb_pdf(
                record.pdf_template_id.id, res_ids=target.ids
            )

            pdf_base64 = base64.b64encode(pdf_content)

            attachment = record.env["ir.attachment"].create(
                {
                    "name": f"{record.name or 'Contract'}.pdf",
                    "type": "binary",
                    "datas": pdf_base64,
                    "res_model": record._name,
                    "res_id": record.id,
                    "mimetype": "application/pdf",
                }
            )

            Documents = record.env["documents.document"].sudo()
            folder = Documents.browse()

            type_field = Documents._fields.get("type")
            folder_id_field = Documents._fields.get("folder_id")


            folder_type_supported = False
            if type_field:
                selection = type_field.selection
                if callable(selection):
                    try:
                        selection = selection(Documents)
                    except TypeError:
                        selection = selection(record.env)
                try:
                    folder_type_supported = any(
                        key == "folder" for key, _label in (selection or [])
                    )
                except Exception:
                    folder_type_supported = False

            if folder_type_supported and folder_id_field:
                parent = Documents.search(
                    [
                        ("name", "=", "Customer Contracts"),
                        ("type", "=", "folder"),
                        ("folder_id", "=", False),
                    ],
                    limit=1,
                )

                if not parent:
                    parent = Documents.create(
                        {
                            "name": "Customer Contracts",
                            "type": "folder",
                            "folder_id": False,
                        }
                    )

                
                folder_name = record.partner_id.name or "Customer"
                folder = Documents.search(
                    [
                        ("name", "=", folder_name),
                        ("type", "=", "folder"),
                        ("folder_id", "=", parent.id),
                    ],
                    limit=1,
                )

                if not folder:
                    folder = Documents.create(
                        {
                            "name": folder_name,
                            "type": "folder",
                            "folder_id": parent.id,
                        }
                    )


            document_vals = {
                "name": f"{record.name or 'Contract'}.pdf",
                "partner_id": record.partner_id.id,
                "attachment_id": attachment.id,
            }

            if folder and "folder_id" in Documents._fields:
                document_vals["folder_id"] = folder.id

            Documents.create(document_vals)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Contract Sent"),
                "message": _(
                    "The contract PDF has been successfully generated and sent to Documents."
                ),
                "sticky": False,
            },
        }

    total_subtotal = fields.Monetary(
        string="Total Subtotal",
        currency_field="currency_id",
        compute="_compute_total_subtotal",
        store=True,
    )

    # Computes the subtotal from selected or available contract lines.
    @api.depends("order_line_ids.price_subtotal", "selected_order_line_ids.price_subtotal", "contract_type")
    def _compute_total_subtotal(self):
        for rec in self:
            lines = rec.selected_order_line_ids if rec.selected_order_line_ids else rec.order_line_ids
            rec.total_subtotal = sum(lines.mapped("price_subtotal"))

    tax_label = fields.Char(
        string="Tax Label",
        compute="_compute_tax_label",
        store=False,
        help="Shows tax rate as a label e.g. 'Tax 15%:'.",
    )

    # Computes the displayed tax label using the effective tax percentage.
    @api.depends("amount_tax", "amount_untaxed", "selected_amount_tax", "selected_amount_untaxed", "contract_type")
    def _compute_tax_label(self):
        for rec in self:
            label = _("Tax")

            base_amount = rec.selected_amount_untaxed if rec.selected_order_line_ids else rec.amount_untaxed
            tax_amount = rec.selected_amount_tax if rec.selected_order_line_ids else rec.amount_tax

            if base_amount and base_amount != 0:
                pct = (tax_amount / base_amount) * 100.0
                pct_str = ("%.2f" % pct).rstrip("0").rstrip(".")
                label = _("Tax  %s%%") % pct_str

            rec.tax_label = label

    # Opens the email composer with contract recipient and subject defaults.
    def action_send_by_email(self):
        self.ensure_one()
        template = self.env.ref('zofirm_contract.mail_template_contract', raise_if_not_found=False)
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', raise_if_not_found=False)

        partner = self.partner_id
        partner_name = (partner.commercial_company_name or partner.name) if partner else ''

        default_subject = _("عقد شركة %s") % partner_name if partner_name else _("عقد شركة")

        ctx = {
            'default_model': self._name,
            'default_res_ids': self.ids,
            'default_use_template': bool(template),
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'force_email': True,
            'default_subject': default_subject,
        }
        if partner:
            ctx['default_partner_ids'] = [partner.id]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'views': [(compose_form.id, 'form')] if compose_form else [(False, 'form')],
            'target': 'new',
            'context': ctx,
        }



    partner_contract_count = fields.Integer(
        string="Contracts",
        compute="_compute_partner_contract_counts",
    )

    # Opens all contracts related to the current customer.
    def action_view_partner_contracts(self):
        """Open Zofirm contracts list filtered by current contract's partner."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return False

        real_id = partner._origin.id or partner.id

        action = self.env.ref("zofirm_contract.action_zofirm_contract", raise_if_not_found=False)
        if not action:
            
            action = (
                self.env["ir.actions.act_window"]
                .sudo()
                .search([("res_model", "=", "zofirm.contract")], limit=1)
            )
            if not action:
                return False
            result = action.sudo().read()[0]
        else:
            result = action.sudo().read()[0]

        result["domain"] = [("partner_id", "child_of", real_id)]
        return result
    
    


    signed_date = fields.Date(string="Signed Date")
    sign_request_id = fields.Many2one(
        "sign.request",
        string="Sign Request",
        readonly=True,
        copy=False,
        ondelete="set null",  
    )

    is_signed = fields.Boolean(
        string="Signed",
        compute="_compute_is_signed",
        store=True,
        copy=False,
    )
    signed_on = fields.Datetime(string="Signed On", readonly=True, copy=False)
    
    # Computes whether the current signature request is signed or completed.
    @api.depends("sign_request_id", "sign_request_id.state")
    def _compute_is_signed(self):
        for rec in self:
            state = rec.sign_request_id.state if rec.sign_request_id else False
            rec.is_signed = state in ("signed", "completed")
    
    partner_signed_contract_count = fields.Integer(
        compute="_compute_partner_contract_counts",
        string="Signed Contracts",
    )

    # Computes the total and signed contract counts for the current customer.
    @api.depends("partner_id", "sign_request_id", "sign_request_id.state")
    def _compute_partner_contract_counts(self):
        Contract = self.env["zofirm.contract"]
        for rec in self:
            if not rec.partner_id:
                rec.partner_contract_count = 0
                rec.partner_signed_contract_count = 0
                continue

            pid = rec.partner_id._origin.id or rec.partner_id.id
            domain_all = [("partner_id", "child_of", pid)]
            domain_signed = domain_all + [("sign_request_id.state", "in", ("signed", "completed"))]

            rec.partner_contract_count = Contract.search_count(domain_all)
            rec.partner_signed_contract_count = Contract.search_count(domain_signed)
            
            
    # Opens signed signature requests related to the current customer.
    def action_view_partner_signed_sign_requests(self):
        self.ensure_one()
        if not self.partner_id:
            return {"type": "ir.actions.act_window_close"}

        pid = self.partner_id._origin.id or self.partner_id.id

        action = self.env["ir.actions.act_window"].sudo().search(
            [("res_model", "=", "sign.request")],
            limit=1,
        )
        if not action:
            return {"type": "ir.actions.act_window_close"}

        res = action.read()[0]
        res["domain"] = [
            ("state", "in", ("signed", "completed")),
            ("request_item_ids.partner_id", "child_of", pid),
        ]
        res["context"] = dict(self.env.context)

        return res


    # Validates report specific required data before contract output is generated.
    def _validate_required_fields_before_contract_output(self):
        """Block Print/Signature/Documents/Sadq until the selected report data is complete."""
        self.ensure_one()

        if self.company_id and self.company_id.id == SIJIL_COMPANY_ID:
            return True

        missing = []
        missing_seen = set()

        # Checks whether a required validation value is empty.
        def _is_empty(value):
            if isinstance(value, str):
                return not value.strip()
            return not bool(value)

        # Returns the user facing label for a field used in validation messages.
        def _display_field_name(record, field_name, fallback):
            """Return the user-facing Odoo field label, never the technical name."""
            if record and field_name in record._fields:
                return record._fields[field_name].string or fallback
            return fallback

        # Adds a missing field message once to the validation result.
        def _append_missing_once(message):
            """Add each missing-field message only once."""
            if message not in missing_seen:
                missing_seen.add(message)
                missing.append(message)

        # Adds a validation message when a required field value is empty.
        def _add_if_empty(value, arabic_label, record, field_name, fallback):
            if _is_empty(value):
                display_name = _display_field_name(record, field_name, fallback)
                _append_missing_once("%s [%s]" % (arabic_label, display_name))

        # Checks whether the contract currently uses a specific report action.
        def _uses_report(xmlid):
            report = self.env.ref(xmlid, raise_if_not_found=False)
            return bool(
                report
                and self.pdf_template_id
                and self.pdf_template_id.id == report.id
            )

        is_audit_contract = _uses_report(
            "zofirm_contract.action_report_zofirm_contract"
        )
        is_bookkeeping_contract = _uses_report(
            "zofirm_contract.action_report_zofirm_bookeeping_contract"
        )
        is_4400_contract = _uses_report(
            "zofirm_contract.action_report_zofirm_4400_contract"
        )

        partner = self.partner_id
        commercial_partner = partner.commercial_partner_id if partner else False
        additional_id = (
            getattr(partner, "l10n_sa_edi_additional_identification_number", False)
            if partner
            else False
        ) or (
            getattr(commercial_partner, "l10n_sa_edi_additional_identification_number", False)
            if commercial_partner
            else False
        )

        partner_for_label = partner or commercial_partner
        _add_if_empty(
            additional_id,
            _(" رقم الموحد او الهوية"),
            partner_for_label,
            "l10n_sa_edi_additional_identification_number",
            _("Additional Identification Number"),
        )

        _add_if_empty(
            self.start_date,
            _("تاريخ البداية"),
            self,
            "start_date",
            _("Start Date"),
        )
        _add_if_empty(
            self.start_hijiry_date,
            _("تاريخ البداية الهجري"),
            self,
            "start_hijiry_date",
            _("Contract Start Date (Hijri)"),
        )

        if not is_bookkeeping_contract:
            _add_if_empty(
                self.end_date_number,
                _("تسلسل بيان التدقيق "),
                self,
                "end_date_number",
                _("1Audit"),
            )

        quotation = self.quotation_id

        if is_4400_contract:
            _add_if_empty(
                quotation.work_scope if quotation else False,
                _(" نطاق الاعمال الخاص بعقد 4400"),
                quotation,
                "work_scope",
                _("SOW"),
            )


            if quotation and "work_scope_en" in quotation._fields:
                _add_if_empty(
                    quotation.work_scope_en,
                    _("نطاق الاعمال باللغة الإنجليزية الخاص بعقد 4400"),
                    quotation,
                    "work_scope_en",
                    _("SOW English"),
                )

        if is_bookkeeping_contract:
            _add_if_empty(
                quotation.bookkeeping_fees if quotation else False,
                _("بند الاتعاب الخاص بعقد مسك الدفاتر"),
                quotation,
                "bookkeeping_fees",
                _("Bookkeeping Fees"),
            )




        if is_audit_contract:
            lines = self.order_line_ids.filtered(
                lambda line: not line.display_type and line.product_id
            )

            if any(not line.fees_period_end for line in lines):
                sample_line = lines[:1]
                display_name = _display_field_name(
                    sample_line,
                    "fees_period_end",
                    _("Period End"),
                )
                _append_missing_once(
                    _("تاريخ نهاية الفترة [%s]") % display_name
                )

            if any(not line.financial_year_ids for line in lines):
                sample_line = lines[:1]
                display_name = _display_field_name(
                    sample_line,
                    "financial_year_ids",
                    _("Year"),
                )
                _append_missing_once(
                    _("السنة المالية [%s]") % display_name
                )

        if missing:
            raise UserError(
                _(
                    ":لا يمكن تنفيذ الطباعة أو طلب التوقيع أو الإرسال إلى صدق. يرجى استكمال الحقول الإلزامية التالية\n\n%s"
                )
                % "\n".join("• %s" % item for item in missing)
            )

        return True


    # Validates the contract and prints the selected report template.
    def action_print_selected_template(self):
        self.ensure_one()
        self._validate_required_fields_before_contract_output()

        if self.pdf_template_id:
            target = self._get_report_target_record(self.pdf_template_id)
            return self.pdf_template_id.report_action(target)

        report_action = self.env.ref(
            "zofirm_contract.action_report_contract_dynamic",
            raise_if_not_found=False,
        )
        return report_action.report_action(self) if report_action else False

    # Formats a fee period date using Arabic month names.
    def _format_fees_date_ar(self, date_value):
        if not date_value:
            return ""

        months = {
            1: "يناير",
            2: "فبراير",
            3: "مارس",
            4: "أبريل",
            5: "مايو",
            6: "يونيو",
            7: "يوليو",
            8: "أغسطس",
            9: "سبتمبر",
            10: "أكتوبر",
            11: "نوفمبر",
            12: "ديسمبر",
        }

        return f"{date_value.day} {months.get(date_value.month, '')} {date_value.year}م"


    # Formats a monetary amount without decimal places.
    def _format_amount_no_decimals(self, amount):
        try:
            return "{:,.0f}".format(int(round(amount or 0)))
        except (TypeError, ValueError):
            return "0"


    # Builds the Arabic fee line text from its date and subtotal.
    def _format_fee_line_sentence(self, line):
        date_str = self._format_fees_date_ar(line.fees_period_end)
        amount = self._format_amount_no_decimals(line.price_subtotal or 0)

        return f"{date_str} مبلغ {amount}"         



    contract_schedule_line_ids = fields.One2many(
        "zofirm.contract.schedule.line",
        "contract_id",
        string="Project schedule",
        copy=True,
    )

    # Generates the selected contract report as a PDF attachment.
    def _prepare_contract_pdf_attachment(self):
        """Generate contract PDF from the selected template and return attachment."""
        self.ensure_one()
        if not self.pdf_template_id:
            return False

        target = self._get_report_target_record(self.pdf_template_id)
        pdf_content, _content_type = self.env["ir.actions.report"]._render_qweb_pdf(
            self.pdf_template_id.id, res_ids=target.ids
        )
        pdf_base64 = base64.b64encode(pdf_content).decode()

        if not (pdf_content and pdf_content[:4] == b"%PDF"):
            raise UserError(_("Generated file is not a valid PDF. Check report template / wkhtmltopdf."))

        filename = f"{self.contract_name or self.name or self.display_name or 'Contract'}.pdf"
        return self.env["ir.attachment"].create(
            {
                "name": filename,
                "type": "binary",
                "datas": pdf_base64,
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/pdf",
            }
        )

    # Returns the preferred customer contact for the signature request.
    def _get_signature_partner(self):
        """Return the best partner to receive the sign request."""
        self.ensure_one()

        commercial_partner = self.partner_id.commercial_partner_id if self.partner_id else False
        authorized_person = (
            getattr(commercial_partner, "authorized_person", False)
            if commercial_partner
            else False
        )

        if authorized_person and authorized_person.email:
            return authorized_person
        if commercial_partner and commercial_partner.email:
            return commercial_partner
        return authorized_person or commercial_partner

    # Builds the domain used to find contracts for the current customer.
    def _get_partner_contract_domain(self, signed_only=False):
        self.ensure_one()
        if not self.partner_id:
            return [("id", "=", 0)]

        commercial_partner = self.partner_id.commercial_partner_id or self.partner_id
        domain = [("partner_id", "child_of", commercial_partner.id)]
        if signed_only:
            domain.append(("sign_request_id.state", "in", ("signed", "completed")))
        return domain

    # Returns contract records that match the current customer domain.
    def _get_partner_contract_records(self, signed_only=False):
        self.ensure_one()
        return self.env["zofirm.contract"].search(
            self._get_partner_contract_domain(signed_only=signed_only)
        )

    
    # Opens signed contract requests related to the current customer.
    def action_view_partner_signed_contracts(self):
        self.ensure_one()

        contracts = self._get_partner_contract_records(signed_only=True)
        sign_requests = contracts.mapped("sign_request_id").filtered(
            lambda r: r.state in ("signed", "completed")
        )

        if not sign_requests:
            return {"type": "ir.actions.act_window_close"}

        if len(sign_requests) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Signed Document"),
                "res_model": "sign.request",
                "view_mode": "form",
                "res_id": sign_requests.id,
                "target": "current",
            }

        action = self.env["ir.actions.act_window"].sudo().search(
            [("res_model", "=", "sign.request")],
            limit=1,
        )
        if not action:
            return {"type": "ir.actions.act_window_close"}

        res = action.read()[0]
        res.update(
            {
                "name": _("Signed Documents"),
                "domain": [("id", "in", sign_requests.ids)],
                "res_id": False,
                "view_mode": "list,form",
                "target": "current",
                "context": dict(self.env.context),
            }
        )
        return res

    # Validates the contract, creates a signature template, and opens the signature editor.
    def action_request_signature(self):
        self.ensure_one()
        self._validate_required_fields_before_contract_output()

        contract_attachment = self._prepare_contract_pdf_attachment()
        if not contract_attachment:
            raise UserError(_("Please select a PDF Template first."))

        pdf_name = contract_attachment.name or f"{self.contract_name or self.name or 'Contract'}.pdf"
        signer_partner = self._get_signature_partner()

        sign_attachment = contract_attachment.sudo().copy(
            {
                "name": pdf_name,
                "res_model": "sign.template",
                "res_id": 0,
            }
        )

        dynamic_template = self.env["sign.template"].sudo().create(
            {
                "name": pdf_name,
                "sijil_contract_id": self.id,
                "sijil_contract_attachment_id": sign_attachment.id,
            }
        )

        doc_model_name, inverse_name, attachment_field = dynamic_template._get_dynamic_document_info()

        doc_vals = {
            inverse_name: dynamic_template.id,
            attachment_field: sign_attachment.id,
        }
        DocModel = self.env[doc_model_name]
        if "name" in DocModel._fields:
            doc_vals["name"] = pdf_name

        first_doc = DocModel.sudo().create(doc_vals)
        sign_attachment.sudo().write(
            {
                "res_model": first_doc._name,
                "res_id": first_doc.id,
                "name": pdf_name,
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "sign.Template",
            "name": "Template Editor",
            "params": {"id": dynamic_template.id},
            "context": {
                "active_model": "sign.template",
                "active_id": dynamic_template.id,
                "default_template_id": dynamic_template.id,
                "sijil_force_sign_defaults": True,
                "sijil_contract_id": self.id,
                "sijil_contract_attachment_id": sign_attachment.id,
                "default_partner_ids": [signer_partner.id] if signer_partner else [],
            },
        }




# Extends report rendering to recover contract context and enforce contract validation.
class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    # Recovers the contract associated with the current report context or quotation.
    def _get_zofirm_preview_contract(self):
        contract_id = self.env.context.get("zofirm_preview_contract_id")
        quotation_id = self.env.context.get("zofirm_preview_quotation_id")

        contract = (
            self.env["zofirm.contract"].browse(contract_id).exists()
            if contract_id
            else self.env["zofirm.contract"].browse()
        )

        if not contract and quotation_id:
            contract = self.env["zofirm.contract"].search(
                [("quotation_id", "=", quotation_id)],
                order="id desc",
                limit=1,
            )

        return contract

    # Uses the recovered contract as the HTML report target when required.
    def _render_qweb_html(self, report_ref, docids, data=None):
        report = self._get_report(report_ref)
        contract = self._get_zofirm_preview_contract()

        if contract and report.model == "zofirm.contract":
            docids = contract.ids

        return super()._render_qweb_html(
            report_ref,
            docids,
            data=data,
        )

    # Validates the contract and restores the correct target before rendering a PDF report.
    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        contract = self._get_zofirm_preview_contract()

        if contract:
            contract._validate_required_fields_before_contract_output()
            if report.model == "zofirm.contract":
                res_ids = contract.ids

        return super()._render_qweb_pdf(
            report_ref,
            res_ids=res_ids,
            data=data,
        )





# Defines the wizard used to select and apply a contract report template.
class ZofirmContractTemplateWizard(models.TransientModel):
    _name = "zofirm.contract.template.wizard"
    _description = "Select Contract Template"

    sale_order_id = fields.Many2one("sale.order", required=True, readonly=True)
    template_type = fields.Selection(
        [
            ("audit", "Audit contract"),
            ("bookkeeping", "Bookeeping contract"),
            ("4400_contract", "4400 contract"),
        ],
        required=True,
        default="audit",
    )

    # Applies the selected contract template to the quotation contract and opens the contract form.
    def action_confirm(self):
        self.ensure_one()
        sale = self.sale_order_id
        if not sale:
            raise UserError(_("Quotation not found."))

        if self.template_type == "audit":
            report_xmlid = "zofirm_contract.action_report_zofirm_contract"
        elif self.template_type == "bookkeeping":
            report_xmlid = "zofirm_contract.action_report_zofirm_bookeeping_contract"
        elif self.template_type == "4400_contract":
            report_xmlid = "zofirm_contract.action_report_zofirm_4400_contract"
        else:
            raise UserError(_("Unknown template type."))

        report = self.env.ref(report_xmlid, raise_if_not_found=False)
        if not report:
            raise UserError(_("Template not found: %s") % report_xmlid)

        Contract = self.env["zofirm.contract"]
        contract = Contract.search([("quotation_id", "=", sale.id)], limit=1)

        vals = {
            "quotation_id": sale.id,
            "pdf_template_id": report.id,
        }

        if contract:
            contract.write({"pdf_template_id": report.id})
        else:
            contract = Contract.create(vals)

        form_view = self.env.ref("zofirm_contract.view_zofirm_contract_form")

        return {
            "type": "ir.actions.act_window",
            "name": "Zofirm Contract",
            "res_model": "zofirm.contract",
            "view_mode": "form",
            "views": [(form_view.id, "form")],
            "res_id": contract.id,
            "target": "current",
        }
