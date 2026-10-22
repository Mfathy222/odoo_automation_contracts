# -*- coding: utf-8 -*-
"""Map the legacy ``payment_duration`` Selection to ``payment_duration_id``.

The Selection field was replaced by a Many2one (``sale.payment.duration``).
Odoo does not drop the old column, so legacy values survive in the table but
are no longer exposed by the ORM. This backfills the new FK from those values,
creating any duration records that are missing from the seed data.
"""

from odoo import SUPERUSER_ID, api

LEGACY_COLUMNS = ("payment_duration", "Payment_duration")


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    duration_model = env["sale.payment.duration"]

    for column in LEGACY_COLUMNS:
        if not _column_exists(cr, "sale_order_line", column):
            continue

        cr.execute(
            f"""
            SELECT DISTINCT "{column}"
            FROM sale_order_line
            WHERE "{column}" IS NOT NULL
              AND "{column}" != ''
              AND payment_duration_id IS NULL
            """
        )
        legacy_values = [row[0] for row in cr.fetchall()]

        for value in legacy_values:
            duration = duration_model.search([("name", "=", value)], limit=1)
            if not duration:
                duration = duration_model.create({"name": value})
            cr.execute(
                f"""
                UPDATE sale_order_line
                SET payment_duration_id = %s
                WHERE "{column}" = %s
                  AND payment_duration_id IS NULL
                """,
                (duration.id, value),
            )
