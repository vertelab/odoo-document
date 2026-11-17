# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DmsFile(models.Model):
    _inherit = "dms.file"

    version_ids = fields.One2many(
        "dms.file.version",
        "file_id",
        string="Versions",
        readonly=True,
    )
    version_count = fields.Integer(
        compute="_compute_version_count",
        string="Version Count",
    )

    @api.depends("version_ids")
    def _compute_version_count(self):
        for record in self:
            record.version_count = len(record.version_ids)

    def write(self, vals):
        """Keep the previous content as a version before overwriting it.

        Hooked on write() rather than _inverse_content(): by the time the
        inverse runs, Odoo has already assigned the new value to the record,
        so reading the old content there returns the new bytes. Reading
        _origin.content here, before super().write(), is the only point where
        the previous value is still available.

        create() is deliberately not covered: a new file has no previous
        content, so there is nothing to keep.
        """
        if "content" in vals and vals["content"]:
            for record in self:
                previous = record._origin.content
                if not previous:
                    continue
                self.env["dms.file.version"]._create_version(record, previous)
        return super().write(vals)

    def action_view_versions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "dms_version.dms_file_version_action"
        )
        action["domain"] = [("file_id", "=", self.id)]
        action["context"] = {"default_file_id": self.id}
        return action
