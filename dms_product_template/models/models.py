# -*- coding: utf-8 -*-
from odoo import models


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_product_template.product_template_dms_storage"
    _dms_access_mode = "inherit"
