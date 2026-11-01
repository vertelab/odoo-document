# -*- coding: utf-8 -*-
from odoo import models


class SlideSlide(models.Model):
    _name = "slide.slide"
    _inherit = ["slide.slide", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_slide.slide_slide_dms_storage"
    _dms_access_mode = "inherit"
