import json  # noqa: I001
import base64
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from markupsafe import Markup

BYPASS_CTX_KEY = "zofirm_contract_approval_bypass"


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    zofirm_contract_id = fields.Many2one(
        "zofirm.contract",
        string="Contract",
        readonly=True,
        copy=False,
        index=True,
    )

    zofirm_contract_action_type = fields.Selection(
        [
            ("mail_send", "Send Contract Email"),
            ("sign_send_request", "Send Signature Request"),
            ("sign_completed_document", "Validate & Send Completed Document"),
        ],
        string="Contract Action",
        readonly=True,
        copy=False,
        index=True,
    )

    zofirm_contract_payload_json = fields.Text(
        string="Contract Payload",
        readonly=True,
        copy=False,
        default="{}",
    )

    zofirm_sign_request_id = fields.Many2one(
        "sign.request",
        string="Sign Request",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    
    zofirm_sign_template_id = fields.Many2one(
    "sign.template",
    string="Sign Template",
    readonly=True,
    copy=False,
    ondelete="set null",
    )
    
    zofirm_contract_pdf_attachment_id = fields.Many2one(
    "ir.attachment",
    string="Contract PDF",
    readonly=True,
    copy=False,
    ondelete="set null",
    )

    zofirm_contract_action_done = fields.Boolean(
        string="Contract Action Executed",
        readonly=True,
        copy=False,
    )

    zofirm_contract_error_message = fields.Text(
        string="Contract Execution Error",
        readonly=True,
        copy=False,
    )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    @api.model
    def _zofirm_is_direct_contract_sender(self):
        """
        الأدمن فقط يرسل مباشرة بدون Approval.
        المستخدم العادي يتم تحويل طلبه إلى Approvals.
        """
        return self.env.user.has_group("base.group_system")

    @api.model
    def _zofirm_get_contract_company(self, contract):
        return contract.company_id or contract.quotation_id.company_id or self.env.company

    @api.model
    def _zofirm_notification(self, title, message, notif_type="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notif_type,
                "sticky": False,
            },
        }
        
        
    @api.model
    def _zofirm_get_contract_form_url(self, contract):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return "%s/web#id=%s&model=zofirm.contract&view_type=form" % (
            base_url,
            contract.id,
        )


    @api.model
    def _zofirm_get_contract_link_html(self, contract):
        url = self._zofirm_get_contract_form_url(contract)
        label = contract.display_name or contract.name or _("Open Contract")
        return Markup('<a href="%s" target="_blank">%s</a>') % (url, label)
    
    @api.model
    def _zofirm_create_contract_pdf_attachment(self, contract, approval, company):
        """
        Generate contract PDF at approval-request time and attach it to the approval request.
        This gives the admin a direct link to the actual contract PDF, not only the contract screen.
        """
        contract = contract.with_company(company).sudo()
        approval = approval.with_company(company).sudo()

        if not contract.pdf_template_id:
            raise UserError(_("Please select a PDF Template first."))

        if not contract.pdf_template_id.exists():
            raise UserError(_("The selected PDF Template no longer exists."))

        target = contract._get_report_target_record(contract.pdf_template_id)

        pdf_content, _content_type = contract.pdf_template_id._render_qweb_pdf(
            contract.pdf_template_id.id,
            res_ids=target.ids,
        )

        if not pdf_content or pdf_content[:4] != b"%PDF":
            raise UserError(_("Generated contract file is not a valid PDF."))

        filename = "%s.pdf" % (
            contract.contract_name
            or contract.name
            or contract.display_name
            or "Contract"
        )

        attachment = self.env["ir.attachment"].with_company(company).sudo().create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "res_model": "approval.request",
                "res_id": approval.id,
                "mimetype": "application/pdf",
            }
        )

        return attachment


    @api.model
    def _zofirm_get_attachment_url(self, attachment):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return "%s/web/content/%s?download=false" % (
            base_url,
            attachment.id,
        )


    @api.model
    def _zofirm_get_attachment_link_html(self, attachment, label=None):
        url = self._zofirm_get_attachment_url(attachment)
        label = label or attachment.name or _("Open Contract PDF")
        return Markup('<a href="%s" target="_blank">%s</a>') % (url, label)

    
    @api.model
    def _zofirm_get_contract_approval_users_for_company(self, company):
        """
        Users selected from:
        Settings -> Sijil Email -> Contract Approval
        """
        if not company:
            company = self.env.company

        if "sijil_contract_approval_user_ids" not in company._fields:
            raise UserError(
                _("Missing field sijil_contract_approval_user_ids on res.company.")
            )

        users = company.sudo().sijil_contract_approval_user_ids.filtered(
            lambda user: user.active and ("share" not in user._fields or not user.share)
        )

        if not users:
            raise UserError(
                _(
                    "No Contract Approval users configured for company: %s.\n"
                    "Please go to Settings > Sijil Email > Contract Approval and select at least one user."
                )
                % company.display_name
            )

        users = users.filtered(
            lambda user: "company_ids" not in user._fields or company in user.company_ids
        )

        if not users:
            raise UserError(
                _(
                    "The selected Contract Approval users do not have access to company: %s.\n"
                    "Please add this company to their Allowed Companies."
                )
                % company.display_name
            )

        return users


    @api.model
    def _zofirm_sync_category_contract_approvers(self, category, company):
        """
        Put company Contract Approval users on the Approval Type,
        so the request appears in the Approvals dashboard.
        """
        approvers = self._zofirm_get_contract_approval_users_for_company(company)

        if "approver_ids" not in category._fields:
            return approvers

        field = category._fields["approver_ids"]
        comodel_name = field.comodel_name
        inverse_name = getattr(field, "inverse_name", False) or "category_id"

        CategoryApprover = self.env[comodel_name].with_company(company).sudo()

        current_lines = category.sudo().approver_ids
        selected_user_ids = set(approvers.ids)

        lines_to_remove = current_lines.filtered(
            lambda line: line.user_id and line.user_id.id not in selected_user_ids
        )
        if lines_to_remove:
            lines_to_remove.unlink()

        existing_user_ids = set(category.sudo().approver_ids.mapped("user_id").ids)

        for user in approvers:
            if user.id in existing_user_ids:
                continue

            vals = {}

            if inverse_name in CategoryApprover._fields:
                vals[inverse_name] = category.id

            if "user_id" in CategoryApprover._fields:
                vals["user_id"] = user.id

            if "required" in CategoryApprover._fields:
                vals["required"] = True

            if "company_id" in CategoryApprover._fields:
                vals["company_id"] = company.id

            CategoryApprover.create(vals)

        return approvers


    @api.model
    def _zofirm_sync_request_contract_approvers(self, approval, approvers):
            """
            Put selected users directly on the Approval Request,
            so it appears in My Approvals / Dashboard for those users.
            """
            if "approver_ids" not in approval._fields:
                return

            field = approval._fields["approver_ids"]
            comodel_name = field.comodel_name
            inverse_name = getattr(field, "inverse_name", False) or "request_id"

            RequestApprover = self.env[comodel_name].sudo()
            current_lines = approval.sudo().approver_ids

            selected_user_ids = set(approvers.ids)

            lines_to_remove = current_lines.filtered(
                lambda line: line.user_id and line.user_id.id not in selected_user_ids
            )
            if lines_to_remove:
                lines_to_remove.unlink()

            existing_user_ids = set(approval.sudo().approver_ids.mapped("user_id").ids)

            for user in approvers:
                if user.id in existing_user_ids:
                    continue

                vals = {}

                if inverse_name in RequestApprover._fields:
                    vals[inverse_name] = approval.id

                if "user_id" in RequestApprover._fields:
                    vals["user_id"] = user.id

                if "required" in RequestApprover._fields:
                    vals["required"] = True

                if "status" in RequestApprover._fields:
                    vals["status"] = "new"

                RequestApprover.create(vals)


    @api.model
    def _zofirm_get_sign_template_from_payload(self, payload):
        """
        Get original sign.template used by employee after placing signature fields.
        """
        payload = payload or {}
        simple_fields = payload.get("simple_fields") or {}

        template_id = simple_fields.get("template_id")
        if not template_id:
            return self.env["sign.template"]

        return self.env["sign.template"].sudo().browse(template_id).exists()


    @api.model
    def _zofirm_get_sign_template_link_html(self, sign_template):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        url = "%s/web#id=%s&model=sign.template&view_type=form" % (
            base_url,
            sign_template.id,
        )
        label = _("Open Signature Template")
        return Markup('<a href="%s" target="_blank">%s</a>') % (url, label)


    @api.model
    def _zofirm_prepare_approval_pdf_attachment(self, contract, approval, company, sign_template=False):
        """
        For signature approval, use the same PDF attached to sign.template when available.
        This keeps the same base document used by the employee.
        Signature boxes themselves are not embedded in PDF; they are opened via Sign Template Editor.
        """
        source_attachment = False

        if sign_template:
            source_attachment = getattr(sign_template, "sijil_contract_attachment_id", False)

        if source_attachment:
            return source_attachment.sudo().copy(
                {
                    "res_model": "approval.request",
                    "res_id": approval.id,
                    "name": source_attachment.name,
                }
            )

        return self._zofirm_create_contract_pdf_attachment(
            contract=contract,
            approval=approval,
            company=company,
        )


    def action_zofirm_open_sign_template_editor(self):
        self.ensure_one()

        if not self.zofirm_sign_template_id:
            raise UserError(_("No Sign Template linked to this approval request."))

        return {
            "type": "ir.actions.client",
            "tag": "sign.Template",
            "name": _("Template Editor"),
            "params": {"id": self.zofirm_sign_template_id.id},
            "context": {
                "active_model": "sign.template",
                "active_id": self.zofirm_sign_template_id.id,
                "default_template_id": self.zofirm_sign_template_id.id,
            },
        }
    @api.model
    def _zofirm_get_contract_approval_users_for_company(self, company):
        """
        Users selected from:
        Settings -> Sijil Email -> Contract Approval

        They receive and approve all contract approval requests for this company.
        Admin remains direct sender and full manager, but requests are not sent
        to admins unless they are selected in this company field.
        """
        if not company:
            company = self.env.company

        users = company.sudo().sijil_contract_approval_user_ids.filtered(
            lambda user: user.active and (not hasattr(user, "share") or not user.share)
        )

        if not users:
            raise UserError(
                _(
                    "No Contract Approval users configured for company: %s.\n"
                    "Please go to Settings > Sijil Email > Contract Approval and select at least one user."
                )
                % company.display_name
            )

        users = users.filtered(
            lambda user: not hasattr(user, "company_ids") or company in user.company_ids
        )

        if not users:
            raise UserError(
                _(
                    "The selected Contract Approval users do not have access to company: %s.\n"
                    "Please add the company to their Allowed Companies or select another user."
                )
                % company.display_name
            )

        return users

    @api.model
    def _zofirm_get_or_create_contract_approval_category(self, company):
        """
        One Approval Type per company.
        Example:
        Contract Send Approval - Sijilacc
        """
        Category = self.env["approval.category"].with_company(company).sudo()

        category_name = "Contract Send Approval - %s" % company.display_name

        domain = [("name", "=", category_name)]
        if "company_id" in Category._fields:
            domain.append(("company_id", "=", company.id))

        category = Category.search(domain, limit=1)

        if not category:
            vals = {"name": category_name}

            if "company_id" in Category._fields:
                vals["company_id"] = company.id

            category = Category.create(vals)

        self._zofirm_sync_category_contract_approvers(category, company)

        return category

    
    @api.model
    def _zofirm_sync_category_contract_approvers(self, category, company):
        """
        Sync Approval Type approvers from the company's Contract Approval users.
        """
        approvers = self._zofirm_get_contract_approval_users_for_company(company)

        if "approver_ids" not in category._fields:
            return approvers

        CategoryApprover = self.env["approval.category.approver"].with_company(company).sudo()

        current_lines = category.sudo().approver_ids
        selected_user_ids = set(approvers.ids)

        lines_to_remove = current_lines.filtered(
            lambda line: line.user_id and line.user_id.id not in selected_user_ids
        )
        if lines_to_remove:
            lines_to_remove.unlink()

        existing_user_ids = set(category.sudo().approver_ids.mapped("user_id").ids)

        for user in approvers:
            if user.id in existing_user_ids:
                continue

            vals = {}

            if "category_id" in CategoryApprover._fields:
                vals["category_id"] = category.id

            if "user_id" in CategoryApprover._fields:
                vals["user_id"] = user.id

            if "required" in CategoryApprover._fields:
                vals["required"] = True

            if "company_id" in CategoryApprover._fields:
                vals["company_id"] = company.id

            CategoryApprover.create(vals)

        return approvers

    def _zofirm_get_request_status(self):
        self.ensure_one()

        if "request_status" in self._fields:
            return self.request_status

        if "status" in self._fields:
            return self.status

        if "state" in self._fields:
            return self.state

        return False

    def _zofirm_is_request_approved(self):
        self.ensure_one()
        return self._zofirm_get_request_status() in ("approved", "done")

    # ---------------------------------------------------------
    # Create Approval Request
    # ---------------------------------------------------------
    @api.model
    def _zofirm_create_contract_send_approval(
        self,
        contract,
        action_type,
        payload=None,
        sign_request=False,
    ):
        if not contract:
            raise UserError(_("Contract not found."))

        company = self._zofirm_get_contract_company(contract)
        approvers = self._zofirm_get_contract_approval_users_for_company(company)
        category = self._zofirm_get_or_create_contract_approval_category(company)

        sign_template = False
        if action_type == "sign_send_request":
            sign_template = self._zofirm_get_sign_template_from_payload(payload)

        Approval = self.with_company(company).with_context(
            allowed_company_ids=[company.id],
            company_id=company.id,
        ).sudo()

        existing = Approval.search(
            [
                ("zofirm_contract_id", "=", contract.id),
                ("zofirm_contract_action_type", "=", action_type),
                ("zofirm_contract_action_done", "=", False),
            ],
            limit=1,
        )

        if existing and existing._zofirm_get_request_status() in ("new", "pending"):
            return self._zofirm_notification(
                _("Approval Already Requested"),
                _("There is already a pending approval request for this contract in Approvals."),
                "warning",
            )

        action_label = dict(self._fields["zofirm_contract_action_type"].selection).get(
            action_type,
            action_type,
        )

        vals = {
            "name": _("%s - %s") % (action_label, contract.display_name),
            "category_id": category.id,
            "zofirm_contract_id": contract.id,
            "zofirm_contract_action_type": action_type,
            "zofirm_contract_payload_json": json.dumps(payload or {}, default=str),
            "zofirm_sign_request_id": sign_request.id if sign_request else False,
            "zofirm_sign_template_id": sign_template.id if sign_template else False,
        }

        if "request_owner_id" in Approval._fields:
            vals["request_owner_id"] = self.env.user.id

        if "company_id" in Approval._fields:
            vals["company_id"] = company.id

        if "reason" in Approval._fields:
            vals["reason"] = _(
                "User: %s\n"
                "Company: %s\n"
                "Contract: %s\n"
                "Requested Action: %s"
            ) % (
                self.env.user.display_name,
                company.display_name,
                contract.display_name,
                action_label,
            )

        approval = Approval.create(vals)

        self._zofirm_sync_request_contract_approvers(approval, approvers)

        contract_screen_link = self._zofirm_get_contract_link_html(contract)

        contract_pdf_attachment = self._zofirm_prepare_approval_pdf_attachment(
            contract=contract,
            approval=approval,
            company=company,
            sign_template=sign_template,
        )

        approval.write({
            "zofirm_contract_pdf_attachment_id": contract_pdf_attachment.id,
        })

        contract_pdf_link = self._zofirm_get_attachment_link_html(
            contract_pdf_attachment,
            _("Open Contract PDF"),
        )

        signature_template_line = Markup("")
        if sign_template:
            signature_template_line = Markup(
                "<br/><b>Signature Fields:</b> %s"
            ) % self._zofirm_get_sign_template_link_html(sign_template)

        approval.message_post(
            body=Markup(
                "Contract send approval request created.<br/>"
                "<b>Contract Screen:</b> %s<br/>"
                "<b>Contract PDF:</b> %s"
                "%s<br/>"
                "<b>Company:</b> %s<br/>"
                "<b>Requested Action:</b> %s"
            ) % (
                contract_screen_link,
                contract_pdf_link,
                signature_template_line,
                company.display_name,
                action_label,
            ),
            attachment_ids=[contract_pdf_attachment.id],
        )

        if hasattr(approval, "action_confirm"):
            approval.action_confirm()

        approval_url = "%s/web#id=%s&model=approval.request&view_type=form" % (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url"),
            approval.id,
        )

        approval_link = Markup('<a href="%s" target="_blank">%s</a>') % (
            approval_url,
            approval.display_name,
        )

        contract.with_company(company).sudo().message_post(
            body=Markup(
                "Approval request has been created in Approvals.<br/>"
                "<b>Action:</b> %s<br/>"
                "<b>Company:</b> %s<br/>"
                "<b>Approval Request:</b> %s"
            ) % (
                action_label,
                company.display_name,
                approval_link,
            )
        )

        for approver in approvers:
            approval.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=approver.id,
                summary=_("Contract approval required"),
                note=Markup(
                    "Please review this contract approval request.<br/>"
                    "<b>Contract Screen:</b> %s<br/>"
                    "<b>Contract PDF:</b> %s"
                    "%s<br/>"
                    "<b>Company:</b> %s<br/>"
                    "<b>Action:</b> %s"
                ) % (
                    contract_screen_link,
                    contract_pdf_link,
                    signature_template_line,
                    company.display_name,
                    action_label,
                ),
            )

        return self._zofirm_notification(
            _("Approval Requested"),
            _("The request has been created in Approvals and is waiting for approval."),
            "warning",
        )
        
        

    # ---------------------------------------------------------
    # Execute After Approval
    # ---------------------------------------------------------
    def action_approve(self):
        res = super().action_approve()

        for request in self:
            if not request.zofirm_contract_id:
                continue

            if request.zofirm_contract_action_done:
                continue

            if not request._zofirm_is_request_approved():
                continue

            request.sudo()._zofirm_execute_contract_action_after_approval()

        return res

    def _zofirm_execute_contract_action_after_approval(self):
        self.ensure_one()

        contract = self.zofirm_contract_id
        if not contract:
            return False

        company = self._zofirm_get_contract_company(contract)

        request = self.with_company(company).with_context(
            allowed_company_ids=[company.id],
            company_id=company.id,
            **{BYPASS_CTX_KEY: True},
        )

        payload = json.loads(request.zofirm_contract_payload_json or "{}")

        try:
            if request.zofirm_contract_action_type == "mail_send":
                result = request._zofirm_execute_mail_send(payload)

            elif request.zofirm_contract_action_type == "sign_send_request":
                result = request._zofirm_execute_sign_send_request(payload)

            elif request.zofirm_contract_action_type == "sign_completed_document":
                result = request._zofirm_execute_completed_document(payload)

            else:
                raise UserError(_("Unsupported contract approval action."))

            request.write(
                {
                    "zofirm_contract_action_done": True,
                    "zofirm_contract_error_message": False,
                }
            )

            contract.with_company(company).sudo().message_post(
                body=_("Approved action executed successfully from Approvals.")
            )

            return result

        except Exception as e:
            request.write({"zofirm_contract_error_message": str(e)})
            raise

    def _zofirm_execute_mail_send(self, payload):
        company = self._zofirm_get_contract_company(self.zofirm_contract_id)

        ctx = dict(payload.get("context") or {})
        ctx.update(
            {
                BYPASS_CTX_KEY: True,
                "allowed_company_ids": [company.id],
                "company_id": company.id,
            }
        )

        Compose = self.env["mail.compose.message"].with_company(company).with_context(ctx)

        vals = {}

        for fname in [
            "composition_mode",
            "model",
            "res_id",
            "subject",
            "body",
            "email_from",
            "email_to",
            "email_cc",
            "reply_to",
            "auto_delete",
        ]:
            if fname in Compose._fields and fname in payload:
                vals[fname] = payload[fname]

        for fname in ["template_id", "subtype_id"]:
            if fname in Compose._fields and payload.get(fname):
                vals[fname] = payload[fname]

        if "res_ids" in Compose._fields and payload.get("res_ids"):
            vals["res_ids"] = payload["res_ids"]

        if "partner_ids" in Compose._fields and payload.get("partner_ids"):
            vals["partner_ids"] = [(6, 0, payload["partner_ids"])]

        if "attachment_ids" in Compose._fields and payload.get("attachment_ids"):
            vals["attachment_ids"] = [(6, 0, payload["attachment_ids"])]

        wizard = Compose.create(vals)
        return wizard.with_context(**{BYPASS_CTX_KEY: True}).action_send_mail()

    def _zofirm_execute_sign_send_request(self, payload):
        company = self._zofirm_get_contract_company(self.zofirm_contract_id)

        ctx = dict(payload.get("context") or {})
        ctx.update(
            {
                BYPASS_CTX_KEY: True,
                "allowed_company_ids": [company.id],
                "company_id": company.id,
            }
        )

        SignWizard = self.env["sign.send.request"].with_company(company).with_context(ctx)

        vals = {}

        for fname, value in (payload.get("simple_fields") or {}).items():
            if fname in SignWizard._fields:
                vals[fname] = value

        for fname, ids in (payload.get("many2many_fields") or {}).items():
            if fname in SignWizard._fields:
                vals[fname] = [(6, 0, ids)]

        if "signer_ids" in SignWizard._fields and payload.get("signer_ids"):
            vals["signer_ids"] = [
                (0, 0, line_vals)
                for line_vals in payload["signer_ids"]
            ]

        wizard = SignWizard.create(vals)
        method_name = payload.get("method_name") or "send_request"

        return wizard.with_context(**{BYPASS_CTX_KEY: True})._zofirm_call_parent_sign_send_method(
            method_name
        )

    def _zofirm_execute_completed_document(self, payload):
        company = self._zofirm_get_contract_company(self.zofirm_contract_id)

        sign_request = self.zofirm_sign_request_id
        if not sign_request:
            raise UserError(_("Sign request not found."))

        method_name = payload.get("method_name") or "action_validate_and_send_completed_document"

        return sign_request.with_company(company).with_context(
            allowed_company_ids=[company.id],
            company_id=company.id,
            **{BYPASS_CTX_KEY: True},
        )._zofirm_call_parent_completed_document_method(method_name)


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    def _zofirm_normalize_ids(self, value):
        if not value:
            return []

        if hasattr(value, "ids"):
            return value.ids

        if isinstance(value, int):
            return [value]

        if isinstance(value, (list, tuple)):
            return [v for v in value if isinstance(v, int)]

        if isinstance(value, str):
            return [
                int(v)
                for v in value.replace("[", "").replace("]", "").split(",")
                if v.strip().isdigit()
            ]

        return []

    def _zofirm_get_contract_from_mail_composer(self):
        self.ensure_one()

        model = getattr(self, "model", False) or self.env.context.get("default_model")
        res_ids = []

        if "res_ids" in self._fields and self.res_ids:
            res_ids = self._zofirm_normalize_ids(self.res_ids)

        if not res_ids and "res_id" in self._fields and self.res_id:
            res_ids = [self.res_id]

        if not res_ids:
            res_ids = self._zofirm_normalize_ids(
                self.env.context.get("default_res_ids")
                or self.env.context.get("active_ids")
                or self.env.context.get("default_res_id")
                or self.env.context.get("active_id")
            )

        if model != "zofirm.contract" or not res_ids:
            return self.env["zofirm.contract"]

        return self.env["zofirm.contract"].browse(res_ids[0]).exists()

    def _zofirm_mail_payload(self):
        self.ensure_one()

        payload = {
            "context": dict(self.env.context),
            "partner_ids": self.partner_ids.ids if "partner_ids" in self._fields else [],
            "attachment_ids": self.attachment_ids.ids if "attachment_ids" in self._fields else [],
        }

        for fname in [
            "composition_mode",
            "model",
            "res_id",
            "res_ids",
            "subject",
            "body",
            "email_from",
            "email_to",
            "email_cc",
            "reply_to",
            "auto_delete",
            "template_id",
            "subtype_id",
        ]:
            if fname not in self._fields:
                continue

            field = self._fields[fname]
            value = self[fname]

            if field.type == "many2one":
                payload[fname] = value.id if value else False
            elif field.type in ("many2many", "one2many"):
                payload[fname] = value.ids
            else:
                payload[fname] = value

        return payload

    def action_send_mail(self):
        self.ensure_one()

        if self.env.context.get(BYPASS_CTX_KEY):
            return super().action_send_mail()

        approval_model = self.env["approval.request"]

        if approval_model._zofirm_is_direct_contract_sender():
            return super().action_send_mail()

        contract = self._zofirm_get_contract_from_mail_composer()
        if not contract:
            return super().action_send_mail()

        return approval_model._zofirm_create_contract_send_approval(
            contract=contract,
            action_type="mail_send",
            payload=self._zofirm_mail_payload(),
        )

