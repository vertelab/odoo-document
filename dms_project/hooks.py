# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2022- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
##############################################################################

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Give existing projects the directory they never had.

    ``dms_project`` shipped without a storage, so ``create_parent_dir()``
    could never succeed and no project has a directory. This creates the
    missing ones and is safe to re-run.

    Adoption before creation: a directory already linked to the project by
    ``res_model``/``res_id`` is reused. A directory that was created by the
    old code and carries only the name is adopted by setting ``res_id``,
    rather than leaving an orphan and creating a second one.
    """
    Directory = env["dms.directory"].sudo()
    projects = env["project.project"].with_context(active_test=False).search([])
    created = adopted = 0
    for project in projects:
        existing = Directory.search(
            [
                ("res_model", "=", "project.project"),
                ("res_id", "=", project.id),
                ("is_root_directory", "=", False),
            ],
            limit=1,
        )
        if existing:
            continue
        # A directory left behind by the old name-based code has the project's
        # name but no res_id. Adopt it instead of creating a second one.
        orphan = Directory.search(
            [
                ("name", "=", project.display_name),
                ("res_id", "=", False),
                ("is_root_directory", "=", False),
                ("model_id.model", "=", "project.project"),
            ],
            limit=1,
        )
        if orphan:
            orphan.write({"res_id": project.id})
            adopted += 1
            continue
        try:
            project._dms_ensure_directory()
            created += 1
        except Exception:
            _logger.warning(
                "Could not create DMS directory for project %s", project.id,
                exc_info=True,
            )
    # ``dms_directory_id`` is a stored compute keyed on ``display_name``, so it
    # does not notice a directory created behind its back. Recompute it for
    # every project the hook touched.
    projects.invalidate_recordset(["dms_directory_id", "doc_count"])
    projects._compute_dms_directory_id()
    _logger.info(
        "dms_project: %s directories created, %s adopted, %s projects total",
        created,
        adopted,
        len(projects),
    )
