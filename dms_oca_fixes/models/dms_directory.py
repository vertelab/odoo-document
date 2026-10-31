# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, models
from odoo.exceptions import ValidationError

from odoo.addons.dms.tools.file import check_name


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    @api.constrains("name")
    def _check_name(self):
        """Honour ``check_name=False`` for both checks, not just the first.

        OCA's version guards the character check with the context flag but
        lets the duplicate check run unconditionally. So a caller that passes
        ``check_name=False`` - which by definition knows it is creating a
        colliding name on purpose - still gets "A directory with the same name
        already exists". That made the flag useless for the one case it exists
        for, and forced the source patch this module replaces.
        """
        for record in self:
            if not self.env.context.get("check_name", True):
                continue
            if not check_name(record.name):
                raise ValidationError(_("The directory name is invalid."))
            if record.is_root_directory:
                children = record.sudo().storage_id.root_directory_ids
            else:
                children = record.sudo().parent_id.child_directory_ids

            if children.filtered(
                lambda child, record=record: child.name == record.name
                and child != record
            ):
                raise ValidationError(
                    _("A directory with the same name already exists.")
                )
