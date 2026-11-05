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

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DmsExcalidrawWizard(models.TransientModel):
    """Ask for the whiteboard's name before the file is created.

    Why a wizard and not a `name` query parameter: "New whiteboard" used to
    create `Whiteboard.excalidraw` immediately, with no way to name it. The
    only way to rename was to close the editor, find the file in DMS and
    rename it there -- and a second click collided with the first file and
    answered 404.

    The wizard is opened by the directory button. It validates the name
    against the directory's existing files so the user sees the collision
    before the file is created, not as an error afterwards.

    The controller still accepts `?name=` and still falls back to numbered
    names: the wizard is the normal path, but a direct URL must keep working.
    """

    _name = "dms.excalidraw.wizard"
    _description = "New whiteboard"

    directory_id = fields.Many2one(
        "dms.directory",
        string="Directory",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(
        string="Name",
        required=True,
        default=lambda self: self._default_name(),
        help="The .excalidraw extension is added automatically if you omit it.",
    )
    name_taken = fields.Boolean(
        string="Name is taken",
        compute="_compute_name_taken",
        help="True when the directory already holds a file with this name.",
    )

    @api.model
    def _default_name(self):
        """Return the first free default name in the current directory.

        `default_directory_id` comes from the button's context. When it is
        absent (e.g. the wizard opened from a menu) the plain default is
        returned and the collision check happens on save instead.
        """
        directory_id = self.env.context.get("default_directory_id")
        if not directory_id:
            return _("Whiteboard")
        directory = self.env["dms.directory"].browse(directory_id)
        if not directory.exists():
            return _("Whiteboard")
        return self._first_free_name(directory)

    @api.model
    def _first_free_name(self, directory, limit=50):
        """Return `Whiteboard`, then `Whiteboard (2)`, `(3)`, ... as free.

        Same convention desktop file managers use, and the same fallback the
        controller applies when a name is taken at creation time.
        """
        DmsFile = self.env["dms.file"].sudo()
        candidate = _("Whiteboard")
        if not DmsFile.search_count(
            [("directory_id", "=", directory.id), ("name", "=", candidate)]
        ):
            return candidate
        for n in range(2, limit + 1):
            candidate = _("Whiteboard (%s)", n)
            if not DmsFile.search_count(
                [("directory_id", "=", directory.id), ("name", "=", candidate)]
            ):
                return candidate
        return _("Whiteboard")

    @api.depends("name", "directory_id")
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
        """Return the name with the .excalidraw extension appended."""
        self.ensure_one()
        name = (self.name or "").strip()
        extension = ".excalidraw"
        if not name.lower().endswith(extension):
            name = "%s%s" % (name, extension)
        return name

    def action_create(self):
        """Create the whiteboard and open the editor."""
        self.ensure_one()
        if not self.directory_id.permission_create:
            raise UserError(
                _("You may not create documents in “%s”.", self.directory_id.name)
            )

        action = (
            self.env["dms.file"]
            .with_context(default_directory_id=self.directory_id.id)
            .action_new_whiteboard(
                directory=self.directory_id,
                name=self._full_name(),
            )
        )
        return action
