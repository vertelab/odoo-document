# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import datetime
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    deletion_delay = fields.Integer(
        string="Trash Retention (days)",
        default=0,
        help="Days a deleted file stays in the trash before it is removed for "
             "good. 0 disables the trash: a delete is immediate, as before.",
    )


class DmsFile(models.Model):
    _inherit = "dms.file"

    deletion_date = fields.Datetime(
        string="Delete After",
        readonly=True,
        copy=False,
        help="Set when the file is deleted while its directory has a trash "
             "retention. The cron removes the file once this date has passed.",
    )

    def unlink(self):
        """Move the file to the trash when its directory has a retention.

        Falls back to a real unlink when no retention is configured, so a
        directory that never opted in behaves exactly as before.
        """
        if self.env.context.get("dms_trash_purge"):
            return super().unlink()
        immediate = self.browse()
        for record in self:
            delay = record.directory_id.deletion_delay or 0
            if delay <= 0:
                immediate |= record
                continue
            deadline = fields.Datetime.now() + datetime.timedelta(days=delay)
            record.write({"active": False, "deletion_date": deadline})
            _logger.info(
                "dms_trash: '%s' (id=%s) moved to trash until %s",
                record.name,
                record.id,
                deadline,
            )
        if immediate:
            return super(DmsFile, immediate).unlink()
        return True

    def action_restore_from_trash(self):
        """Bring a trashed file back."""
        self.ensure_one()
        self.write({"active": True, "deletion_date": False})
        return True

    @api.model
    def _cron_purge_trash(self):
        """Remove files whose trash retention has expired."""
        expired = (
            self.with_context(active_test=False)
            .sudo()
            .search(
                [
                    ("active", "=", False),
                    ("deletion_date", "!=", False),
                    ("deletion_date", "<=", fields.Datetime.now()),
                ]
            )
        )
        if not expired:
            _logger.info("dms_trash: nothing to purge")
            return 0
        _logger.info("dms_trash: purging %s file(s)", len(expired))
        count = len(expired)
        # Bypass this model's own unlink(): it would see a directory with a
        # retention and archive the record again instead of removing it, so
        # the cron would never actually delete anything.
        super(DmsFile, expired.with_context(dms_trash_purge=True)).unlink()
        return count
