import io

from odoo import api, models
from odoo.tools import pdf
from odoo.tools.pdf import PdfFileWriter


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    DEFAULT_SALE_REPORT_NAMES = {"sale.report_saleorder","sale.report_saleorder_raw",}
    

    CUSTOM_FINANCIAL_REPORT_NAMES = {
    "zofirm_contract.sale_report_financial_offer_raw",
    "zofirm_contract.sale_report_financial_offer_without_total_raw",
    "zofirm_contract.sale_report_financial_offer_with_total_amount_raw",
    "zofirm_contract.sale_report_financial_offer_4400_raw",
}

    def _get_contract_name_from_context(self):
        return (
            self.env.context.get("zofirm_contract_name")
            or self.env.context.get("sijil_contract_name")
        )

    @api.depends("name")
    @api.depends_context("zofirm_contract_name", "sijil_contract_name")
    def _compute_display_name(self):
        super()._compute_display_name()
        suffix = self._get_contract_name_from_context()
        if not suffix:
            return

        for rec in self:
            if rec.display_name:
                rec.display_name = f"{rec.display_name} — {suffix}"

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100, **kwargs):
        domain = domain or []
        res = super().name_search(
            name=name,
            domain=domain,
            operator=operator,
            limit=limit,
        )

        suffix = self._get_contract_name_from_context()
        if suffix:
            res = [(rid, f"{label} — {suffix}") for rid, label in res]

        return res

    def _sijil_normalize_res_ids(self, res_ids):
        if not res_ids:
            return []

        if isinstance(res_ids, int):
            return [res_ids]

        if isinstance(res_ids, str):
            return [int(x) for x in res_ids.split(",") if x.strip().isdigit()]

        return list(res_ids)

    def _sijil_get_first_sale_order(self, res_ids):
        ids = self._sijil_normalize_res_ids(res_ids)

        if not ids and self.env.context.get("active_model") == "sale.order":
            ids = self._sijil_normalize_res_ids(
                self.env.context.get("active_ids") or self.env.context.get("active_id")
            )

        if not ids:
            return self.env["sale.order"]

        return self.env["sale.order"].browse(ids[:1]).exists()

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)

        if (
            report
            and report.report_name in self.DEFAULT_SALE_REPORT_NAMES
            and not self.env.context.get("zofirm_skip_financial_offer_redirect")
        ):
            order = self._sijil_get_first_sale_order(res_ids)

            # SijilACC id=2 يظل على تقرير Odoo/Sijil العادي
            if order and order.company_id and order.company_id.id != 2:
                financial_report = self.env.ref(
                    "zofirm_contract.action_report_saleorder_financial_offer",
                    raise_if_not_found=False,
                )

                if financial_report:
                    return financial_report.with_context(
                        zofirm_skip_financial_offer_redirect=True
                    )._render_qweb_pdf(
                        financial_report.report_name,
                        res_ids=self._sijil_normalize_res_ids(res_ids),
                        data=data,
                    )

        return super()._render_qweb_pdf(
            report_ref,
            res_ids=res_ids,
            data=data,
        )



    def _render_qweb_pdf_prepare_streams(
        self,
        report_ref,
        data,
        res_ids=None,
    ):
        """
        دمج ملفات Quote Builder مع تقارير العرض المالي المخصصة.

        الترتيب النهائي:
        1. Header PDFs
        2. Product PDFs
        3. التقرير المالي المخصص
        4. Footer PDFs
        """
        result = super()._render_qweb_pdf_prepare_streams(
            report_ref,
            data,
            res_ids=res_ids,
        )

        report = self._get_report(report_ref)

        # لا نتدخل في أي تقرير آخر
        if report.report_name not in self.CUSTOM_FINANCIAL_REPORT_NAMES:
            return result

        order_ids = self._sijil_normalize_res_ids(res_ids)

        orders = (
            self.env["sale.order"]
            .browse(order_ids)
            .exists()
        )

        for order in orders:
            order_result = result.get(order.id, {})
            initial_stream = order_result.get("stream")

            if not initial_stream:
                continue

            quotation_documents = order.quotation_document_ids

            headers = quotation_documents.filtered(
                lambda document: document.document_type == "header"
            )

            footers = quotation_documents - headers

            has_product_documents = any(
                line.product_document_ids
                for line in order.order_line
            )

            # لا توجد ملفات PDF ليتم دمجها
            if (
                not headers
                and not has_product_documents
                and not footers
            ):
                continue

            form_fields_values_mapping = {}
            writer = PdfFileWriter()

            report_with_order_context = self.with_context(
                use_babel=True,
                lang=order._get_lang() or self.env.user.lang,
            )

            # =====================================
            # 1. ملفات Header
            # =====================================
            for header in headers:
                prefix = (
                    f"quotation_document_id_{header.id}__"
                )

                report_with_order_context\
                    ._update_mapping_and_add_pages_to_writer(
                        writer,
                        header,
                        form_fields_values_mapping,
                        prefix,
                        order,
                    )

            # =====================================
            # 2. ملفات PDF المرتبطة بالمنتجات
            # =====================================
            if has_product_documents:
                for line in order.order_line:
                    for document in line.product_document_ids:
                        prefix = (
                            f"sol_id_{line.id}_"
                            f"product_document_id_{document.id}__"
                        )

                        report_with_order_context\
                            ._update_mapping_and_add_pages_to_writer(
                                writer,
                                document,
                                form_fields_values_mapping,
                                prefix,
                                order,
                                line,
                            )

            # =====================================
            # 3. تقرير الكوتيشن المخصص
            # =====================================
            self._add_pages_to_writer(
                writer,
                initial_stream.getvalue(),
            )

            # =====================================
            # 4. ملفات Footer
            # =====================================
            for footer in footers:
                prefix = (
                    f"quotation_document_id_{footer.id}__"
                )

                report_with_order_context\
                    ._update_mapping_and_add_pages_to_writer(
                        writer,
                        footer,
                        form_fields_values_mapping,
                        prefix,
                        order,
                    )

            # تعبئة حقول PDF القابلة للتخصيص
            pdf.fill_form_fields_pdf(
                writer,
                form_fields=form_fields_values_mapping,
            )

            # استبدال التقرير الأصلي بالتقرير النهائي المدمج
            with io.BytesIO() as output_buffer:
                writer.write(output_buffer)

                result[order.id]["stream"] = io.BytesIO(
                    output_buffer.getvalue()
                )

        return result
    
    
    
class IrActionsActions(models.Model):
    _inherit = "ir.actions.actions"

    @api.model
    def get_bindings(self, model_name):
        bindings = super().get_bindings(model_name)

        if model_name != "sale.order" or self.env.company.id != 2:
            return bindings

        hidden_report_xmlids = (
            "zofirm_contract.action_report_saleorder_financial_offer_without_total",
            "zofirm_contract.action_report_saleorder_financial_offer_with_total_amount",
        )

        hidden_report_ids = set()

        for xmlid in hidden_report_xmlids:
            report_action = self.env.ref(
                xmlid,
                raise_if_not_found=False,
            )
            if report_action:
                hidden_report_ids.add(report_action.id)

        report_bindings = bindings.get("report", [])

        filtered_report_bindings = [
            action
            for action in report_bindings
            if action.get("id") not in hidden_report_ids
        ]

        if filtered_report_bindings:
            bindings["report"] = filtered_report_bindings
        else:
            bindings.pop("report", None)

        return bindings
