# -*- coding: utf-8 -*-
from odoo import models


class AccountAsset(models.Model):
    _name = "account.asset"
    _inherit = ["account.asset", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_account_asset.asset_dms_storage"
    _dms_access_mode = "inherit"
