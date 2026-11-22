# -*- coding: utf-8 -*-
from odoo import models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_purchase.purchase_order_dms_storage"
    _dms_access_mode = "inherit"
