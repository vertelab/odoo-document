# -*- coding: utf-8 -*-
from odoo import models


class SlideChannel(models.Model):
    _name = "slide.channel"
    _inherit = ["slide.channel", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_slide.slide_channel_dms_storage"
    _dms_access_mode = "inherit"
