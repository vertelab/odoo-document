# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Receive files photographed on a phone.

``web_pwa_push`` serves the camera page and the upload endpoint but has no
idea what a document is. It calls ``dms.file.pwa_capture_store(files, **kw)``
and expects a JSON-safe dict back. Everything DMS-specific lives here.
"""

import base64
import logging

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class DmsFile(models.Model):
    _inherit = "dms.file"

    capture_source = fields.Selection(
        selection=[
            ("manual", "Manual"),
            ("pwa", "Mobile capture"),
        ],
        default="manual",
        readonly=True,
        help="How the file entered the DMS. Set to 'pwa' when it came from "
             "the phone camera page.",
    )

    def pwa_capture_store(self, files, directory_id=None, **kwargs):
        """Store uploaded files in a DMS directory.

        Called by ``web_pwa_push`` from ``/pwa/upload``. Runs as the
        uploading user -- the controller deliberately does not sudo -- so
        the directory's own access rules decide whether this is allowed.

        :param files: list of ``werkzeug.FileStorage`` from the request
        :param directory_id: target ``dms.directory`` id
        :return: ``{'ids': [...], 'names': [...]}``
        """
        if not directory_id:
            raise UserError(_("No target directory given."))
        directory = self.env["dms.directory"].browse(int(directory_id))
        if not directory.exists():
            raise UserError(_("Directory %s does not exist.", directory_id))
        # The controller does not sudo, so this raises for a user without
        # create rights instead of writing into a directory they cannot see.
        directory.check_access("create")

        created = self.browse()
        for upload in files:
            payload = upload.read()
            if not payload:
                _logger.warning(
                    "dms_mobile: skipping empty upload %s", upload.filename
                )
                continue
            created |= self.create({
                "name": upload.filename or _("Capture"),
                "directory_id": directory.id,
                "content": base64.b64encode(payload),
                "capture_source": "pwa",
            })
        _logger.info(
            "dms_mobile: stored %s file(s) in %s", len(created), directory.name
        )
        return {
            "ok": True,
            "ids": created.ids,
            "names": created.mapped("name"),
        }
