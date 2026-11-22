# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsCalendarEvent(DmsBridgeCase):
    model = "calendar.event"
    access_mode = "inherit"
    storage_xmlid = "dms_calendar_event.calendar_event_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test mote", "start": "2026-01-01 10:00:00",
                "stop": "2026-01-01 12:00:00"}

    def _create_record(self):
        return self.env["calendar.event"].create(self._create_record_vals())
