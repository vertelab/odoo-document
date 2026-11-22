# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dms_clamav_enabled = fields.Boolean(
        string="Scan Uploads",
        config_parameter="dms_clamav.enabled",
        default=True,
    )
    dms_clamav_host = fields.Char(
        string="clamd Host",
        config_parameter="dms_clamav.host",
        default="localhost",
    )
    dms_clamav_port = fields.Integer(
        string="clamd Port",
        config_parameter="dms_clamav.port",
        default=3310,
    )
