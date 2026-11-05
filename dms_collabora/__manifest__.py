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

{
    "name": "DMS Document: Collabora",
    "summary": "Open DMS office documents in Collabora Online",
    "description": """
Registers Collabora Online as the editor for office documents in DMS.

WHY A BRIDGE AND NOT A PATCH OF dms_excalidraw
==============================================
`dms_excalidraw` owns the click in the Files view. Its capability table maps
an extension to a capability field and an action method on `dms.file`:

    docx -> can_open_in_euro_office -> open_in_euro_office_action

That table is backend-agnostic in SHAPE but the entries name one backend.
Adding Collabora by editing it would repeat the mistake it was written to fix
(a table that hardcodes a vendor) — and `dms_excalidraw` would have to know
about Collabora.

Instead this module contributes the same two things `dms_euro_office` does:
a computed `can_open_in_collabora` field and an action that returns an
`act_url`. Whatever reads the capability table picks it up.

WHY THE URL NEEDS THE ATTACHMENT, NOT THE FILE
==============================================
`collabora_odoo` serves its editor at

    /collabora_odoo/frame/<attachment_id>/<read|write>

where the id is an `ir.attachment`, not a `dms.file`. DMS keeps its bytes in
the attachment field `content_file` (`dms/models/dms_file.py`:
`content_file = fields.Binary(attachment=True)`), so this module resolves
`dms.file` -> its `content_file` attachment and passes THAT id.

Passing the `dms.file` id would look up an unrelated attachment or none at
all — the failure mode is a 404 with no hint about which id was wrong.

WHY THE MODE IS read/write AND NOT edit
=======================================
`collabora_odoo`'s own JS switches on `read` and `write` and silently falls
back to `read` for anything else. `edit` is not a value it knows. A user
clicking "edit" and getting a read-only editor would blame the editor, not
the URL.
""",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "category": "Productivity/Documents",
    "version": "18.0.1.0.0",
    "depends": ["dms", "collabora_odoo"],
    "data": [
        "views/dms_file_view.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
