import logging
import re

from odoo import api, models  # type: ignore

_logger = logging.getLogger(__name__)


# Mail models whose outgoing mails should inherit the company-level
# "Sijil Email Defaults" (FROM / CC / Outgoing Mail Server).
_SIJIL_EMAIL_TARGET_MODELS = ("sign.request", "sale.order")

# Models for which email_from is FORCED (not additive). sign.request has no
# user-facing FROM field on its wizard, so whatever sign sets internally
# (always the logged-in user's email) is never a deliberate user choice -
# and if the pinned SMTP server authenticates as sales@sijilacc.com, it
# cannot actually send-as abosetta@zofirm.com without SendAs permission
# (Outlook returns 5.2.252 SendAsDenied). For sale.order we stay additive
# so the salesperson's explicit composer choice wins.
_SIJIL_EMAIL_FORCE_FROM_MODELS = ("sign.request",)

# sign.request invitation emails always embed this URL. Used as a
# last-resort fingerprint when sign creates mail.mail with blank
# model/res_id AND a blank-model mail.message (observed on Odoo 19
# Enterprise).
_SIGN_URL_RE = re.compile(r"/sign/(?:document|sign)/(\d+)")


class MailMail(models.Model):
    _inherit = "mail.mail"

    def _sijil_resolve_origin(self, vals):
        """Return (model, res_id, record) for the business record this mail
        originates from, or (False, False, False).

        Tried in order:
        1. mail.mail vals['model'] + vals['res_id']      (sale composer path)
        2. vals['mail_message_id'].model + .res_id        (generic mail.thread)
        3. Regex '/sign/document/<id>/' in body_html      (sign invite path)

        If (3) matches but the record can't be browsed, returns
        ('sign.request', 0, False) so the caller can still fall back to
        env.company for the defaults.
        """
        model = vals.get("model")
        res_id = vals.get("res_id")
        if model and res_id:
            record = self.env[model].sudo().browse(res_id).exists()
            return model, res_id, record

        message_id = vals.get("mail_message_id")
        if message_id:
            message = self.env["mail.message"].sudo().browse(message_id).exists()
            if message and message.model and message.res_id:
                record = self.env[message.model].sudo().browse(message.res_id).exists()
                return message.model, message.res_id, record

        body_html = vals.get("body_html") or ""
        if "/sign/" in body_html:
            match = _SIGN_URL_RE.search(body_html)
            if match:
                req_id = int(match.group(1))
                record = self.env["sign.request"].sudo().browse(req_id).exists()
                return "sign.request", req_id, record
            # Body looks like a sign mail but no request id extractable:
            # still return a sentinel so company-level defaults apply.
            return "sign.request", 0, False

        return False, False, False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            model, res_id, record = self._sijil_resolve_origin(vals)
            if model not in _SIJIL_EMAIL_TARGET_MODELS:
                continue

            company = getattr(record, "company_id", False) if record else False
            if not company:
                company = self.env.company

            default_from = getattr(company, "sijil_sales_email_from", False)
            default_cc = getattr(company, "sijil_sales_email_cc", False)
            default_server = getattr(company, "sijil_sales_mail_server_id", False)

            # Nothing configured for this company -> no-op.
            if not (default_from or default_cc or default_server):
                continue

            applied = []
            force_from = model in _SIJIL_EMAIL_FORCE_FROM_MODELS
            if default_from and (force_from or not vals.get("email_from")):
                previous_from = vals.get("email_from")
                vals["email_from"] = default_from
                if force_from and previous_from and previous_from != default_from:
                    applied.append(f"email_from(forced, was={previous_from!r})")
                else:
                    applied.append("email_from")
            if default_cc and not vals.get("email_cc"):
                vals["email_cc"] = default_cc
                applied.append("email_cc")
            if default_server and not vals.get("mail_server_id"):
                vals["mail_server_id"] = default_server.id
                applied.append("mail_server_id")

            if record and not vals.get("model"):
                vals["model"] = model
            if record and not vals.get("res_id"):
                vals["res_id"] = res_id

            if applied:
                _logger.info(
                    "Sijil Email Defaults applied %s to mail.mail for "
                    "%s(res_id=%s, company=%s, subject=%r)",
                    applied, model, res_id, company.display_name,
                    vals.get("subject") or "",
                )

        return super().create(vals_list)
