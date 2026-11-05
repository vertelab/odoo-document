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

"""Word, Excel and PowerPoint as document types in the shared wizard.

The wizard (`dms.document.wizard`) knows nothing about office formats. It
asks `dms.document.creator` for every registered creator; this module adds
three. Installing it makes the formats appear in the dropdown — no change to
`dms_excalidraw` is needed.

THREE KINDS OF STARTING POINT
=============================
The wizard offers `blank`, `dms` template and (when Euro-Office Templates is
installed) `office_form`. This module has to handle all three:

    blank        the shipped empty file in static/templates/
    dms          a dms.file marked is_document_template — copied verbatim
    office_form  a euro_office.odoo.templates record — its attachment is
                 copied, and the user fills the form in the editor

They are not interchangeable. A DMS template is a document you maintain like
any other. A Euro-Office form is a PDF with Odoo fields in it, and filling it
is a different workflow. Keeping the code paths separate makes that visible.
"""

import base64
import logging
import os

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DmsDocumentCreatorOffice(models.AbstractModel):
    _inherit = "dms.document.creator"

    def _get_creators(self):
        """Add the office formats to whatever other modules registered.

        `super()` is essential: every creator module subclasses the same
        abstract model, and Odoo calls only the LAST `_get_creators()`.
        Without the chain, installing this module would silently replace the
        whiteboard entry with Word/Excel/PowerPoint.
        """
        creators = super()._get_creators()
        creators.extend(
            [
                {
                    "key": "docx",
                    "label": _("Word"),
                    "extension": "docx",
                    "sequence": 10,
                    "create": self._create_office,
                    "open": self._open_office,
                },
                {
                    "key": "xlsx",
                    "label": _("Excel"),
                    "extension": "xlsx",
                    "sequence": 20,
                    "create": self._create_office,
                    "open": self._open_office,
                },
                {
                    "key": "pptx",
                    "label": _("PowerPoint"),
                    "extension": "pptx",
                    "sequence": 30,
                    "create": self._create_office,
                    "open": self._open_office,
                },
            ]
        )
        return creators

    # ------------------------------------------------------------------
    # Blank files
    # ------------------------------------------------------------------

    def _empty_template(self, extension):
        """Return the bytes of the shipped empty file for `extension`.

        Read from the module directory, not from an attachment: the file is
        part of the code, versioned with it, and identical for every
        database. An attachment would have to be created per database and
        would drift.
        """
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "static",
            "templates",
            "empty.%s" % extension,
        )
        if not os.path.exists(path):
            _logger.error("dms_document_office: missing template %s", path)
            return None
        with open(path, "rb") as handle:
            return handle.read()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def _create_office(self, directory, name, template=None, values=None):
        """Create an office document in `directory`.

        `template` is either a `dms.file` (marked as a template) or a
        `euro_office.odoo.templates` record. The two are told apart by model
        name, because the wizard passes whichever the user chose and the
        creator should not need a second parameter for it.
        """
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else "docx"
        content = None

        if template is not None:
            model = template._name
            if model == "dms.file":
                content = template.content or ""
                if not content:
                    _logger.warning(
                        "dms_document_office: DMS template %s is empty; "
                        "falling back to the shipped blank file",
                        template.id,
                    )
                    content = None
            elif model == "euro_office.odoo.templates":
                content = self._content_from_office_template(template)
            else:
                _logger.warning(
                    "dms_document_office: unknown template model %s; "
                    "falling back to the shipped blank file",
                    model,
                )

        if not content:
            raw = self._empty_template(extension)
            if raw is None:
                # A missing template is a deployment error, not a user error.
                # Creating a zero-byte .docx would look like it worked and
                # then fail to open — worse than refusing.
                raise UserError(
                    _(
                        "The blank %(ext)s template is missing from the "
                        "module. Reinstall dms_document_office.",
                        ext=extension,
                    )
                )
            content = base64.b64encode(raw)

        vals = {
            "name": name,
            "directory_id": directory.id,
            "content": content,
        }
        if values:
            vals.update(values)

        return self.env["dms.file"].create(vals)

    def _content_from_office_template(self, template):
        """Return base64 content from a Euro-Office form template.

        The template keeps its file in an `ir.attachment` (`attachment_id`),
        not in a binary field of its own — `file` is the upload field and is
        cleared after the attachment is written. Reading `file` would give an
        empty value for every template that was uploaded more than once.
        """
        attachment = template.attachment_id
        if not attachment:
            _logger.warning(
                "dms_document_office: Euro-Office template %s has no "
                "attachment; falling back to the shipped blank file",
                template.id,
            )
            return None

        # `datas` is base64 already — dms.file.content expects base64 too.
        return attachment.datas

    # ------------------------------------------------------------------
    # Opening
    # ------------------------------------------------------------------

    def _open_office(self, dms_file):
        """Open the new document in Euro-Office when it is installed.

        `dms_euro_office` ships the editor bridge. Without it the file is
        opened in its DMS form, which is still a valid place to download it
        from — a broken link would be worse.
        """
        if "can_open_in_euro_office" in self.env["dms.file"]._fields:
            return dms_file.open_in_euro_office_action()

        return {
            "type": "ir.actions.act_window",
            "name": dms_file.name,
            "res_model": "dms.file",
            "res_id": dms_file.id,
            "view_mode": "form",
            "target": "current",
        }
