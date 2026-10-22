# -*- coding: utf-8 -*-
"""Rewrite stale view arches that still reference ``financial_quarter``.

The Selection/Char field was replaced by ``financial_quarter_ids``. Customized
or not-yet-reloaded ``ir.ui.view`` rows can still mention the old name, which
blocks module upgrade while validating inherited sale.order forms.
"""

from __future__ import annotations

import json
import logging

_logger = logging.getLogger(__name__)

_REPLACEMENTS = (
    ('name="financial_quarter"', 'name="financial_quarter_ids"'),
    ("name='financial_quarter'", "name='financial_quarter_ids'"),
    ('[@name="financial_quarter"]', '[@name="financial_quarter_ids"]'),
    ("[@name='financial_quarter']", "[@name='financial_quarter_ids']"),
    ("product_item.financial_quarter", "product_item.financial_quarter_ids"),
    ("line.financial_quarter", "line.financial_quarter_ids"),
)


def _rewrite_arch(arch):
    if not arch or "financial_quarter" not in arch:
        return arch, False
    new_arch = arch
    for old, new in _REPLACEMENTS:
        new_arch = new_arch.replace(old, new)
    return new_arch, new_arch != arch


def _rewrite_arch_db(arch_db):
    if arch_db is None:
        return arch_db, False
    if isinstance(arch_db, dict):
        changed = False
        rewritten = {}
        for lang, arch in arch_db.items():
            new_arch, did_change = _rewrite_arch(arch if isinstance(arch, str) else str(arch))
            rewritten[lang] = new_arch
            changed = changed or did_change
        return rewritten, changed
    if isinstance(arch_db, str):
        try:
            parsed = json.loads(arch_db)
        except (TypeError, ValueError, json.JSONDecodeError):
            return _rewrite_arch(arch_db)
        if isinstance(parsed, dict):
            return _rewrite_arch_db(parsed)
        return _rewrite_arch(arch_db)
    return arch_db, False


def _arch_column_type(cr):
    cr.execute(
        """
        SELECT data_type
          FROM information_schema.columns
         WHERE table_name = 'ir_ui_view'
           AND column_name = 'arch_db'
        """
    )
    row = cr.fetchone()
    return row[0] if row else ""


def migrate(cr, version):
    arch_type = _arch_column_type(cr)
    cr.execute(
        """
        SELECT id, arch_db
          FROM ir_ui_view
         WHERE arch_db::text LIKE '%financial_quarter%'
        """
    )
    rows = cr.fetchall()
    fixed = 0
    for view_id, arch_db in rows:
        if isinstance(arch_db, str):
            try:
                arch_db = json.loads(arch_db)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        rewritten, changed = _rewrite_arch_db(arch_db)
        if not changed:
            continue
        if arch_type == "jsonb":
            payload = json.dumps(rewritten if isinstance(rewritten, dict) else {"en_US": rewritten})
            cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE id = %s",
                (payload, view_id),
            )
        else:
            payload = (
                json.dumps(rewritten)
                if isinstance(rewritten, dict)
                else rewritten
            )
            cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s WHERE id = %s",
                (payload, view_id),
            )
        fixed += 1
    _logger.info(
        "zofirm_contract: rewrote financial_quarter -> financial_quarter_ids in %s views",
        fixed,
    )
