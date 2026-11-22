# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_account_move.account_move_dms_storage"
    _dms_access_mode = "inherit"
