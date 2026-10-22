from odoo import _, api, fields, models  # noqa: I001
from odoo.exceptions import UserError

BYPASS_CTX_KEY = "zofirm_contract_approval_bypass"


class SignSendRequest(models.TransientModel):
    _inherit = "sign.send.request"

    def _zofirm_get_contract_from_sign_wizard(self): 
        self.ensure_one()

        if hasattr(self, "_sijil_get_template_and_contract"):
            _template, contract = self._sijil_get_template_and_contract()
            if contract:
                return contract

        template = self.template_id if "template_id" in self._fields else False

        if template and getattr(template, "sijil_contract_id", False):
            return template.sijil_contract_id

        return self.env["zofirm.contract"]

    def _zofirm_sign_send_payload(self, method_name):
        self.ensure_one()

        simple_fields = {}
        many2many_fields = {}
        signer_lines = []

        for fname in [
            "template_id",
            "subject",
            "filename",
            "validity",
            "message",
            "body",
            "reference",
            "signing_order",
        ]:
            if fname not in self._fields:
                continue

            field = self._fields[fname]
            value = self[fname]

            if field.type == "many2one":
                simple_fields[fname] = value.id if value else False
            else:
                simple_fields[fname] = value

        for fname in ["partner_ids", "cc_partner_ids", "attachment_ids"]:
            if fname in self._fields:
                many2many_fields[fname] = self[fname].ids

        if "signer_ids" in self._fields:
            for line in self.signer_ids:
                line_vals = {}

                for fname in [
                    "partner_id",
                    "role_id",
                    "mail_sent_order",
                    "sms_number",
                    "auth_method",
                ]:
                    if fname not in line._fields:
                        continue

                    field = line._fields[fname]
                    value = line[fname]

                    if field.type == "many2one":
                        line_vals[fname] = value.id if value else False
                    else:
                        line_vals[fname] = value

                signer_lines.append(line_vals)

        return {
            "method_name": method_name,
            "context": dict(self.env.context),
            "simple_fields": simple_fields,
            "many2many_fields": many2many_fields,
            "signer_ids": signer_lines,
        }

    def _zofirm_call_parent_sign_send_method(self, method_name):
        for candidate in [
            method_name,
            "send_request",
            "action_send_request",
            "action_send",
        ]:
            parent = getattr(super(SignSendRequest, self), candidate, None)
            if parent:
                return parent()

        raise UserError(
            _("Could not find the original Sign send method. Please check the real button method in Developer Mode.")
        )

    def _zofirm_intercept_sign_send(self, method_name):
        self.ensure_one()

        if self.env.context.get(BYPASS_CTX_KEY):
            return self._zofirm_call_parent_sign_send_method(method_name)

        approval_model = self.env["approval.request"]

        if approval_model._zofirm_is_direct_contract_sender():
            return self._zofirm_call_parent_sign_send_method(method_name)

        contract = self._zofirm_get_contract_from_sign_wizard()
        if not contract:
            return self._zofirm_call_parent_sign_send_method(method_name)

        return approval_model._zofirm_create_contract_send_approval(
            contract=contract,
            action_type="sign_send_request",
            payload=self._zofirm_sign_send_payload(method_name),
        )

    def send_request(self):
        return self._zofirm_intercept_sign_send("send_request")

    def action_send_request(self):
        return self._zofirm_intercept_sign_send("action_send_request")

    def action_send(self):
        return self._zofirm_intercept_sign_send("action_send")


class SignRequest(models.Model):
    _inherit = "sign.request"

    def _zofirm_get_contract_from_sign_request(self):
        self.ensure_one()

        template = self.template_id

        if template and getattr(template, "sijil_contract_id", False):
            return template.sijil_contract_id

        return self.env["zofirm.contract"]

    def _zofirm_call_parent_completed_document_method(self, method_name):
        for candidate in [
            method_name,
            "action_validate_and_send_completed_document",
            "validate_and_send_completed_document",
            "action_send_completed_document",
            "send_completed_document",
        ]:
            parent = getattr(super(SignRequest, self), candidate, None)
            if parent:
                return parent()

        raise UserError(
            _("Could not find the original completed-document method. This button may be handled by a Sign JS/controller route in this Odoo version.")
        )

    def _zofirm_intercept_completed_document(self, method_name):
        self.ensure_one()

        if self.env.context.get(BYPASS_CTX_KEY):
            return self._zofirm_call_parent_completed_document_method(method_name)

        approval_model = self.env["approval.request"]

        if approval_model._zofirm_is_direct_contract_sender():
            return self._zofirm_call_parent_completed_document_method(method_name)

        contract = self._zofirm_get_contract_from_sign_request()
        if not contract:
            return self._zofirm_call_parent_completed_document_method(method_name)

        return approval_model._zofirm_create_contract_send_approval(
            contract=contract,
            action_type="sign_completed_document",
            payload={"method_name": method_name},
            sign_request=self,
        )

    def action_validate_and_send_completed_document(self):
        return self._zofirm_intercept_completed_document("action_validate_and_send_completed_document")

    def validate_and_send_completed_document(self):
        return self._zofirm_intercept_completed_document("validate_and_send_completed_document")

    def action_send_completed_document(self):
        return self._zofirm_intercept_completed_document("action_send_completed_document")

    def send_completed_document(self):
        return self._zofirm_intercept_completed_document("send_completed_document")
    
    
    
    def _sync_signed_to_contract(self):
        """When request is signed, mark related contract signed."""
        for req in self:
            template = req.template_id
            if not template:
                continue

            # Sijil
            contract = getattr(template, "sijil_contract_id", False)
            if contract:
                vals = {"sign_request_id": req.id}
                if req.state in ("signed", "completed"):
                    vals.update({"is_signed": True, "signed_on": fields.Datetime.now()})
                contract.sudo().write(vals)
                continue

            # Zofirm (لو عندك نفس الربط في template)
            contract = getattr(template, "zofirm_contract_id", False)
            if contract:
                vals = {"sign_request_id": req.id}
                if req.state in ("signed", "completed"):
                    vals.update({"is_signed": True, "signed_on": fields.Datetime.now()})
                contract.sudo().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._sync_signed_to_contract()
        return recs

    def write(self, vals):
        res = super().write(vals)
        # لو الحالة اتغيرت (خصوصًا إلى signed/completed) نعمل sync
        if "state" in vals or "template_id" in vals:
            self._sync_signed_to_contract()
        return res


# -----------------------------------------------------------------------------------
# sign.request.item — workaround for Odoo Enterprise whatsapp_sign bug
# -----------------------------------------------------------------------------------

class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    def _send_signature_access_message(self):
        if len(self) <= 1:
            return super()._send_signature_access_message()
        for item in self:
            super(SignRequestItem, item)._send_signature_access_message()