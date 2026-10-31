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

    def _inverse_content(self):
        """Keep the previous content as a version before overwriting it.

        ``_inverse_content`` also runs on create, so guard on both ``record.id``
        (the row already exists in the database) and ``record._origin.content``
        (there was content before). A brand new file must not get a version of
        itself.
        """
        for record in self:
            if not record.id:
                continue
            previous = record._origin.content
            if not previous:
                continue
            self.env["dms.file.version"]._create_version(record, previous)
        return super()._inverse_content()

    def action_view_versions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "dms_version.dms_file_version_action"
        )
        action["domain"] = [("file_id", "=", self.id)]
        action["context"] = {"default_file_id": self.id}
        return action
