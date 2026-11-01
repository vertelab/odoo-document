# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Move the applicant storage from attachment to file.

The applicant bridge uses the ``owner`` access mode: a candidate's CV and
interview notes belong to the recruiter handling the application, not to
the company. An attachment storage cannot express that -- dms_security_mixin
hardcodes inheritance from the parent record, so the owner group is ignored
and every internal user who can read the applicant can read the CV.

The XML now says ``save_type='file'``, but the data block is ``noupdate``
(rewriting the storage re-runs a dms_field constraint that fails against a
root directory whose res_model has not been cleared yet). An existing
database therefore keeps ``attachment`` and the mixin refuses to create the
directory at all:

    Model hr.applicant uses access mode 'owner', but storage Applicants has
    save_type='attachment'.

WHY THE ROOT DIRECTORY IS DELETED RATHER THAN UPDATED. dms_field has two
constraints that together make the flip impossible in place:

  _constrain_model_ids   @api.constrains("model_ids", "save_type"). It
                         skips attachment storages, and for a
                         non-attachment one it requires every directory's
                         res_model to be IN model_ids. With model_ids empty
                         ``res_model not in []`` is True even for
                         res_model = False, so an empty model_ids can never
                         be satisfied while a directory exists. Writing
                         save_type re-runs this, and the root directory is
                         still there.
  _check_resource        a non-attachment storage with model_ids needs a
                         root directory WITH res_model.

Deleting the root first means the constraint has no directory to compare
against, and the mixin recreates the root on first use. The root is empty
by definition at this point: the mismatch blocked every directory creation,
so there is nothing to lose.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    storage = env.ref(
        "dms_hr_job_recruitment.hr_applicant_dms_storage",
        raise_if_not_found=False,
    )
    if not storage or storage.save_type != "attachment":
        return

    root = env["dms.directory"].search([
        ("storage_id", "=", storage.id),
        ("is_root_directory", "=", True),
    ])
    # Refuse to destroy anything that holds documents. The mismatch blocked
    # creation, so an empty root is the expected state -- but a database
    # that was switched to owner mode after files were uploaded must be
    # migrated by hand, not by this script.
    if root:
        files = env["dms.file"].search_count([("directory_id", "in", root.ids)])
        children = env["dms.directory"].search_count(
            [("parent_id", "in", root.ids)]
        )
        if files or children:
            _logger.warning(
                "dms_hr_job_recruitment: applicant root directory #%s holds "
                "%s file(s) and %s subdirectory(ies); leaving the storage as "
                "%s. Migrate it by hand.",
                root.id, files, children, storage.save_type,
            )
            return
        root.unlink()
        _logger.info(
            "dms_hr_job_recruitment: removed the empty applicant root "
            "directory so the storage can leave attachment mode"
        )

    if storage.model_ids:
        storage.write({"model_ids": [(5, 0, 0)]})
        _logger.info(
            "dms_hr_job_recruitment: cleared model_ids on the applicant "
            "storage (owner mode resolves nothing from a model)"
        )

    storage.write({
        "save_type": "file",
        "inherit_access_from_parent_record": False,
    })
    _logger.info(
        "dms_hr_job_recruitment: applicant storage switched from "
        "attachment to file (owner access mode)"
    )
