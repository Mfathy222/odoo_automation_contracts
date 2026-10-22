from odoo import fields, api, models  # noqa: I001

SIJIL_COMPANY_ID = 2


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sow_line_ids = fields.One2many(
        comodel_name="product.sow.line",
        inverse_name="product_tmpl_id",
        string="SOW Lines",
        copy=True,
    )


class ProductSowLine(models.Model):
    _name = "product.sow.line"
    _description = "Product SOW Line"
    _order = "id"
    _rec_name = "name"

    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Product",
        required=True,
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(
        string="Line",
        required=True,
        translate=True,
    )

    subline_ids = fields.One2many(
        comodel_name="product.sow.subline",
        inverse_name="sow_line_id",
        string="Sublines",
        copy=True,
    )


class ProductSowSubline(models.Model):
    _name = "product.sow.subline"
    _description = "Product SOW Subline"
    _order = "id"
    _rec_name = "name"

    sow_line_id = fields.Many2one(
        comodel_name="product.sow.line",
        string="SOW Line",
        required=True,
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(
        string="Subline",
        required=True,
        translate=True,
    )


class SaleOrderSowItem(models.Model):
    _name = "sale.order.sow.item"
    _description = "Sale Order SOW Item"
    _order = "display_order, id"

    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Quotation",
        required=True,
        ondelete="cascade",
        index=True,
    )

    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Quotation Line",
        ondelete="cascade",
        index=True,
        readonly=True,
    )

    financial_quarter_ids = fields.Many2many(
        related="sale_order_line_id.financial_quarter_ids",
        string="Quarter",
        readonly=True,
    )

    # Compat for stale DB/custom views still referencing the old field name.
    financial_quarter = fields.Char(
        string="Quarter",
        compute="_compute_financial_quarter",
        readonly=True,
    )

    @api.depends(
        "financial_quarter_ids",
        "financial_quarter_ids.name",
        "financial_quarter_ids.sequence",
    )
    def _compute_financial_quarter(self):
        for item in self:
            quarters = item.financial_quarter_ids.sorted(
                lambda quarter: quarter.sequence
            )
            item.financial_quarter = ", ".join(quarters.mapped("name"))

    payment_duration_id = fields.Many2one(
        related="sale_order_line_id.payment_duration_id",
        string="Payment Duration",
        readonly=True,
    )

    fees_period_start = fields.Date(
        related="sale_order_line_id.fees_period_start",
        string="Period Start",
        readonly=True,
    )

    fees_period_end = fields.Date(
        related="sale_order_line_id.fees_period_end",
        string="Period End",
        readonly=True,
    )

    financial_year_ids = fields.Many2many(
        related="sale_order_line_id.financial_year_ids",
        string="Years",
        readonly=True,
    )

    # Internal unique key used during synchronization
    item_key = fields.Char(
        string="Technical Key",
        required=True,
        index=True,
        copy=False,
    )

    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Product Template",
        required=True,
        readonly=True,
        ondelete="cascade",
        index=True,
    )

    product_display_name = fields.Char(
        string="Product",
        readonly=True,
    )

    sow_line_id = fields.Many2one(
        comodel_name="product.sow.line",
        string="SOW Line",
        readonly=True,
        ondelete="cascade",
        index=True,
    )

    sow_subline_id = fields.Many2one(
        comodel_name="product.sow.subline",
        string="SOW Subline",
        readonly=True,
        ondelete="cascade",
        index=True,
    )

    item_kind = fields.Selection(
        selection=[
            ("product", "Product"),
            ("line", "Line"),
            ("subline", "Subline"),
        ],
        string="Type",
        required=True,
        readonly=True,
    )

    display_order = fields.Integer(
        string="Display Order",
        default=10,
        readonly=True,
    )

    display_label = fields.Char(
        string="Line / Subline",
        compute="_compute_display_label",
        store=True,
    )

    selected = fields.Boolean(
        string="Selected",
        default=False,
        copy=True,
    )

    _sale_order_sow_item_key_unique = models.Constraint(
        "unique(order_id, item_key)",
        "The same SOW item cannot be added twice to one quotation.",
    )

    @api.depends(
        "item_kind",
        "sow_line_id.name",
        "sow_subline_id.name",
    )
    def _compute_display_label(self):
        for item in self:
            if item.item_kind == "product":
                item.display_label = ""

            elif item.item_kind == "subline":
                item.display_label = f"↳ {item.sow_subline_id.name or ''}"

            else:
                item.display_label = item.sow_line_id.name or ""

    @api.onchange("selected")
    def _onchange_selected(self):
        """
        Checking/unchecking a main Line changes all its Sublines.

        A Subline can still be unchecked individually afterwards.
        """
        for item in self:
            if item.item_kind != "line" or not item.order_id:
                continue

            children = item.order_id.sow_item_ids.filtered(
                lambda child: (
                    child.item_kind == "subline"
                    and child.sale_order_line_id == item.sale_order_line_id
                    and child.sow_line_id == item.sow_line_id
                )
            )

            for child in children:
                child.selected = item.selected

    @api.model_create_multi
    def create(self, vals_list):

        for vals in vals_list:
            if not vals.get("sow_line_id") and vals.get("sow_subline_id"):
                subline = (
                    self.env["product.sow.subline"]
                    .browse(vals["sow_subline_id"])
                    .exists()
                )

                if subline:
                    vals["sow_line_id"] = subline.sow_line_id.id

            if not vals.get("product_tmpl_id") and vals.get("sale_order_line_id"):
                sale_line = (
                    self.env["sale.order.line"]
                    .browse(vals["sale_order_line_id"])
                    .exists()
                )

                if sale_line and sale_line.product_id:
                    vals["product_tmpl_id"] = sale_line.product_id.product_tmpl_id.id

            if not vals.get("product_tmpl_id") and vals.get("sow_line_id"):
                sow_line = (
                    self.env["product.sow.line"].browse(vals["sow_line_id"]).exists()
                )

                if sow_line:
                    vals["product_tmpl_id"] = sow_line.product_tmpl_id.id

            if not vals.get("item_key") and vals.get("sale_order_line_id"):
                sale_line_id = vals["sale_order_line_id"]
                item_kind = vals.get("item_kind")

                if item_kind == "product":
                    vals["item_key"] = f"{sale_line_id}:product"

                elif item_kind == "subline":
                    vals["item_key"] = (
                        f"{sale_line_id}:"
                        f"line:{vals.get('sow_line_id')}:"
                        f"subline:{vals.get('sow_subline_id')}"
                    )

                else:
                    vals["item_key"] = f"{sale_line_id}:line:{vals.get('sow_line_id')}"

        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)

        # Server-side protection for imports/API/direct writes
        if "selected" in vals and not self.env.context.get("skip_sow_checkbox_cascade"):
            line_items = self.filtered(lambda item: item.item_kind == "line")

            for item in line_items:
                children = self.search(
                    [
                        (
                            "order_id",
                            "=",
                            item.order_id.id,
                        ),
                        (
                            "sale_order_line_id",
                            "=",
                            item.sale_order_line_id.id,
                        ),
                        (
                            "sow_line_id",
                            "=",
                            item.sow_line_id.id,
                        ),
                        (
                            "item_kind",
                            "=",
                            "subline",
                        ),
                    ]
                )

                children.with_context(skip_sow_checkbox_cascade=True).write(
                    {
                        "selected": vals["selected"],
                    }
                )

        return result


