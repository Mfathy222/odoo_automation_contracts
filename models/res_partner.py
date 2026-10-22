from odoo import api, fields, models  # type: ignore

SIJIL_COMPANY_ID = 2


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    authorized_person_domain_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Available Authorized Persons",
        compute="_compute_authorized_person_domain_ids",
    )
    authorized_person = fields.Many2one(
        'res.partner',
        string="Authorized person",
        help="اختر شخصًا من جهات الاتصال التابعة لهذه الشركة."
    )

    zofirm_contract_count = fields.Integer(
        string="Zofirm Contracts",
        compute="_compute_zofirm_contract_count",
    )

    sijil_contract_count = fields.Integer(
        string="Sijil Contracts",
        compute="_compute_sijil_contract_count",
    )

    # -----------------------------
    #  Zofirm Contracts
    # -----------------------------
    @api.depends("child_ids")
    def _compute_zofirm_contract_count(self):
        Contract = self.env["zofirm.contract"]
        for partner in self:
            real_id = partner._origin.id or partner.id
            if not real_id:
                partner.zofirm_contract_count = 0
                continue

            partner.zofirm_contract_count = Contract.search_count([
                ("partner_id", "child_of", real_id),
                ("company_id", "!=", SIJIL_COMPANY_ID),
            ])

    def action_view_zofirm_contracts(self):
        self.ensure_one()
        real_id = self._origin.id or self.id
        if not real_id:
            return False

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
        result["domain"] = [
            ("partner_id", "child_of", real_id),
            ("company_id", "!=", SIJIL_COMPANY_ID),
        ]
        return result

    # -----------------------------
    #  Sijil Contracts
    # -----------------------------
    @api.depends("child_ids")
    def _compute_sijil_contract_count(self):
        Contract = self.env["zofirm.contract"]
        for partner in self:
            real_id = partner._origin.id or partner.id
            if not real_id:
                partner.sijil_contract_count = 0
                continue

            partner.sijil_contract_count = Contract.search_count([
                ("partner_id", "child_of", real_id),
                ("company_id", "=", SIJIL_COMPANY_ID),
            ])

    def action_view_sijil_contracts(self):
        self.ensure_one()
        real_id = self._origin.id or self.id
        if not real_id:
            return False

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
        result["domain"] = [
            ("partner_id", "child_of", real_id),
            ("company_id", "=", SIJIL_COMPANY_ID),
        ]
        return result

    # -----------------------------
    #  Display name helpers (Odoo 19 replacement for name_get)
    # -----------------------------
    @api.depends("name", "commercial_company_name")
    @api.depends_context("sijil_contract_name")
    def _compute_display_name(self):
        super()._compute_display_name()
        suffix = self.env.context.get("sijil_contract_name")
        if not suffix:
            return
        for partner in self:
            if partner.display_name:
                partner.display_name = f"{partner.display_name} — {suffix}"

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100, **kwargs):
        # NOTE: Odoo 19 BaseModel.name_search has no `order` param. Use **kwargs
        # to absorb anything the framework might add in future versions without
        # propagating it to super, which would TypeError.
        domain = domain or []
        res = super().name_search(name=name, domain=domain, operator=operator, limit=limit)
        suffix = self.env.context.get("sijil_contract_name")
        if suffix:
            res = [(rid, f"{label} — {suffix}") for rid, label in res]
        return res

    # -----------------------------
    #  Authorized person view tweak (Odoo 19 _get_view replaces fields_view_get)
    # -----------------------------
    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == 'form':
            company_name = (self.env.company.name or '').lower()
            placeholder = "sijil authorized person" if 'sijil' in company_name else "zofirm authorized person"
            for node in arch.xpath("//field[@name='authorized_person']"):
                node.set('placeholder', placeholder)
        return arch, view

    @api.depends(
        "child_ids",
        "child_ids.is_company",
        "child_ids.name",
        "commercial_partner_id",
    )
    def _compute_authorized_person_domain_ids(self):
        for partner in self:
            commercial_partner = partner.commercial_partner_id or partner

            children = commercial_partner.child_ids.filtered(
                lambda child: (
                    not child.is_company
                    and child.id != 'partner.id'
                )
            )

            partner.authorized_person_domain_ids = children