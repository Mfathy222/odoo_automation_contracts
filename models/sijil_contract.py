from odoo import api, fields, models, _  # noqa: I001
from odoo.exceptions import UserError  
from odoo.tools.safe_eval import safe_eval
import base64
import logging
import re

_logger = logging.getLogger(__name__)

# Keep this value identical to contract_approval_request.py / sign_request.py.
# When an approved Sign payload is replayed, we must preserve the exact signer
# lines chosen by the user and avoid applying template defaults a second time.
BYPASS_CTX_KEY = "zofirm_contract_approval_bypass"


class SignTemplate(models.Model):
    _inherit = "sign.template"

    sijil_contract_id = fields.Many2one(
        "zofirm.contract",
        string="Sijil Contract",
        ondelete="set null",
    )
    sijil_contract_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Contract PDF Attachment",
        ondelete="set null",
    )

    def _get_dynamic_document_info(self):
        SignTemplateModel = self.env["sign.template"]
        for field_name, field in SignTemplateModel._fields.items():
            if (
                "document" in field_name
                and getattr(field, "type", None) == "one2many"
                and getattr(field, "comodel_name", None)
            ):
                doc_model_name = field.comodel_name
                inverse_name = getattr(field, "inverse_name", False)
                if not inverse_name:
                    break
                DocModel = self.env[doc_model_name]
                for attachment_field in ("attachment_id", "document_attachment_id", "ir_attachment_id"):
                    if attachment_field in DocModel._fields:
                        return doc_model_name, inverse_name, attachment_field
                raise UserError(_("Could not find the attachment field on %s.") % doc_model_name)
        raise UserError(_("Could not find the Sign template documents relation in Odoo 19."))

    def _sijil_wrap_send_action(self, action):
        contract = self.sijil_contract_id
        if not contract:
            return action

        contract_title = contract.contract_name or contract.name or contract.display_name
        filename = contract_title if (contract_title or "").lower().endswith(".pdf") else f"{contract_title}.pdf"
        validity_date = contract.end_date or False
        signer_partner = contract._get_signature_partner()

        base = action.get("context") or {}
        if isinstance(base, str):
            base = safe_eval(base)
        new_ctx = dict(base)
        new_ctx.update(
            {
                "active_model": "sign.template",
                "active_id": self.id,
                "default_template_id": self.id,
                "default_reference": contract.name or contract.display_name,
                "sijil_force_sign_defaults": True,
                "default_subject": f"Signature Request – {contract_title}",
                "default_filename": filename,
                "default_validity": validity_date,
                "default_partner_ids": [signer_partner.id] if signer_partner else [],
                # Do not add the signer to CC. The signer already receives the
                # signature request through signer_ids / partner_ids.
                "default_cc_partner_ids": [],
                "default_attachment_ids": [self.sijil_contract_attachment_id.id]
                if self.sijil_contract_attachment_id
                else [],
            }
        )
        action["context"] = new_ctx
        return action

    def action_send_request(self):
        action = super().action_send_request()
        return self._sijil_wrap_send_action(action)


class SignSendRequest(models.TransientModel):
    _inherit = "sign.send.request"

    def _sijil_get_template_and_contract(self):
        template = self.template_id
        if template and getattr(template, "sijil_contract_id", False):
            return template, template.sijil_contract_id

        ctx = self.env.context
        template_id = ctx.get("default_template_id") or (
            ctx.get("active_id") if ctx.get("active_model") == "sign.template" else False
        )

        if isinstance(template_id, str):
            template_id = template_id.strip()
            template_id = int(template_id) if template_id.isdigit() else False
        elif isinstance(template_id, (list, tuple)):
            template_id = template_id[0] if template_id and isinstance(template_id[0], int) else False
        elif not isinstance(template_id, int):
            template_id = False

        if template_id:
            template = self.env["sign.template"].browse(template_id).exists()
            if template and getattr(template, "sijil_contract_id", False):
                return template, template.sijil_contract_id

        return False, False

    def _sijil_apply_template_defaults(self):
        self.ensure_one()

        # The approval flow recreates sign.send.request from the payload that
        # already contains the exact signer_ids selected by the user. Applying
        # defaults again here can overwrite Signer 1 with the customer partner.
        if self.env.context.get(BYPASS_CTX_KEY):
            return

        template, contract = self._sijil_get_template_and_contract()
        if not contract:
            return

        contract_title = contract.contract_name or contract.name or contract.display_name
        filename = contract_title if (contract_title or "").lower().endswith(".pdf") else f"{contract_title}.pdf"
        validity_date = contract.end_date or False
        signer_partner = contract._get_signature_partner()

        if "subject" in self._fields:
            self.subject = f"Signature Request – {contract_title}"
        if "filename" in self._fields:
            self.filename = filename
        if "validity" in self._fields:
            self.validity = validity_date

        attach = getattr(template, "sijil_contract_attachment_id", False)
        if attach and "attachment_ids" in self._fields:
            self.attachment_ids = [(6, 0, [attach.id])]

        if signer_partner:
            if "partner_ids" in self._fields:
                self.partner_ids = [(6, 0, [signer_partner.id])]
            if "cc_partner_ids" in self._fields:
                self.cc_partner_ids = [(5, 0, 0)]
            if "signer_ids" in self._fields:
                # Only populate an empty signer role. Never fall back to the
                # first existing signer, otherwise Signer 1 can be replaced by
                # the customer when the wizard is rebuilt after Approval.
                target_line = self.signer_ids.filtered(lambda s: not s.partner_id)[:1]
                if target_line:
                    target_line.partner_id = signer_partner.id

        company = (contract.company_id if contract else False) or self.env.company
        if company:
            if company.sijil_sales_email_from and "email_from" in self._fields:
                self.email_from = company.sijil_sales_email_from
            if company.sijil_sales_mail_server_id and "mail_server_id" in self._fields:
                self.mail_server_id = company.sijil_sales_mail_server_id.id

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            rec._sijil_apply_template_defaults()
        return recs

    @api.onchange("template_id")
    def _onchange_template_id(self):
# ===   
        parent_method = getattr(super(), "_onchange_template_id", None)
        res = parent_method() if parent_method else None
        for rec in self:
            rec._sijil_apply_template_defaults()
        return res


class SaleOrder(models.Model):
    _inherit = "sale.order"

    project_schedule_line_ids = fields.One2many(
        comodel_name="sale.order.project.schedule.line",
        inverse_name="order_id",
        string="Project schedule",
        copy=True,
    )

    def _sanitize_filename(self, name):
        name = (name or "Contract").strip()
        name = re.sub(r"[\\/\t\n\r\x00\x1f:\*\?\"<>|]+", " ", name)
        return name[:120]

    def action_create_sijil_contract(self):
        action = super().action_create_sijil_contract()
        if not (action and isinstance(action, dict)):
            return action

        res_id = action.get("res_id")
        contract = self.env["zofirm.contract"].browse(res_id).exists() if res_id else False
        if not contract:
            contract = self.env["zofirm.contract"].search(
                [("quotation_id", "=", self.id)], order="id desc", limit=1
            )
        if not contract:
            return action

        try:
            if (not contract.contract_schedule_line_ids) and hasattr(self, "project_schedule_line_ids"):
                vals_list = [
                    {
                        "description": l.description,
                        "duration_per_week": l.duration_per_week,
                        "outputs": l.outputs,
                    }
                    for l in self.project_schedule_line_ids
                ]
                if vals_list:
                    contract.write({"contract_schedule_line_ids": [(0, 0, v) for v in vals_list]})
                    contract.message_post(body=_("Copied Project schedule from Quotation."))
        except Exception as e:
            _logger.exception("Copy schedule failed")
            contract.message_post(body=_("Failed to copy Project schedule: %s") % e)

        try:
            report = self.env.ref("sijil_contract.report_contract_from_word", raise_if_not_found=False)
            if report:
                pdf_content, _content_type = self.env["ir.actions.report"]._render_qweb_pdf(
                    report.report_name, res_ids=[contract.id]
                )
                partner_name = self.partner_id.name or contract.partner_id.name or "Contract"
                fname = f"عقد - {self._sanitize_filename(partner_name)}.pdf"
                att = self.env["ir.attachment"].create(
                    {
                        "name": fname,
                        "res_model": "zofirm.contract",
                        "res_id": contract.id,
                        "datas": base64.b64encode(pdf_content),
                        "type": "binary",
                        "mimetype": "application/pdf",
                    }
                )
                contract.message_post(body=_("Contract PDF generated and attached."), attachment_ids=[att.id])
        except Exception as e:
            _logger.exception("Contract PDF generation failed")
            contract.message_post(body=_("Contract PDF generation failed: %s") % e)

        return action


class SaleOrderProjectScheduleLine(models.Model):
    _name = "sale.order.project.schedule.line"
    _description = "Sale Order Project Schedule Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    description = fields.Char(string="Description")
    duration_per_week = fields.Char(string="Duration")
    outputs = fields.Text(string="Outputs")
    name = fields.Char(string="Name", compute="_compute_name", store=False)

    @api.depends("description")
    def _compute_name(self):
        for rec in self:
            rec.name = rec.description or _("Schedule Line")


class SijilContractScheduleLine(models.Model):
    _name = "zofirm.contract.schedule.line"
    _description = "Sijil Contract Project Schedule Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    contract_id = fields.Many2one(
        "zofirm.contract",
        string="Contract",
        ondelete="cascade",
        required=True,
        index=True,
    )
    description = fields.Char("Description", required=True)
    duration_per_week = fields.Float("Duration per week")
    outputs = fields.Text("Outputs")
