# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import models

from odoo.addons.dms.tools.file import unique_name


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _dms_directories_create(self):
        """Create the DMS directory tree, with a unique name per sibling.

        OCA uses ``model_item.display_name`` verbatim. Two records with the
        same display name (two contacts called "Anna Andersson", two products
        with the same name) therefore produced two sibling directories with
        the same name - which ``_check_name`` rejects unless the context flag
        is off, and which is ambiguous for the user even when it is allowed.

        ``unique_name`` appends a suffix on collision, so the second record
        gets "Anna Andersson (2)" instead of a duplicate or an error.
        """
        items = self.sudo()._get_dms_directories(self.res_model, False)
        for item in items:
            model_item = self.env[self.res_model].browse(self.res_id)
            ir_model_item = (
                self.env["ir.model"].sudo().search([("model", "=", self.res_model)])
            )
            existing_names = item.child_directory_ids.mapped("name") or []
            dir_name = unique_name(model_item.display_name, existing_names)
            self.env["dms.directory"].sudo().with_context(check_name=False).create(
                {
                    "name": dir_name,
                    "model_id": ir_model_item.id,
                    "res_model": self.res_model,
                    "res_id": self.res_id,
                    "parent_id": item.id,
                    "storage_id": item.storage_id.id,
                }
            )
