# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models


_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def _preferred_lang(env, search_text):
    """
    Detect language from what the user typed.

    Arabic text -> Arabic translation.
    Other text  -> English translation.
    """
    prefix = "ar" if _ARABIC_RE.search(search_text or "") else "en"

    preferred_code = (
        "ar_001"
        if prefix == "ar"
        else "en_US"
    )

    active_langs = env["res.lang"].sudo().search([
        ("active", "=", True)
    ])

    # Prefer exact standard Odoo code.
    exact = active_langs.filtered(
        lambda lang: lang.code == preferred_code
    )[:1]

    if exact:
        return exact.code

    # Fallback to any active Arabic / English language.
    same_family = active_langs.filtered(
        lambda lang:
            (lang.code or "").lower().startswith(prefix)
    )[:1]

    if same_family:
        return same_family.code

    return env.lang or "en_US"


# ============================================================
# product.product
# ============================================================

class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def name_search(
        self,
        name="",
        domain=None,
        operator="ilike",
        limit=100,
    ):
        """
        Search products using the language detected
        from the user's typed text.
        """
        lang = _preferred_lang(self.env, name)

        products = self.with_context(lang=lang)

        return super(
            ProductProduct,
            products,
        ).name_search(
            name=name,
            domain=domain or [],
            operator=operator,
            limit=limit,
        )

    @api.model
    def web_name_search(
        self,
        name,
        specification,
        domain=None,
        operator="ilike",
        limit=100,
    ):
        """
        IMPORTANT for Odoo 19 autocomplete.

        Many2One autocomplete calls web_name_search(),
        not name_search() directly.

        We must therefore apply the selected language here
        as well, otherwise Odoo rebuilds display_name using
        the user's UI language.
        """
        lang = _preferred_lang(self.env, name)

        products = self.with_context(lang=lang)

        return super(
            ProductProduct,
            products,
        ).web_name_search(
            name,
            specification,
            domain=domain or [],
            operator=operator,
            limit=limit,
        )

    catalog_secondary_name = fields.Char(
        string="Secondary Product Name",
        compute="_compute_catalog_secondary_name",
    )

    @api.depends("product_tmpl_id.name")
    @api.depends_context("lang")
    def _compute_catalog_secondary_name(self):
        current_lang = self.env.context.get("lang") or self.env.lang or "en_US"

        for product in self:

            if current_lang.lower().startswith("ar"):
                secondary_lang = "en_US"

            else:
                secondary_lang = "ar_001"

            current_name = (
                product.with_context(lang=current_lang).name
                or ""
            )

            secondary_name = (
                product.with_context(lang=secondary_lang).name
                or ""
            )

            if (
                secondary_name
                and secondary_name.strip() != current_name.strip()
            ):
                product.catalog_secondary_name = secondary_name
            else:
                product.catalog_secondary_name = False

# ============================================================
# product.template
# ============================================================

class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def name_search(
        self,
        name="",
        domain=None,
        operator="ilike",
        limit=100,
    ):
        """
        Search Product Templates using the language
        detected from the entered text.
        """
        lang = _preferred_lang(self.env, name)

        templates = self.with_context(lang=lang)

        return super(
            ProductTemplate,
            templates,
        ).name_search(
            name=name,
            domain=domain or [],
            operator=operator,
            limit=limit,
        )

    @api.model
    def web_name_search(
        self,
        name,
        specification,
        domain=None,
        operator="ilike",
        limit=100,
    ):
        """
        Force autocomplete display_name to use the same
        language that was detected from the user's search.
        """
        lang = _preferred_lang(self.env, name)

        templates = self.with_context(lang=lang)

        return super(
            ProductTemplate,
            templates,
        ).web_name_search(
            name,
            specification,
            domain=domain or [],
            operator=operator,
            limit=limit,
        )
        
        
    alternate_language_name = fields.Char(
        string="Translation",
        compute="_compute_alternate_language_name",
    )

    @api.depends("name")
    @api.depends_context("lang")
    def _compute_alternate_language_name(self):
        current_lang = (
            self.env.context.get("lang")
            or self.env.user.lang
            or "en_US"
        )

        # إذا كانت واجهة المستخدم عربية → اعرض الإنجليزية
        # غير ذلك → اعرض العربية
        target_lang = "en_US" if current_lang.startswith("ar") else "ar_001"

        for product in self:
            current_name = product.name or ""

            translated_name = (
                product.with_context(lang=target_lang).name or ""
            )

            # إذا لم توجد ترجمة فعلية، لا نكرر نفس الاسم
            if (
                translated_name.strip()
                and translated_name.strip() != current_name.strip()
            ):
                product.alternate_language_name = translated_name
            else:
                product.alternate_language_name = False
        