# -*- coding: utf-8 -*-
from odoo import models


class HrEmployee(models.Model):
    _name = "hr.employee"
    _inherit = ["hr.employee", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_hr_employee.hr_employee_dms_storage"
    _dms_access_mode = "owner"

    def _dms_owner_field(self):
        """The employee's own user is the owner of their documents."""
        self.ensure_one()
        return self.user_id
