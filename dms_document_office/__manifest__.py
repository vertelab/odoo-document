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
    "name": "DMS Document: Office",
    "summary": "Create Word, Excel and PowerPoint documents from DMS",
    "description": """
Registers the office formats with the shared "New document" wizard
(`dms.document.creator`), so a user can create a blank or template-based
`.docx`, `.xlsx` or `.pptx` directly in a DMS directory.

WHY A SEPARATE MODULE
=====================
The registry lives in `dms_excalidraw` because that module ships the first
creator. Putting the office creators there would make `dms_excalidraw` depend
on `dms_euro_office` — and a customer who wants whiteboards without
Euro-Office could not install it. A module per format family keeps the
dependency graph honest:

    dms_excalidraw          registry + whiteboard
    dms_document_office     Word / Excel / PowerPoint   <- this module

WHY SHIPPED EMPTY FILES AND NOT GENERATED ONES
==============================================
An empty `.docx` is a zip with three XML parts and a `[Content_Types].xml`
that must list them. Generating that in Python is ~80 lines nobody reviews.
The three files in `static/templates/` were produced by the format itself and
are 1-2 KB each. They open in Word, LibreOffice and Euro-Office, which is the
only test that matters.

WHY TEMPLATES ARE `dms.file` RECORDS
====================================
A template is a normal document marked `is_document_template`. It inherits
the directory's access groups, retention and backup, appears in the customer's
Documents counter, and is maintained like any other file. No parallel store,
no second permission model.
""",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "category": "Productivity/Documents",
    "version": "18.0.1.0.1",
    "depends": ["dms", "dms_excalidraw"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
