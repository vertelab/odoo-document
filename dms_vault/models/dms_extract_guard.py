# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""dms.file — the extractor's second guard.

``dms.directory.extract_enabled`` is a setting, and settings get forgotten or
set back. The vault forces it to False in the same write that sets
``is_vault``, but a user can still flip it afterwards — and if that is the
only guard, the extractor decrypts the file on read and indexes plaintext.

This override is the code-level guard: it checks ``vault_id`` and says
``skipped`` regardless of the flag. Two independent guards, because the
failure mode of the setting is silent.
"""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DmsFile(models.Model):
    _inherit = "dms.file"

    def _extract_needs_work(self):
        """A vault file is never a candidate, whatever the directory says.

        Returning False here keeps the file out of the queue entirely, so it
        does not occupy a batch slot on every tick. ``_extract_one`` still
        guards, because the queue is not the only caller.
        """
        self.ensure_one()
        if self.vault_id:
            return False
        return super()._extract_needs_work()

    def _extract_one(self):
        """A vault file is never extracted, whatever the directory says."""
        self.ensure_one()
        if self.vault_id:
            self.write({
                "extract_state": "skipped",
                "extract_date": fields.Datetime.now(),
                "extract_error": False,
            })
            return
        return super()._extract_one()
