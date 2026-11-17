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

"""One "New document" wizard, extended by the modules that can create files.

WHY A REGISTRY AND NOT A FIXED LIST
===================================
`dms_excalidraw` knows how to make a `.excalidraw`. `dms_euro_office` knows
how to make `.docx`/`.xlsx`/`.pptx`. A third module may add `.md` or `.drawio`
tomorrow. If the wizard hard-coded the types, every new format would be an
edit to this module — and the wizard would grow a dependency on every module
that can create a document.

So the wizard asks the registry. A module registers a creator by subclassing
`dms.document.creator`:

    class DmsDocumentCreatorExcalidraw(models.Model):
        _inherit = "dms.document.creator"
        _name = "dms.document.creator.excalidraw"

        def _get_creators(self):
            return [{
                "key": "excalidraw",
                "label": _("Whiteboard"),
                "extension": "excalidraw",
                "sequence": 40,
                "create": self._create_excalidraw,
            }]

`_get_creators()` is called on an EMPTY recordset, so a creator does not need
a database row — it is a namespace for a function, not a record.

WHY A TEMPLATE AND NOT A GENERATED FILE
=======================================
An empty `.docx` is a zip with four XML parts and a `[Content_Types].xml`
that must list them. Generating that in Python is 80 lines that nobody
reviews; shipping a real empty `.docx` is one binary file that Word itself
produced. The binary wins: it opens in every client, and it is what the
"template" feature needs anyway.

Templates are `dms.file` records marked with `is_document_template`. A
template is a normal document — it inherits the directory's access groups,
retention and backup, and an administrator maintains it the same way as any
other file. No parallel store.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DmsDocumentCreator(models.AbstractModel):
    """Namespace for document creators. Subclassed by format modules."""

    _name = "dms.document.creator"
    _description = "Document creator registry"

    @api.model
    def _get_creators(self):
        """Return the list of creators this module contributes.

        Each entry is a dict:
            key        stable identifier, used in the wizard's selection
            label      what the user sees
            extension  file extension without the dot
            sequence   ordering in the dropdown (lower first)
            create     callable(directory, name, template) -> dms.file
        """
        return []

    @api.model
    def get_creators(self):
        """Aggregate every registered creator, ordered by sequence.

        Called on the abstract model, so every subclass's `_get_creators()`
        runs. Duplicate keys are a programming error, not a user error —
        two modules claiming `.docx` would silently shadow each other.
        """
        seen = {}
        for entry in self._get_creators():
            key = entry["key"]
            if key in seen:
                raise ValidationError(
                    _(
                        "Two document creators claim the key “%(key)s”. "
                        "Rename one of them.",
                        key=key,
                    )
                )
            seen[key] = entry
        return sorted(seen.values(), key=lambda e: (e.get("sequence", 100), e["key"]))

    @api.model
    def get_selection(self):
        """Return the creators as an Odoo selection list."""
        return [(c["key"], c["label"]) for c in self.get_creators()]

    @api.model
    def create_document(self, key, directory, name, template=None, values=None):
        """Create a document of type `key` in `directory`.

        `values` carries the optional fields the wizard collected —
        `category_id`, `tag_ids`. A creator merges them into its `create()`
        call, so a new format does not have to know about them.
        """
        for creator in self.get_creators():
            if creator["key"] == key:
                return creator["create"](directory, name, template, values)
        raise UserError(_("Unknown document type: %(key)s", key=key))

    @api.model
    def open_document(self, dms_file):
        """Return the action that opens a freshly created document.

        A creator may override this by putting `open` in its registry entry;
        otherwise the file is opened in its DMS form, which is where the
        "Open in ..." button lives.
        """
        for creator in self.get_creators():
            if creator["extension"] == dms_file.extension and creator.get("open"):
                return creator["open"](dms_file)

        return {
            "type": "ir.actions.act_window",
            "name": dms_file.name,
            "res_model": "dms.file",
            "res_id": dms_file.id,
            "view_mode": "form",
            "target": "current",
        }


class DmsDocumentWizard(models.TransientModel):
    """Ask for name, type and template before the file is created.

    Replaces the whiteboard-only wizard. The type list comes from the
    registry, so installing `dms_euro_office` adds Word/Excel/PowerPoint
    without touching this file.
    """

    _name = "dms.document.wizard"
    _description = "New document"

    directory_id = fields.Many2one(
        "dms.directory",
        string="Directory",
        required=True,
        ondelete="cascade",
    )
    document_type = fields.Selection(
        selection="_selection_document_type",
        string="Type",
        required=True,
        default=lambda self: self._default_document_type(),
    )
    name = fields.Char(
        string="Name",
        required=True,
        default=lambda self: self._default_name(),
        help="The extension is added automatically if you omit it.",
    )
    template_source = fields.Selection(
        selection="_selection_template_source",
        string="Start from",
        default="blank",
        required=True,
    )
    template_id = fields.Many2one(
        "dms.file",
        string="DMS template",
        domain="[('is_document_template', '=', True), "
        "('extension', '=', document_type)]",
        help="A document in DMS marked as a template.",
    )
    office_template_id = fields.Many2one(
        "euro_office.odoo.templates",
        string="Euro-Office form template",
        help="A fillable PDF form from Euro-Office Templates. The form is "
        "used as the starting point; filling it in is done in the editor.",
    )
    category_id = fields.Many2one(
        "dms.category",
        string="Category",
        help="Optional. Same categories the file form offers.",
    )
    tag_ids = fields.Many2many(
        "dms.tag",
        string="Tags",
        help="Optional. Free-form labels, shared with the rest of DMS.",
    )

    # --- Access ---------------------------------------------------------
    #
    # A `dms.file` has no ACL of its own: access comes from the DIRECTORY's
    # `group_ids` (dms.access.group). So the wizard cannot grant a file
    # narrower access than its folder — that is a property of the DMS model,
    # not a gap here.
    #
    # What it CAN do is show the inherited groups and let the user add more
    # to the directory in the same step, which is what "set it yourself"
    # means in practice: the groups belong to the folder.
    inherit_access = fields.Boolean(
        string="Inherit access from directory",
        default=True,
        help="The document is readable by whoever may read the directory. "
        "Uncheck to change the directory's groups below — that affects every "
        "document in the folder, not only this one.",
    )
    inherited_group_ids = fields.Many2many(
        "dms.access.group",
        string="Directory access",
        compute="_compute_inherited_group_ids",
        help="Groups the directory already grants access to.",
    )
    group_ids = fields.Many2many(
        "dms.access.group",
        string="Additional groups",
        help="Added to the directory's access groups. Applies to the whole "
        "folder, because DMS grants access per directory.",
    )

    name_taken = fields.Boolean(
        string="Name is taken",
        compute="_compute_name_taken",
    )

    @api.depends("directory_id")
    def _compute_inherited_group_ids(self):
        for wizard in self:
            wizard.inherited_group_ids = wizard.directory_id.group_ids

    @api.model
    def _selection_template_source(self):
        """What the new document starts from.

        `blank`        the shipped empty file
        `dms`          a `dms.file` marked `is_document_template`
        `office_form`  a fillable form from `euro_office.odoo.templates`

        The third option only appears when that module is installed: it is
        a different feature (Odoo fields inside a PDF form), not another
        way to store a blank document. Keeping them apart in the UI avoids
        the impression that they are interchangeable.
        """
        sources = [
            ("blank", _("Blank document")),
            ("dms", _("DMS template")),
        ]
        if "euro_office.odoo.templates" in self.env:
            sources.append(("office_form", _("Euro-Office form")))
        return sources

    @api.model
    def _selection_document_type(self):
        return self.env["dms.document.creator"].get_selection()

    @api.model
    def _default_document_type(self):
        creators = self.env["dms.document.creator"].get_creators()
        return creators[0]["key"] if creators else False

    @api.model
    def _extension_for(self, key):
        for creator in self.env["dms.document.creator"].get_creators():
            if creator["key"] == key:
                return creator["extension"]
        return key

    @api.model
    def _default_name(self):
        """Return the first free default name in the current directory."""
        directory_id = self.env.context.get("default_directory_id")
        if not directory_id:
            return _("Document")
        directory = self.env["dms.directory"].browse(directory_id)
        if not directory.exists():
            return _("Document")
        return self._first_free_name(directory, _("Document"))

    @api.model
    def _first_free_name(self, directory, base, limit=50):
        """Return `base`, then `base (2)`, `(3)`, ... as free."""
        DmsFile = self.env["dms.file"].sudo()
        if not DmsFile.search_count(
            [("directory_id", "=", directory.id), ("name", "=", base)]
        ):
            return base
        for n in range(2, limit + 1):
            candidate = "%s (%s)" % (base, n)
            if not DmsFile.search_count(
                [("directory_id", "=", directory.id), ("name", "=", candidate)]
            ):
                return candidate
        return base

    @api.depends("name", "directory_id", "document_type")
    def _compute_name_taken(self):
        DmsFile = self.env["dms.file"].sudo()
        for wizard in self:
            if not wizard.name or not wizard.directory_id:
                wizard.name_taken = False
                continue
            full = wizard._full_name()
            wizard.name_taken = bool(
                DmsFile.search_count(
                    [
                        ("directory_id", "=", wizard.directory_id.id),
                        ("name", "=", full),
                    ]
                )
            )

    def _full_name(self):
        """Return the name with the type's extension appended."""
        self.ensure_one()
        name = (self.name or "").strip()
        extension = ".%s" % self._extension_for(self.document_type)
        if not name.lower().endswith(extension.lower()):
            name = "%s%s" % (name, extension)
        return name

    @api.onchange("document_type")
    def _onchange_document_type(self):
        """Drop a template that no longer matches the selected type."""
        if self.template_id and self.template_id.extension != self.document_type:
            self.template_id = False

    @api.onchange("template_source")
    def _onchange_template_source(self):
        """Only the field for the chosen source stays filled."""
        if self.template_source != "dms":
            self.template_id = False
        if self.template_source != "office_form":
            self.office_template_id = False

    def action_create(self):
        """Create the document and open it."""
        self.ensure_one()
        if not self.directory_id.permission_create:
            raise UserError(
                _(
                    "You may not create documents in “%s”.",
                    self.directory_id.complete_name or self.directory_id.name,
                )
            )

        template = None
        if self.template_source == "dms":
            if not self.template_id:
                raise UserError(
                    _("Choose a DMS template, or switch to a blank document.")
                )
            template = self.template_id
        elif self.template_source == "office_form":
            if not self.office_template_id:
                raise UserError(
                    _("Choose a Euro-Office form, or switch to a blank document.")
                )
            template = self.office_template_id

        # Access is a property of the DIRECTORY in DMS, not of the file. So
        # "set it yourself" means adding groups to the folder — which affects
        # every document in it. The wizard says so in the field help, and the
        # write happens here, before the file is created, so the new file is
        # covered by the groups from its first moment.
        if not self.inherit_access and self.group_ids:
            self.directory_id.write(
                {"group_ids": [(4, group.id) for group in self.group_ids]}
            )

        values = {}
        if self.category_id:
            values["category_id"] = self.category_id.id
        if self.tag_ids:
            values["tag_ids"] = [(6, 0, self.tag_ids.ids)]

        dms_file = self.env["dms.document.creator"].create_document(
            self.document_type,
            self.directory_id,
            self._full_name(),
            template=template,
            values=values or None,
        )

        return self.env["dms.document.creator"].open_document(dms_file)
