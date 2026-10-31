# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsHrEmployee(DmsBridgeCase):
    model = "hr.employee"
    access_mode = "owner"
    storage_xmlid = "dms_hr_employee.hr_employee_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test anstalld", "user_id": self.env.user.id}

    def _create_record(self):
        return self.env["hr.employee"].create(self._create_record_vals())
