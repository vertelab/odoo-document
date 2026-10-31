# -*- coding: utf-8 -*-
from odoo import models


class PropertyProperty(models.Model):
    _name = "property.property"
    _inherit = ["property.property", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_property_mgmt.property_property_dms_storage"
    _dms_access_mode = "inherit"
