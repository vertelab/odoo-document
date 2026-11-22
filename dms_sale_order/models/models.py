# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_sale_order.sale_order_dms_storage"
    _dms_access_mode = "inherit"
