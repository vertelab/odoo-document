# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    version_retention_count = fields.Integer(
        string="Keep Versions",
        default=10,
        help="Number of versions to keep per file. 0 means unlimited. "
             "The most recent version is never pruned.",
    )
    version_retention_days = fields.Integer(
        string="Keep Versions For (days)",
        default=0,
        help="Delete versions older than this many days. 0 means no age limit. "
             "The most recent version is never pruned.",
    )
