from odoo import api, fields, models, Command, _  # noqa: I001
from odoo.exceptions import ValidationError, AccessError, UserError
from odoo.tools import html2plaintext
from odoo.tools.float_utils import float_compare
from lxml import etree, html
from markupsafe import Markup, escape
from copy import deepcopy
import math


SIJIL_COMPANY_ID = 2
REPORT_XMLID_ZOFIRM = "zofirm_contract.action_report_zofirm_contract"
REPORT_XMLID_SIJIL = "zofirm_contract.action_report_contract"
REPORT_XMLID_SIJIL_MAINTENANCE = (
    "zofirm_contract.action_report_sijil_maintenance_contract"
)


class SaleOrder(models.Model):
    _inherit = "sale.order"
    


    def _get_contract_section_name(self, line):
        """Return a section label using the matching product translation.

        A standard Odoo section has no product_id.  We therefore first use the
        optional custom section_product_id when it is populated; otherwise we
        resolve the product.template by the stored section text, checking the
        English name, the partner language, then the other active languages.
        The final product name is always read in the partner language.
        """
        self.ensure_one()

        if not line:
            return ""

        section_name = (getattr(line, "name", False) or "").strip()
        if not section_name:
            return ""

        partner_lang = self.partner_id.lang or self.env.lang or "en_US"

        # Best case: the section is explicitly linked to a product by the
        # custom field.  This also avoids ambiguity when product names repeat.
        line_fields = getattr(line, "_fields", {})
        if "section_product_id" in line_fields and line.section_product_id:
            return line.section_product_id.product_tmpl_id.with_context(
                lang=partner_lang
            ).name or section_name

        ProductTemplate = self.env["product.template"].sudo().with_context(
            active_test=False
        )

        # Most existing sections in this database were saved with the English
        # product name, so check English first.
        product_tmpl = ProductTemplate.with_context(lang="en_US").search(
            [("name", "=ilike", section_name)],
            limit=1,
        )

        # The section may already have been created in the customer's language.
        if not product_tmpl:
            product_tmpl = ProductTemplate.with_context(lang=partner_lang).search(
                [("name", "=ilike", section_name)],
                limit=1,
            )

        # Final fallback: the partner may have changed language after the quote
        # was created, so the stored section can be in another active language.
        if not product_tmpl:
            active_lang_codes = self.env["res.lang"].sudo().search(
                [("active", "=", True)]
            ).mapped("code")
            for lang_code in active_lang_codes:
                if lang_code in ("en_US", partner_lang):
                    continue
                product_tmpl = ProductTemplate.with_context(lang=lang_code).search(
                    [("name", "=ilike", section_name)],
                    limit=1,
                )
                if product_tmpl:
                    break

        if not product_tmpl:
            return section_name

        return product_tmpl.with_context(lang=partner_lang).name or section_name

    bookkeeping_fees = fields.Text(string="Bookkeeping Fees")

    work_scope = fields.Text(
        string="SOW",
        copy=True,
    )

    work_scope_qut = fields.Text(
        default="الاستفسار والملاحظة والاطلاع، ثم إعداد نتائج الاطلاع على المستندات الداعمة للتقرير.",
        copy=True,
    )
    
    work_scope_qut_en = fields.Text(
        string="SOW QUT English",
        default="Performing agreed-upon procedures and preparing a report presenting factual findings based on the agreed scope of work.",
        copy=True,
    )
        
    @api.constrains("work_scope_qut")
    def _check_work_scope_qut_limits(self):
        for order in self:
            if not order.work_scope_qut:
                continue

            text = (
                order.work_scope_qut
                .replace("\r\n", "\n")
                .replace("\r", "\n")
            )

            lines = text.split("\n")

            additional_lines = lines[1:]

            while additional_lines and not additional_lines[-1].strip():
                additional_lines.pop()

            if len(additional_lines) > 4:
                raise ValidationError(
                    _(
                        "يمكن إضافة 4 سطور فقط بعد السطر الأول "
                        "في نطاق أعمال عرض سعر تقرير 4400"
                    )
                )
                
            additional_text = "".join(additional_lines)

            characters_count = len(additional_text)

            if characters_count > 750:
                raise ValidationError(
                    _(
                        "المحتوى بعد السطر الأول لا يمكن أن يتجاوز ""750 حرفًا  \n"
                        # "العدد الحالي: %s حرف"
                    )
                    # % characters_count
                )
    
    
    
    fees_payment_line_ids = fields.One2many(
        "sale.order.fees.line",
        "order_id",
        string="Fees and Payments",
    )

    can_manage_contracts = fields.Boolean(
        string="Can Manage Contracts",
        compute="_compute_can_manage_contracts",
        store=False,
    )
    is_sijil_company = fields.Boolean(
        string="Is Sijil Company",
        compute="_compute_is_sijil_company",
        store=False,
    )
    has_contract = fields.Boolean(
        string="Has Contract",
        compute="_compute_has_contract",
        store=False,
    )

    fees_percentage_total = fields.Float(
        string="Fees Total (%)",
        compute="_compute_fees_percentage_total",
        store=False,
    )

    fees_percentage_full = fields.Boolean(
        string="Fees % Full",
        compute="_compute_fees_percentage_total",
        store=False,
    )
    
    is_company_1 = fields.Boolean(
    compute="_compute_button_company_visibility",
    store=False,
    )

    is_company_1_or_2 = fields.Boolean(
        compute="_compute_button_company_visibility",
        store=False,
    )


    @api.depends_context("allowed_company_ids")
    def _compute_button_company_visibility(self):
        active_company_id = self.env.company.id

        for order in self:
            order.is_company_1 = active_company_id == 1
            order.is_company_1_or_2 = active_company_id in (1, 2)

    # def action_print_zofirm(self):
    #     self.ensure_one()
    #     return self.env.ref("zofirm_contract.action_report_saleorder_financial_offer").report_action(self)
    
    def action_print_zofirm(self):
        self.ensure_one()

        report = self.env.ref(
            "zofirm_contract.action_report_saleorder_financial_offer_without_total",
            raise_if_not_found=False,
        )

        if not report:
            raise UserError(_("Quotation report is not configured."))

        return report.with_context(
            lang=self.partner_id.lang or self.env.lang
        ).report_action(self)
        
    def action_print_4400_qut(self):
        self.ensure_one()

        report = self.env.ref(
            "zofirm_contract.action_report_saleorder_financial_offer_4400",
            raise_if_not_found=False,
        )

        if not report:
            raise UserError(_("4400 quotation report is not configured."))

        return report.report_action(self)

    def _get_note_without_leading_blank_lines(self):
        self.ensure_one()

        note_text = html2plaintext(self.note or "")

        # تنظيف المسافات والمحارف غير المرئية القادمة من محرر HTML
        note_text = (
            note_text.replace("\u00a0", " ")  # Non-breaking space
            .replace("\u200b", "")  # Zero-width space
            .replace("\ufeff", "")  # BOM / invisible character
            .replace("*", "")
        )

        lines = note_text.splitlines()

        # حذف الأسطر الفارغة من البداية فقط
        while lines and not lines[0].strip():
            lines.pop(0)

        # حذف الأسطر الفارغة من النهاية مع الحفاظ على الأسطر الداخلية
        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Financial offer note pagination
    # -------------------------------------------------------------------------
    # IMPORTANT:
    # The helpers below NEVER convert the note to plain text for output.
    # html2plaintext() is used only to ESTIMATE rendered height. The returned
    # page fragments are always built from the original HTML, so bullets, bold,
    # line breaks, inline styles and RTL/LTR formatting remain intact.

    def _financial_note_estimated_lines(self, html_fragment, chars_per_line=58):
        """Estimate visual lines without changing the HTML that will be printed."""
        text = html2plaintext(str(html_fragment or ""))
        text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")

        raw_lines = text.splitlines() or [text]
        total = 0.0
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                total += 1.0
                continue
            # Approximation only; output HTML is untouched.
            total += max(1.0, math.ceil(len(line) / float(chars_per_line)))

        return max(total, 1.0)

    def _financial_note_first_page_capacity(self, financial_lines):
        """
        Estimate how many note text-lines fit below the financial table on the
        last financial page, based on the CURRENT report CSS dimensions.

        This protects the VAT/Total block from being pushed outside the fixed
        1280px page while keeping its visual position unchanged.
        """
        # CSS-derived approximate free height before the note starts:
        # 1280px page - 60mm top padding - 25mm bottom padding
        # - title - table header - separator ~= 690px before table data rows.
        remaining_px = 690.0

        for line in financial_lines:
            display_type = getattr(line, "display_type", False)

            if display_type in ("line_section", "line_subsection"):
                # Section row: 14mm min height + vertical padding.
                remaining_px -= 75.0
                continue

            if display_type == "line_note":
                # Order-line note row: estimate its wrapped height.
                row_html = getattr(line, "name", "") or ""
                row_lines = self._financial_note_estimated_lines(
                    escape(row_html), chars_per_line=72
                )
                remaining_px -= max(69.0, row_lines * 52.0 + 20.0)
                continue

            # Product/service row. 22mm is about 83px in CSS. Add a little
            # extra room when the description is likely to wrap.
            product_name = ""
            if getattr(line, "product_template_id", False):
                product_name = line.product_template_id.name or ""
            wrapped = max(1, math.ceil(len(product_name) / 52.0))
            remaining_px -= max(83.0, wrapped * 50.0)

        # .fin-note font-size is 30px on the report and line-height is 1.45.
        note_line_px = 43.5
        if remaining_px <= note_line_px:
            return 0.0
        return max(0.0, math.floor(remaining_px / note_line_px))

    def _financial_note_make_list_html(self, list_element, list_items, item_offset=0):
        """Rebuild one list fragment from original LI nodes and list attributes."""
        wrapper = deepcopy(list_element)
        for child in list(wrapper):
            wrapper.remove(child)

        # The wrapper text before the first <li> is preserved.
        wrapper.tail = None

        # Preserve ordered-list numbering when a list continues on a later page.
        if str(wrapper.tag).lower() == "ol" and item_offset:
            try:
                original_start = int(wrapper.get("start") or 1)
            except (TypeError, ValueError):
                original_start = 1
            wrapper.set("start", str(original_start + item_offset))

        for item in list_items:
            cloned_item = deepcopy(item)
            cloned_item.tail = item.tail
            wrapper.append(cloned_item)

        return etree.tostring(
            wrapper, encoding="unicode", method="html", with_tail=False
        )

    def _financial_note_units(self):
        """
        Build pagination units from the ORIGINAL note HTML.

        Paragraphs/divs stay intact. UL/OL lists are split at LI boundaries so
        long bullet lists can continue on another page without converting them
        to plain text or losing inline formatting inside each LI.
        """
        self.ensure_one()
        note_html = self.note or ""
        if not note_html:
            return []

        try:
            root = html.fragment_fromstring(str(note_html), create_parent="div")
        except (etree.ParserError, ValueError, TypeError):
            # Fail-safe: keep the exact original value as one safe fragment.
            return [
                {
                    "kind": "html",
                    "html": str(note_html),
                    "weight": self._financial_note_estimated_lines(note_html),
                }
            ]

        units = []

        # Preserve text that exists directly before the first element.
        if root.text:
            raw_text = str(escape(root.text))
            units.append(
                {
                    "kind": "html",
                    "html": raw_text,
                    "weight": self._financial_note_estimated_lines(raw_text),
                }
            )

        list_group = 0
        for child in root:
            tag = child.tag.lower() if isinstance(child.tag, str) else ""

            if tag in ("ul", "ol") and any(
                isinstance(li.tag, str) and li.tag.lower() == "li" for li in child
            ):
                list_group += 1
                li_index = 0
                for li in child:
                    if not isinstance(li.tag, str) or li.tag.lower() != "li":
                        continue
                    li_html = etree.tostring(
                        li, encoding="unicode", method="html", with_tail=False
                    )
                    units.append(
                        {
                            "kind": "list_item",
                            "group": list_group,
                            "list_element": child,
                            "item": li,
                            "item_index": li_index,
                            "weight": self._financial_note_estimated_lines(li_html),
                        }
                    )
                    li_index += 1

                # Preserve any whitespace/text after the whole list.
                if child.tail:
                    tail_html = str(escape(child.tail))
                    units.append(
                        {
                            "kind": "html",
                            "html": tail_html,
                            "weight": self._financial_note_estimated_lines(tail_html),
                        }
                    )
                continue

            child_html = etree.tostring(
                child, encoding="unicode", method="html", with_tail=True
            )
            units.append(
                {
                    "kind": "html",
                    "html": child_html,
                    "weight": self._financial_note_estimated_lines(child_html),
                }
            )

        return units

    def _financial_note_render_page_units(self, page_units):
        """Serialize one page while preserving the original HTML markup."""
        if not page_units:
            return Markup("")

        output = []
        index = 0
        while index < len(page_units):
            unit = page_units[index]

            if unit["kind"] != "list_item":
                output.append(unit["html"])
                index += 1
                continue

            group = unit["group"]
            list_element = unit["list_element"]
            first_item_index = unit["item_index"]
            items = []

            while (
                index < len(page_units)
                and page_units[index]["kind"] == "list_item"
                and page_units[index]["group"] == group
            ):
                items.append(page_units[index]["item"])
                index += 1

            output.append(
                self._financial_note_make_list_html(
                    list_element, items, item_offset=first_item_index
                )
            )

        return Markup("".join(output))

    def _get_financial_note_pages(self, last_financial_page_lines=None):
        """
        Return safe HTML fragments for the quotation note.

        Page 1 is sized for the space that remains beside VAT/Total on the last
        financial page. Continuation pages have a larger note-only capacity.
        No output conversion to plain text is performed.
        """
        self.ensure_one()

        note_html = self.note or ""
        if not note_html:
            return [Markup("")]

        units = self._financial_note_units()
        if not units:
            return [Markup(note_html)]

        first_capacity = self._financial_note_first_page_capacity(
            last_financial_page_lines or self.env["sale.order.line"]
        )

        # Continuation page: 1280px with the same 60mm / 25mm safe-area
        # padding and no title/table/totals. ~21 normal note lines is safe.
        continuation_capacity = 21.0

        pages = []
        current = []
        used = 0.0
        capacity = first_capacity
        current_list_group = None

        for unit in units:
            extra = unit["weight"]
            # A list has a small top/bottom browser margin. Count it once when
            # that list begins on a page. This affects pagination only.
            if unit["kind"] == "list_item" and current_list_group != unit["group"]:
                extra += 0.7

            # If the first page has no safe note space, or the next complete
            # HTML block does not fit there, move that block to a continuation
            # page rather than clipping it or pushing VAT/Total down.
            if not pages and not current and (capacity <= 0 or extra > capacity):
                pages.append([])
                capacity = continuation_capacity
                used = 0.0
                current_list_group = None
                extra = unit["weight"]
                if unit["kind"] == "list_item":
                    extra += 0.7

            if current and used + extra > capacity:
                pages.append(current)
                current = []
                used = 0.0
                capacity = continuation_capacity
                current_list_group = None
                extra = unit["weight"]
                if unit["kind"] == "list_item":
                    extra += 0.7

            current.append(unit)
            used += extra
            current_list_group = unit["group"] if unit["kind"] == "list_item" else None

        if current or not pages:
            pages.append(current)

        # IMPORTANT: if everything fits on one page, return the exact original
        # HTML value, untouched, so its rendering is byte-for-byte based on the
        # same note HTML that was printed before this pagination change.
        if len(pages) == 1:
            return [Markup(note_html)]

        return [self._financial_note_render_page_units(page) for page in pages]

    @api.depends("company_id")
    def _compute_can_manage_contracts(self):
        user = self.env.user
        is_admin = user.has_group("base.group_system")
        for order in self:
            if is_admin:
                order.can_manage_contracts = True
            elif order.company_id.id == SIJIL_COMPANY_ID:
                order.can_manage_contracts = user.has_group(
                    "zofirm_contract.group_sijil_contract_manager"
                )
            else:
                order.can_manage_contracts = user.has_group(
                    "zofirm_contract.group_zofirm_contract_manager"
                )

    @api.depends("company_id")
    def _compute_is_sijil_company(self):
        for order in self:
            order.is_sijil_company = order.company_id.id == SIJIL_COMPANY_ID

    @api.depends("company_id", "name")
    def _compute_has_contract(self):
        user = self.env.user
        if not (
            user.has_group("zofirm_contract.group_zofirm_contract_manager")
            or user.has_group("zofirm_contract.group_sijil_contract_manager")
            or user.has_group("base.group_system")
        ):
            for order in self:
                order.has_contract = False
            return

        Contract = self.env["zofirm.contract"].sudo()
        for order in self:
            domain = order._get_contract_domain(Contract, order)
            order.has_contract = bool(domain and Contract.search_count(domain))

    @api.depends("fees_payment_line_ids.percentage_total")
    def _compute_fees_percentage_total(self):
        for order in self:
            total = sum(order.fees_payment_line_ids.mapped("percentage_total") or [0.0])
            order.fees_percentage_total = total
            order.fees_percentage_full = (
                float_compare(total, 100.0, precision_digits=2) >= 0
            )

    def _get_contract_domain(self, Contract, order):
        domain = []
        link_candidates = ["order_id", "sale_order_id", "sale_id", "quotation_id"]
        link_field = next((f for f in link_candidates if f in Contract._fields), None)
        if link_field:
            domain.append((link_field, "=", order.id))
        else:
            name_candidates = [
                "order_name",
                "quotation",
                "quotation_name",
                "order_ref",
                "quote_ref",
                "sale_order_name",
            ]
            name_field = next(
                (f for f in name_candidates if f in Contract._fields), None
            )
            if name_field:
                domain.append((name_field, "=", order.name))
        if "company_id" in Contract._fields and order.company_id:
            domain.append(("company_id", "=", order.company_id.id))
        return domain

    def _get_contract_report_xmlid(self):
        self.ensure_one()
        return (
            REPORT_XMLID_SIJIL
            if self.company_id.id == SIJIL_COMPANY_ID
            else REPORT_XMLID_ZOFIRM
        )

    def _open_contract(self, contract):
        return {
            "type": "ir.actions.act_window",
            "name": _("Contract"),
            "res_model": "zofirm.contract",
            "view_mode": "form",
            "views": [
                (self.env.ref("zofirm_contract.view_zofirm_contract_form").id, "form")
            ],
            "target": "current",
            "res_id": contract.id,
        }

    def action_create_contract(self):
        self.ensure_one()

        if not self.can_manage_contracts:
            raise AccessError(
                _("You don't have enough access rights to run this action.")
            )

        # افتح الويزرد للشركات غير SIJIL
        if self.company_id.id != SIJIL_COMPANY_ID:
            return {
                "type": "ir.actions.act_window",
                "name": _("Select Contract Template"),
                "res_model": "zofirm.contract.template.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_sale_order_id": self.id,
                    "default_template_type": "audit",
                },
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Create Sijillacc Contract"),
            "res_model": "sijil.contract.create.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
                "default_contract_type": "sijil_contract",
            },
        }

    def action_create_sijil_contract(self):
        return self.action_create_contract()

    def action_create_zofirm_contract(self):
        return self.action_create_contract()

    def action_send_sijil_qut(self):
        self.ensure_one()
        if self.company_id.id != SIJIL_COMPANY_ID:
            raise AccessError(_("Not allowed."))
        return self.action_quotation_send()

    def action_print_quotation(self):
        self.ensure_one()
        return self.env.ref("sale.action_report_saleorder").report_action(self)

    def action_quotation_send(self):
        # Pre-fill the "Send by Email" composer with the company-level defaults
        # configured under Settings > Sijil Email. Blank values = no override.
        action = super().action_quotation_send()
        if not (action and isinstance(action, dict)):
            return action
        company = (self and self[:1].company_id) or self.env.company
        if not company:
            return action
        ctx = dict(action.get("context") or {})
        if company.sijil_sales_email_from and "default_email_from" not in ctx:
            ctx["default_email_from"] = company.sijil_sales_email_from
        if company.sijil_sales_email_cc and "default_email_cc" not in ctx:
            ctx["default_email_cc"] = company.sijil_sales_email_cc
        if company.sijil_sales_mail_server_id and "default_mail_server_id" not in ctx:
            ctx["default_mail_server_id"] = company.sijil_sales_mail_server_id.id
        action["context"] = ctx
        return action

    # -------------------------------------------------------------------------------------------------------------------
    contract_count = fields.Integer(
        string="Contracts",
        compute="_compute_contract_count",
        store=False,
    )

    @api.depends("name", "company_id")
    def _compute_contract_count(self):
        Contract = self.env["zofirm.contract"].sudo()
        for order in self:
            order.contract_count = Contract.search_count(
                [("quotation_id", "=", order.id)]
            )

    def action_view_quotation_contracts(self):
        self.ensure_one()

        if not self.can_manage_contracts:
            raise AccessError(
                _("You don't have enough access rights to run this action.")
            )

        Contract = self.env["zofirm.contract"].sudo()
        contracts = Contract.search([("quotation_id", "=", self.id)])

        if not contracts:
            return False

        if len(contracts) == 1:
            return self._open_contract(contracts[0])

        action = self.env.ref(
            "zofirm_contract.action_zofirm_contract", raise_if_not_found=False
        )
        if not action:
            action = (
                self.env["ir.actions.act_window"]
                .sudo()
                .search([("res_model", "=", "zofirm.contract")], limit=1)
            )
            if not action:
                return False
            result = action.read()[0]
        else:
            result = action.read()[0]

        result["domain"] = [("id", "in", contracts.ids)]
        result["context"] = dict(self.env.context, default_quotation_id=self.id)
        return result

    # =================================================================
    # SOW Tab
    # =================================================================
    # add: SOW selections saved on the quotation
    sow_item_ids = fields.One2many(
        comodel_name="sale.order.sow.item",
        inverse_name="order_id",
        string="SOW",
        copy=True,
    )

    def _prepare_sow_item_values(self):

        self.ensure_one()

        values_list = []
        display_order = 10

        order_lines = self.order_line.sorted(
            key=lambda line: (
                line.sequence,
                line.id or 0,
            )
        )

        for order_line in order_lines:
            if order_line.display_type or not order_line.product_id:
                continue

            sale_line_id = order_line._origin.id

            if not sale_line_id:
                continue

            product_tmpl = order_line.product_id.product_tmpl_id

            product_display_name = order_line.product_id.display_name

            values_list.append(
                {
                    "item_key": f"{sale_line_id}:product",
                    "sale_order_line_id": sale_line_id,
                    "product_tmpl_id": product_tmpl.id,
                    # "product_display_name": (order_line.product_id.display_name),
                    "product_display_name": product_display_name,
                    "sow_line_id": False,
                    "sow_subline_id": False,
                    "item_kind": "product",
                    "display_order": display_order,
                }
            )

            display_order += 10

            sow_lines = product_tmpl.sow_line_ids.sorted(key=lambda record: record.id)

            for sow_line in sow_lines:
                values_list.append(
                    {
                        "item_key": (f"{sale_line_id}:line:{sow_line.id}"),
                        "sale_order_line_id": sale_line_id,
                        "product_tmpl_id": product_tmpl.id,
                        "product_display_name": False,
                        # "product_display_name": product_display_name,
                        "sow_line_id": sow_line.id,
                        "sow_subline_id": False,
                        "item_kind": "line",
                        "display_order": display_order,
                    }
                )

                display_order += 10

                for sow_subline in sow_line.subline_ids.sorted(
                    key=lambda record: record.id
                ):
                    values_list.append(
                        {
                            "item_key": (
                                f"{sale_line_id}:"
                                f"line:{sow_line.id}:"
                                f"subline:{sow_subline.id}"
                            ),
                            "sale_order_line_id": sale_line_id,
                            "product_tmpl_id": product_tmpl.id,
                            "product_display_name": False,
                            # "product_display_name": product_display_name,
                            "sow_line_id": sow_line.id,
                            "sow_subline_id": sow_subline.id,
                            "item_kind": "subline",
                            "display_order": display_order,
                        }
                    )

                    display_order += 10

        return values_list

    def _sync_sow_items(self):
        """
        Synchronize quotation SOW with the current products.

        Existing checkbox values remain unchanged.
        New Lines and Sublines are selected automatically.
        New Sublines inherit the selected state of their parent Line when available.
        """
        Item = self.env["sale.order.sow.item"]

        force_select_all = self.env.context.get("force_select_all_sow_items")

        for order in self:
            if not order.id:
                continue

            # Company ID 2 does not use this SOW page
            if order.company_id.id == SIJIL_COMPANY_ID:
                order.sow_item_ids.unlink()
                continue

            prepared_values = order._prepare_sow_item_values()

            expected_keys = {values["item_key"] for values in prepared_values}

            existing_by_key = {item.item_key: item for item in order.sow_item_ids}

            line_selected_by_pair = {
                (
                    item.sale_order_line_id.id,
                    item.sow_line_id.id,
                ): item.selected
                for item in order.sow_item_ids
                if (
                    item.item_kind == "line"
                    and item.sale_order_line_id
                    and item.sow_line_id
                )
            }

            create_values = []

            for values in prepared_values:
                existing_item = existing_by_key.get(values["item_key"])

                if existing_item:
                    update_values = {}

                    for field_name in (
                        "sale_order_line_id",
                        "product_tmpl_id",
                        "product_display_name",
                        "sow_line_id",
                        "sow_subline_id",
                        "item_kind",
                        "display_order",
                    ):
                        new_value = values[field_name]
                        old_value = existing_item[field_name]

                        if field_name.endswith("_id"):
                            old_value = old_value.id

                        if old_value != new_value:
                            update_values[field_name] = new_value

                    if (
                        force_select_all
                        and existing_item.item_kind in ("line", "subline")
                        and not existing_item.selected
                    ):
                        update_values["selected"] = True

                    if update_values:
                        existing_item.with_context(
                            skip_sow_checkbox_cascade=True
                        ).write(update_values)

                    continue

                # Product row has no checkbox.
                # Line/Subline rows are selected automatically.
                selected = values["item_kind"] in ("line", "subline")

                if force_select_all and values["item_kind"] in ("line", "subline"):
                    selected = True

                elif values["item_kind"] == "subline":
                    selected = line_selected_by_pair.get(
                        (
                            values["sale_order_line_id"],
                            values["sow_line_id"],
                        ),
                        selected,
                    )

                create_values.append(
                    {
                        **values,
                        "order_id": order.id,
                        "selected": selected,
                    }
                )

            if create_values:
                Item.create(create_values)

            # Remove SOW items whose product/Line/Subline was removed
            stale_items = order.sow_item_ids.filtered(
                lambda item: item.item_key not in expected_keys
            )

            if stale_items:
                stale_items.unlink()

    @api.onchange("order_line", "company_id")
    def _onchange_order_line_sow_items(self):
        """Display SOW immediately when quotation products change."""
        for order in self:
            if order.company_id.id == SIJIL_COMPANY_ID:
                order.sow_item_ids = [Command.clear()]
                continue

            # Preserve current checkbox values
            selected_by_key = {
                item.item_key: item.selected for item in order.sow_item_ids
            }

            line_selected_by_pair = {
                (
                    item.sale_order_line_id.id,
                    item.sow_line_id.id,
                ): item.selected
                for item in order.sow_item_ids
                if (
                    item.item_kind == "line"
                    and item.sale_order_line_id
                    and item.sow_line_id
                )
            }

            commands = [Command.clear()]

            for values in order._prepare_sow_item_values():
                selected = selected_by_key.get(values["item_key"])

                if selected is None:
                    selected = values["item_kind"] in ("line", "subline")

                    if values["item_kind"] == "subline":
                        selected = line_selected_by_pair.get(
                            (
                                values["sale_order_line_id"],
                                values["sow_line_id"],
                            ),
                            selected,
                        )

                commands.append(
                    Command.create(
                        {
                            **values,
                            "selected": selected,
                        }
                    )
                )

            order.sow_item_ids = commands

    def action_refresh_sow_items(self):

        self.ensure_one()

        self.with_context(force_select_all_sow_items=True)._sync_sow_items()

        return {
            "type": "ir.actions.client",
            "tag": "soft_reload",
        }

    @api.model_create_multi
    def create(self, vals_list):
        # Prevent child sale.order.line create from syncing too early
        orders = super(
            SaleOrder,
            self.with_context(skip_sow_line_sync=True),
        ).create(vals_list)

        orders._sync_sow_items()

        return orders

    def write(self, vals):
        # If order lines are being changed, sync once after the whole write
        target = self

        if "order_line" in vals:
            target = self.with_context(skip_sow_line_sync=True)

        result = super(SaleOrder, target).write(vals)

        if not self.env.context.get("skip_sow_sync") and {
            "company_id",
            "order_line",
        } & set(vals):
            self._sync_sow_items()

        return result


class SijilContractCreateWizard(models.TransientModel):
    _name = "sijil.contract.create.wizard"
    _description = "Create Sijillacc Contract Wizard"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Quotation",
        required=True,
        readonly=True,
    )

    contract_type = fields.Selection(
        [
            ("sijil_contract", "Sijillacc contract"),
            ("sijil_maintenance_contract", "Sijillacc maintenance contract"),
        ],
        string="Contract Type",
        required=True,
        default="sijil_contract",
    )

    line_ids = fields.One2many(
        "sijil.contract.create.wizard.line",
        "wizard_id",
        string="Quotation Products / Services",
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)

        sale = False
        sale_id = vals.get("sale_order_id") or self.env.context.get(
            "default_sale_order_id"
        )
        if sale_id:
            sale = self.env["sale.order"].browse(sale_id).exists()

        if sale and "line_ids" in fields_list and not vals.get("line_ids"):
            vals["line_ids"] = self._prepare_wizard_lines(sale)

        return vals

    @api.model
    def _prepare_wizard_lines(self, sale):
        lines = sale.order_line.filtered(lambda l: not l.display_type and l.product_id)
        values = []

        for line in lines:
            uom = (
                line.product_uom_id
                if "product_uom_id" in line._fields
                else line.product_uom
            )
            currency = (
                line.currency_id if "currency_id" in line._fields else sale.currency_id
            )

            values.append(
                (
                    0,
                    0,
                    {
                        "sale_line_id": line.id,
                        "product_id": line.product_id.id,
                        "name": line.name,
                        "product_uom_qty": line.product_uom_qty,
                        "product_uom_id": uom.id,
                        "price_unit": line.price_unit,
                        "price_subtotal": line.price_subtotal,
                        "currency_id": currency.id,
                    },
                )
            )

        return values

    @api.onchange("contract_type")
    def _onchange_contract_type_fill_lines(self):
        for wizard in self:
            if (
                wizard.contract_type == "sijil_maintenance_contract"
                and wizard.sale_order_id
                and not wizard.line_ids
            ):
                wizard.line_ids = wizard._prepare_wizard_lines(wizard.sale_order_id)

    def _copy_project_schedule_to_contract(self, contract):
        self.ensure_one()

        # حماية من حالة أن العقد لم يتم إنشاؤه أو رجع None
        if not contract:
            return

        # حماية لو الحقل غير موجود لأي سبب
        if "contract_schedule_line_ids" not in contract._fields:
            return

        sale = self.sale_order_id

        # حماية لو جدول Project schedule غير موجود على عرض السعر
        if "project_schedule_line_ids" not in sale._fields:
            return

        if contract.contract_schedule_line_ids:
            return

        vals_list = [
            {
                "description": line.description,
                "duration_per_week": line.duration_per_week,
                "outputs": line.outputs,
            }
            for line in sale.project_schedule_line_ids
        ]

        if vals_list:
            contract.write(
                {"contract_schedule_line_ids": [(0, 0, vals) for vals in vals_list]}
            )
            contract.message_post(body=_("Copied Project schedule from Quotation."))

    def action_create_contract(self):
        self.ensure_one()

        sale = self.sale_order_id.exists()
        if not sale:
            raise UserError(_("Quotation not found."))

        if sale.company_id.id != SIJIL_COMPANY_ID:
            raise AccessError(_("This wizard is available only for Sijillacc company."))

        if not sale.can_manage_contracts:
            raise AccessError(
                _("You don't have enough access rights to run this action.")
            )

        report_xmlid = (
            REPORT_XMLID_SIJIL_MAINTENANCE
            if self.contract_type == "sijil_maintenance_contract"
            else REPORT_XMLID_SIJIL
        )

        report = self.env.ref(report_xmlid, raise_if_not_found=False)
        if not report:
            raise UserError(_("Report template not found: %s") % report_xmlid)

        selected_sale_lines = self.line_ids.filtered(lambda l: l.sale_line_id).mapped(
            "sale_line_id"
        )

        if (
            self.contract_type == "sijil_maintenance_contract"
            and not selected_sale_lines
        ):
            raise UserError(
                _(
                    "Please keep at least one product/service for the maintenance contract."
                )
            )

        Contract = self.env["zofirm.contract"]

        domain = [
            ("quotation_id", "=", sale.id),
            ("contract_type", "=", self.contract_type),
        ]

        contract = Contract.search(domain, limit=1)

        vals = {
            "quotation_id": sale.id,
            "start_date": fields.Date.context_today(self),
            "pdf_template_id": report.id,
            "contract_type": self.contract_type,
        }

        if self.contract_type == "sijil_maintenance_contract":
            vals["selected_order_line_ids"] = [(6, 0, selected_sale_lines.ids)]
        else:
            vals["selected_order_line_ids"] = [(5, 0, 0)]

        if contract:
            contract.write(vals)
        else:
            created_contract = Contract.create(vals)
            contract = (
                created_contract
                if created_contract
                else Contract.search(domain, order="id desc", limit=1)
            )

        if not contract:
            raise UserError(
                _(
                    "Contract was not created. Please check the create() method on zofirm.contract."
                )
            )

        self._copy_project_schedule_to_contract(contract)

        return sale._open_contract(contract)


class SijilContractCreateWizardLine(models.TransientModel):
    _name = "sijil.contract.create.wizard.line"
    _description = "Sijillacc Contract Wizard Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "sijil.contract.create.wizard",
        required=True,
        ondelete="cascade",
    )

    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Quotation Line",
        readonly=False,
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        readonly=True,
    )

    name = fields.Text(
        string="Description",
        readonly=True,
    )

    product_uom_qty = fields.Float(
        string="Quantity",
        readonly=True,
    )

    product_uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        readonly=True,
    )

    price_unit = fields.Float(
        string="Unit Price",
        readonly=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        readonly=True,
    )

    price_subtotal = fields.Monetary(
        string="Subtotal",
        currency_field="currency_id",
        readonly=True,
    )


class SaleOrderFeesLine(models.Model):
    _name = "sale.order.fees.line"
    _description = "Fees and Payment Plan Line"

    order_id = fields.Many2one(
        "sale.order",
        string="Quotation",
        required=True,
        ondelete="cascade",
    )

    name = fields.Char(string="Installment", help="مثال: الأولى، الثانية ...")

    percentage_total = fields.Float(
        string="Percentage of Total (%)", help="النسبة من القيمة الإجمالية للعرض"
    )

    currency_id = fields.Many2one(
        "res.currency",
        related="order_id.currency_id",
        store=True,
        readonly=True,
    )

    amount = fields.Monetary(
        string="Amount (SAR)",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
        help="المبلغ بالريال السعودي لكل دفعة",
    )

    due_stage = fields.Char(
        string="Due Milestone",
        help="مرحلة الاستحقاق (مثال: عند توقيع العقد وبدء العمل)",
    )

    def _sijil_installment_label(self, n: int) -> str:
        ordinals = {
            1: "الأولى",
            2: "الثانية",
            3: "الثالثة",
            4: "الرابعة",
            5: "الخامسة",
            6: "السادسة",
            7: "السابعة",
            8: "الثامنة",
            9: "التاسعة",
            10: "العاشرة",
            11: "الحادية عشرة",
            12: "الثانية عشرة",
        }
        return ordinals.get(n, f"رقم {n}")

    @api.model_create_multi
    def create(self, vals_list):
        # نجمع السطور حسب الـ order_id
        by_order = {}
        for vals in vals_list:
            oid = vals.get("order_id")
            by_order.setdefault(oid, []).append(vals)

        # ====== منع الإضافة إذا وصل الإجمالي 100% أو سيتجاوز 100% ======
        for oid, items in by_order.items():
            if not oid:
                continue
            order = self.env["sale.order"].browse(oid)

            current_total = sum(
                order.fees_payment_line_ids.mapped("percentage_total") or [0.0]
            )

            # لو الإجمالي وصل 100% بالفعل -> امنع إضافة أي سطر جديد
            if float_compare(current_total, 100.0, precision_digits=2) >= 0:
                raise ValidationError(
                    _("لا يمكن إضافة دفعة جديدة لأن إجمالي النِسَب وصل إلى 100%%.")
                )

            # لو الإضافة الحالية ستجعل الإجمالي يتجاوز 100% -> امنع
            new_total = current_total + sum(
                (v.get("percentage_total") or 0.0) for v in items
            )
            if float_compare(new_total, 100.0, precision_digits=2) > 0:
                raise ValidationError(
                    _(
                        "إجمالي نسب الدفعات لا يمكن أن يتجاوز 100%%. (الإجمالي بعد الإضافة: %.2f%%)"
                    )
                    % new_total
                )

        # ====== الترقيم التلقائي (كودك الحالي) ======
        for oid, items in by_order.items():
            if not oid:
                continue

            base = self.search_count([("order_id", "=", oid)])

            i = 0
            for vals in items:
                if not vals.get("name"):
                    n = base + i + 1
                    vals["name"] = f"الدفعة {self._sijil_installment_label(n)}"
                    i += 1

        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        for order in self.mapped("order_id"):
            total = sum(order.fees_payment_line_ids.mapped("percentage_total") or [0.0])
            if float_compare(total, 100.0, precision_digits=2) > 0:
                raise ValidationError(
                    _(
                        "إجمالي نسب الدفعات لا يمكن أن يتجاوز 100%%. (الإجمالي الحالي: %.2f%%)"
                    )
                    % total
                )
        return res

    # ==============================================================================================
    @api.depends("percentage_total", "order_id.amount_total")
    def _compute_amount(self):
        for line in self:
            total = line.order_id.amount_total or 0.0
            perc = line.percentage_total or 0.0
            line.amount = total * perc / 100.0

    @api.onchange("order_id")
    def _onchange_order_id_autofill_installment_name(self):
        for rec in self:
            # لما نضغط Add a line بيكون الاسم فاضي -> املأه
            if rec.order_id and not (rec.name or "").strip():
                # عدّ السطور اللي ليها اسم بالفعل (يشمل السطور الجديدة الغير محفوظة)
                existing_named = [
                    l
                    for l in rec.order_id.fees_payment_line_ids
                    if l != rec and (l.name or "").strip()
                ]
                n = len(existing_named) + 1
                rec.name = f"الدفعة {rec._sijil_installment_label(n)}"

    @api.constrains("percentage_total", "order_id")
    def _check_total_percentage_not_exceed_100(self):
        """Block saving if sum(percentage_total) per order exceeds 100%."""
        for order in self.mapped("order_id"):
            if not order:
                continue
            total = sum(order.fees_payment_line_ids.mapped("percentage_total") or [0.0])
            if float_compare(total, 100.0, precision_digits=2) > 0:
                raise ValidationError(
                    _(
                        "إجمالي نسب الدفعات لا يمكن أن يتجاوز 100%%. الإجمالي الحالي: %.2f%%"
                    )
                    % total
                )

    # ✅ نخزن آخر قيمة صحيحة (للرجوع لها)
    last_valid_percentage = fields.Float(default=0.0)

    @api.onchange("percentage_total", "order_id")
    def _onchange_percentage_total_block_over_100(self):
        for rec in self:
            if not rec.order_id:
                continue

            # اجمالي النسب لكل الدفعات (بما فيها الحالية)
            total = sum(
                (l.percentage_total or 0.0) for l in rec.order_id.fees_payment_line_ids
            )

            if float_compare(total, 100.0, precision_digits=2) > 0:
                # ❌ رجّع للقيمة السابقة بدل ما نعدّلها لقيمة جديدة
                rec.percentage_total = rec.last_valid_percentage

                return {
                    "warning": {
                        "title": _("غير مسموح"),
                        "message": _("لا يمكن أن يتجاوز مجموع نسب الدفعات 100%."),
                    }
                }
            else:
                # ✅ تحديث آخر قيمة صحيحة
                rec.last_valid_percentage = rec.percentage_total or 0.0


# Note: sale.payment.duration and sale.financial.year are defined in
# sale_reference_data.py (Odoo 19 models.Constraint).


# =====================================================================
#   Sale Order Line extender
# =====================================================================


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"
    
    zofirm_product_display_name = fields.Char(
        string="Selected Product Display Name",
        copy=True,
    )

    zofirm_product_display_lang = fields.Char(
        string="Selected Product Display Language",
        copy=True,
    )

    zofirm_product_display_template_id = fields.Many2one(
        "product.template",
        string="Selected Product Display Template",
        copy=True,
        ondelete="set null",
    )
    section_product_id = fields.Many2one(
    'product.product',
    string='Section Product'
    )
        
    product_uom_name = fields.Char(
        related="product_uom_id.name",
        string="UoM",
        readonly=True,
    )
    fees_period_start = fields.Date(string="Period Start")
    fees_period_end = fields.Date(string="Period End")

    payment_duration_id = fields.Many2one(
        comodel_name="sale.payment.duration",
        string="Payment Duration",
        ondelete="restrict",
    )

    financial_year_ids = fields.Many2many(
        comodel_name="sale.financial.year",
        relation="sale_order_line_financial_year_rel",
        column1="order_line_id",
        column2="financial_year_id",
        string="Year",
    )

    financial_quarter_ids = fields.Many2many(
        comodel_name="sale.financial.quarter",
        relation="sale_order_line_financial_quarter_rel",
        column1="order_line_id",
        column2="financial_quarter_id",
        string="Quarter",
    )

    # Compat for stale DB/custom views still referencing the old field name.
    financial_quarter = fields.Char(
        string="Quarter",
        compute="_compute_financial_quarter",
    )

    @api.depends(
        "financial_quarter_ids",
        "financial_quarter_ids.name",
        "financial_quarter_ids.sequence",
    )
    def _compute_financial_quarter(self):
        for line in self:
            line.financial_quarter = line._get_financial_quarter_display()
    
    def _get_financial_quarter_display(self):
        self.ensure_one()

        quarters = self.financial_quarter_ids.sorted(
            lambda quarter: quarter.sequence
        )

        lang = (self.env.context.get("lang") or self.env.lang or "").lower()

        if lang.startswith("en"):
            english_quarters = {
                "first": "First",
                "second": "Second",
                "third": "Third",
                "fourth": "Fourth",
            }

            return ", ".join(
                english_quarters.get(quarter.code, quarter.name or "")
                for quarter in quarters
            )

        return ", ".join(quarters.mapped("name"))

    def _get_financial_years_display(self):
        self.ensure_one()
        years = self.financial_year_ids.sorted(lambda year: year.name or "")
        return ", ".join(years.mapped("name"))

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

    # =============================================================================================
    # skip_sow_line_sync
    # ===========================================================================================

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)

        if not self.env.context.get("skip_sow_line_sync"):
            orders = lines.mapped("order_id").filtered(lambda order: order.id)
            orders._sync_sow_items()

        return lines

    def _update_product_names_to_partner_lang(self):
        for line in self:
            if line.product_id and line.order_id.partner_id.lang:
                line.name = line.product_id.with_context(
                    lang=line.order_id.partner_id.lang
                ).display_name
    

    def write(self, vals):
        orders_before = self.mapped("order_id")

        result = super().write(vals)

        if not self.env.context.get("skip_sow_line_sync") and {
            "product_id",
            "display_type",
            "order_id",
        } & set(vals):
            orders = (orders_before | self.mapped("order_id")).filtered(
                lambda order: order.id
            )

            orders._sync_sow_items()

        return result

    def unlink(self):
        orders = self.mapped("order_id")

        result = super().unlink()

        if not self.env.context.get("skip_sow_line_sync"):
            orders.exists()._sync_sow_items()

        return result
    
    

    


class SaleFinancialQuarter(models.Model):
    _name = "sale.financial.quarter"
    _description = "Financial Quarter"
    _order = "sequence, id"

    name = fields.Char(
        string="Quarter",
        required=True,
        translate=True,
    )

    code = fields.Selection(
        selection=[
            ("first", "First"),
            ("second", "Second"),
            ("third", "Third"),
            ("fourth", "Fourth"),
        ],
        string="Code",
        required=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    active = fields.Boolean(
        default=True,
    )

    _sale_financial_quarter_code_unique = models.Constraint(
        "unique(code)",
        "Quarter code must be unique.",
    )
