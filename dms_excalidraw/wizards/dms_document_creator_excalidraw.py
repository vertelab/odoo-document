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

"""Excalidraw as a document type in the shared "New document" wizard.

This is the registration side of the registry in `dms_document_wizard.py`.
The wizard knows nothing about Excalidraw; it asks every module what it can
create. Adding a format means adding a class like this one — not editing the
wizard.
"""

import base64
import json

from odoo import _, models

# A scene Excalidraw accepts. `{}` or an empty file makes the client report
# "invalid scene" with no indication of the cause, so the shape is fixed.
EMPTY_SCENE = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": [],
    "appState": {
        "gridSize": None,
        "viewBackgroundColor": "#ffffff",
    },
    "files": {},
}


class DmsDocumentCreatorExcalidraw(models.AbstractModel):
    _inherit = "dms.document.creator"

    def _get_creators(self):
        """Add whiteboard to whatever other modules registered.

        `super()` is essential: every creator module subclasses the same
        abstract model, and Odoo calls only the LAST `_get_creators()`. Without
        the chain, installing `dms_document_office` would silently replace the
        whiteboard entry with Word/Excel/PowerPoint.
        """
        creators = super()._get_creators()
        creators.append(
            {
                "key": "excalidraw",
                "label": _("Whiteboard"),
                "extension": "excalidraw",
                # After the office formats: a whiteboard is the less common
                # choice when someone says "new document".
                "sequence": 40,
                "create": self._create_whiteboard,
                "open": self._open_whiteboard,
            }
        )
        return creators

    def _create_whiteboard(self, directory, name, template=None, values=None):
        """Create a `.excalidraw` in `directory`.

        A template, when given, is copied verbatim — a whiteboard template is
        a real `.excalidraw` the administrator drew. Without one, the empty
        scene is written so the editor opens on a blank canvas instead of
        failing to parse.
        """
        if template:
            content = template.content or ""
        else:
            payload = json.dumps(EMPTY_SCENE, separators=(",", ":")).encode("utf-8")
            content = base64.b64encode(payload)

        vals = {
            "name": name,
            "directory_id": directory.id,
            "content": content,
        }
        if values:
            vals.update(values)

        return self.env["dms.file"].create(vals)

    def _open_whiteboard(self, dms_file):
        """Open the whiteboard host page, not the bare Excalidraw service."""
        return {
            "type": "ir.actions.act_url",
            "url": "/dms_excalidraw/whiteboard/%s" % dms_file.id,
            "target": "new",
        }
