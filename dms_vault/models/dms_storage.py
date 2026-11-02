# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""dms.storage — resolve the fs.storage code a DMS storage writes through.

``dms.storage.save_type`` decides *where* a file goes; ``fs.storage`` decides
*how* the object key is built. The vault's filename-obfuscation check needs
the second, and the link between them is not a field — it is the same lookup
``fs_attachment`` does when it picks the storage for an attachment.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class DmsStorage(models.Model):
    _inherit = "dms.storage"

    @api.model
    def _dms_attachment_storage_code(self):
        """The ``fs.storage`` code attachments are written through, or None.

        ``None`` means the bytes never reach a storage backend keyed by
        filename (``save_type='database'``), so there is no object key to
        leak and nothing for the vault to refuse.
        """
        self.ensure_one()
        if self.save_type != "attachment":
            return None
        return (
            self.env["fs.storage"]
            .sudo()
            .get_default_storage_code_for_attachments()
        )
