# -*- coding: utf-8 -*-
from odoo import models


class Repair(models.Model):
    _name = "repair.order"
    _inherit = ["repair.order", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_repair_order.repair_order_dms_storage"
    _dms_access_mode = "inherit"
