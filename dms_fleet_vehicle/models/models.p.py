# -*- coding: utf-8 -*-
from odoo import models


class Fleet(models.Model):
    _name = "fleet.vehicle"
    _inherit = ["fleet.vehicle", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_fleet_vehicle.fleet_vehicle_dms_storage"
    _dms_access_mode = "inherit"
