# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class DmsFileVersion(models.Model):
    _inherit = "dms.file.version"

    @api.model
    def _cron_prune_versions(self):
        """Delete versions outside each directory's retention policy.

        The most recent version of a file is never deleted, whatever the
        policy says — otherwise a file could become unrestorable.
        """
        self.env.cr.execute(
            """
            SELECT v.id
              FROM dms_file_version v
              JOIN dms_file f ON f.id = v.file_id
              JOIN dms_directory d ON d.id = f.directory_id
             WHERE v.id <> (
                     SELECT v2.id FROM dms_file_version v2
                      WHERE v2.file_id = v.file_id
                   ORDER BY v2.version_number DESC
                      LIMIT 1)
               AND (
                     (d.version_retention_count > 0 AND (
                        SELECT COUNT(*) FROM dms_file_version v3
                         WHERE v3.file_id = v.file_id
                           AND v3.version_number > v.version_number
                     ) >= d.version_retention_count)
                  OR (d.version_retention_days > 0
                      AND v.create_date < (now() - (d.version_retention_days || ' days')::interval))
               )
            """
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        if not ids:
            _logger.info("dms_version: nothing to prune")
            return 0
        records = self.browse(ids)
        _logger.info("dms_version: pruning %s version(s)", len(records))
        records.unlink()
        return len(ids)
