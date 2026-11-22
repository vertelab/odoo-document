# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsEvent(DmsBridgeCase):
    model = "event.event"
    access_mode = "inherit"
    storage_xmlid = "dms_event.event_event_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test event", "date_begin": "2026-01-01 10:00:00",
                "date_end": "2026-01-01 12:00:00"}

    def _create_record(self):
        return self.env["event.event"].create(self._create_record_vals())
