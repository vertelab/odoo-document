# -*- coding: utf-8 -*-
"""Repair `dms.directory` rows whose `parent_path` is NULL.

THE SYMPTOM
===========
The Documents list view dies with:

    TypeError: unsupported operand type(s) for +: 'bool' and 'str'
      dms/models/directory.py, _compute_count_total_directories
        self.search_count([("id", "child_of", record.id)])
      odoo/osv/expression.py, child_of_domain
        [('parent_path', '=like', path + '%')]

`child_of` expands to `parent_path =like <path>%`. When `parent_path` is
`False` (NULL in the database), `False + '%'` raises. One bad row takes out
the WHOLE list view — every directory becomes unreachable, not just the
broken one.

WHY IT HAPPENS
==============
`dms.directory` declares `_parent_store = True`, so Odoo maintains
`parent_path` on create and on `parent_id` changes. A row can still end up
NULL when it was:

  * created before `_parent_store` was added to the model,
  * created through a path that bypassed the ORM (raw SQL, an import script),
  * or written by an older version whose `_parent_store` handling differed.

Verified on `luke18` 2026-11-05: directory id=3 ("Docs", created 2026-10-19)
had `parent_path IS NULL`, which made the Documents view unusable. New
directories created through the ORM get the field correctly, so this is
old/foreign data, not an ongoing bug.

WHY A MIGRATION AND NOT A post_init_hook
========================================
A `post_init_hook` only runs when the module is first INSTALLED. An existing
installation — the one that has the broken data — would never run it. A
migration script runs on every upgrade that crosses the version, which is
exactly the set of databases that need the repair.

WHY `_parent_store_compute()`
=============================
It is Odoo's own method for rebuilding the stored hierarchy. It recomputes
every row from `parent_id` and is idempotent: rows that are already correct
are rewritten with the same value. We do not hand-write the path format
(`<id>/<id>/...`), because that format is Odoo's, not ours.

WHAT THIS DOES NOT DO
=====================
It does not touch `parent_id`. A row whose `parent_id` is itself wrong stays
wrong — this repairs the derived column only.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Rebuild `parent_path` for every `dms.directory` row.

    Runs as superuser: the repair is a data fix, not a user action, and a
    restricted role may not be able to read every directory.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    if "dms.directory" not in env:
        # `dms` is a hard dependency, so this cannot happen — but a migration
        # that crashes on a missing model would block the whole upgrade.
        _logger.warning(
            "dms_excalidraw: dms.directory is not in the registry; "
            "skipping the parent_path repair"
        )
        return

    Directory = env["dms.directory"]

    # Count first, so the log says whether anything was actually wrong.
    cr.execute(
        "SELECT count(*) FROM dms_directory WHERE parent_path IS NULL"
    )
    broken = cr.fetchone()[0]

    if not broken:
        _logger.info(
            "dms_excalidraw: no dms.directory rows with a NULL parent_path"
        )
        return

    _logger.warning(
        "dms_excalidraw: %s dms.directory row(s) have a NULL parent_path, "
        "which breaks the Documents list view (child_of on a boolean). "
        "Rebuilding the hierarchy.",
        broken,
    )

    # `_parent_store_compute()` walks every row and rewrites `parent_path`
    # from `parent_id`. Idempotent, and it is Odoo's own implementation of
    # the path format.
    Directory.with_context(active_test=False)._parent_store_compute()

    cr.execute(
        "SELECT count(*) FROM dms_directory WHERE parent_path IS NULL"
    )
    remaining = cr.fetchone()[0]

    if remaining:
        # Do not raise: a single unfixable row (e.g. one whose `parent_id`
        # points at a deleted record) must not block the module upgrade.
        # The log names the count so it can be investigated.
        _logger.error(
            "dms_excalidraw: %s dms.directory row(s) still have a NULL "
            "parent_path after the rebuild. Their `parent_id` may point at "
            "a missing record; the Documents list view will keep failing "
            "until they are fixed by hand.",
            remaining,
        )
    else:
        _logger.info(
            "dms_excalidraw: parent_path rebuilt for %s row(s); no NULLs "
            "remain",
            broken,
        )
