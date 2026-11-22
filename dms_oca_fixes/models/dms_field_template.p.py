# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.dms.tools.file import unique_name


class DmsFieldTemplate(models.Model):
    _inherit = "dms.field.template"

    def create_dms_directory(self):
        """Create the template directory, with a unique name per sibling.

        Same problem as ``ir.attachment._dms_directories_create``: the
        prepared vals carry the record's display name verbatim, so two records
        with the same display name collide. ``unique_name`` appends a suffix
        instead of failing.
        """
        res_model = self.env.context.get("res_model")
        res_id = self.env.context.get("res_id")
        record = self.env[res_model].browse(res_id)
        directory_model = self.env["dms.directory"].sudo()
        if res_model == "dms.field.template":
            existing = (
                directory_model.search([("is_root_directory", "=", True)])
                .mapped("name")
                or []
            )
            return directory_model.create(
                {
                    "storage_id": record.storage_id.id,
                    "res_id": record.id,
                    "res_model": record._name,
                    "is_root_directory": True,
                    "name": unique_name(record.display_name, existing),
                    "group_ids": record.group_ids.ids,
                }
            )
        template = self._get_template_from_model(res_model).sudo()
        if not template:
            raise ValidationError(_("There is no template linked to this model"))
        total_directories = directory_model.search_count(
            [
                ("parent_id", "=", self.parent_directory_id.id),
                ("res_model", "=", res_model),
                ("res_id", "=", res_id),
                ("storage_id", "=", template.storage_id.id),
            ]
        )
        if total_directories > 0:
            raise ValidationError(_("There is already a linked directory created."))
        dms_directory_ids = template.dms_directory_ids
        vals = template._prepare_directory_vals(dms_directory_ids, record)
        if vals.get("parent_id"):
            parent = directory_model.browse(vals["parent_id"])
            existing = parent.child_directory_ids.mapped("name") or []
        else:
            existing = (
                directory_model.search([("is_root_directory", "=", True)])
                .mapped("name")
                or []
            )
        vals["name"] = unique_name(vals["name"], existing)
        return directory_model.create(vals)
