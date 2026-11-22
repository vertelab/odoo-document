# -*- coding: utf-8 -*-
from odoo import models


class EventEvent(models.Model):
    _name = "event.event"
    _inherit = ["event.event", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_event.event_event_dms_storage"
    _dms_access_mode = "inherit"
