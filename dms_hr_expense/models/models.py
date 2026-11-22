# -*- coding: utf-8 -*-
from odoo import models


class HrExpense(models.Model):
    _name = "hr.expense"
    _inherit = ["hr.expense", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_hr_expense.hr_expense_dms_storage"
    _dms_access_mode = "inherit"
