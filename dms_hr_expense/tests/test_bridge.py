# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsHrExpense(DmsBridgeCase):
    model = "hr.expense"
    access_mode = "inherit"
    storage_xmlid = "dms_hr_expense.hr_expense_dms_storage"

    def _create_record_vals(self):
        return {
            "name": "Taxi",
            "employee_id": self.env["hr.employee"].create({"name": "Test"}).id,
            "total_amount": 100.0,
            "product_id": self.env.ref("hr_expense.expense_product_meal").id,
        }

    def _create_record(self):
        return self.env["hr.expense"].create(self._create_record_vals())
