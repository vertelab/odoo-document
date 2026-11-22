# -*- coding: utf-8 -*-
from odoo import models


class Partner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_partner.partner_dms_storage"
    _dms_access_mode = "inherit"
