# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2026- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

"""Collabora Online as the editor for DMS office documents.

Mirrors what `dms_euro_office` does — a computed capability field and an
action returning `act_url` — so whatever reads `dms_excalidraw`'s capability
table finds a working entry without knowing which backend is installed.

The two hard parts are documented where they bite: the id is an
`ir.attachment`, not a `dms.file`, and the mode is `read`/`write`, never
`edit`.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Extensions `collabora_odoo` offers an editor for
# (`static/src/models/attachment_card_cool.js`: cool_extensions).
COLLABORA_EXTENSIONS = {
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "odt", "ods", "odp", "odg",
}


class DmsFile(models.Model):
    _inherit = "dms.file"

    can_open_in_collabora = fields.Boolean(
        string="Can open in Collabora",
        compute="_compute_can_open_in_collabora",
    )

    @api.depends("extension")
    def _compute_can_open_in_collabora(self):
        for record in self:
            extension = (record.extension or "").lower().lstrip(".")
            record.can_open_in_collabora = extension in COLLABORA_EXTENSIONS

    def _collabora_attachment(self):
        """Return the `ir.attachment` that holds this file's bytes.

        DMS stores bytes in `content_file`, a `Binary(attachment=True)` field
        on `dms.file` (see `dms/models/dms_file.py`). Odoo keeps such a field
        in an `ir.attachment` row keyed by `res_model`/`res_id`/`res_field`,
        so that row is what Collabora must be pointed at.

        Raises rather than returning an empty recordset: a URL built from a
        missing id gives a 404 in the editor with nothing naming the cause.
        """
        self.ensure_one()
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "dms.file"),
                ("res_id", "=", self.id),
                ("res_field", "=", "content_file"),
            ],
            limit=1,
        )
        if not attachment:
            raise UserError(
                _(
                    "“%(name)s” has no stored attachment, so Collabora has "
                    "nothing to open.",
                    name=self.name,
                )
            )
        return attachment

    def open_in_collabora_action(self):
        """Return an `ir.actions.act_url` that opens this document.

        The mode is `write` when the user may write to the directory and
        `read` otherwise. `collabora_odoo`'s own JS knows only those two and
        silently falls back to `read` for anything else — so an "edit" that
        came out read-only would look like a broken editor rather than a
        wrong URL.

        Authorisation is the DIRECTORY's (`permission_write`), the same gate
        the rest of DMS uses; `ir.attachment` is `check_access('write')` in
        `collabora_odoo`, which for a `dms.file` attachment is the model
        right, not the directory right.
        """
        self.ensure_one()
        if not self.can_open_in_collabora:
            raise UserError(
                _(
                    "“%(name)s” cannot be opened in Collabora: its extension "
                    "is “%(extension)s”.",
                    name=self.name,
                    extension=self.extension or _("none"),
                )
            )

        attachment = self._collabora_attachment()
        mode = "write" if self.directory_id.permission_write else "read"

        _logger.info(
            "dms_collabora: opening dms.file %s via attachment %s (%s)",
            self.id,
            attachment.id,
            mode,
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/collabora_odoo/frame/%s/%s" % (attachment.id, mode),
            "target": "new",
        }
