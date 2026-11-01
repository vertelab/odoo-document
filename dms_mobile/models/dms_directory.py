# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    mobile_target = fields.Boolean(
        help="Show this directory on /dms/mobile with a camera button. "
             "Use it for the few directories a phone user actually uploads "
             "to, not for the whole tree.",
    )
