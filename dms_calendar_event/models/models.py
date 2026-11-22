# -*- coding: utf-8 -*-
from odoo import models


class Events(models.Model):
    _name = "calendar.event"
    _inherit = ["calendar.event", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_calendar_event.calendar_event_dms_storage"
    _dms_access_mode = "inherit"
