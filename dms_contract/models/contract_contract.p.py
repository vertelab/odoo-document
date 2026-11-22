# -*- coding: utf-8 -*-
from odoo import models


class ContractContract(models.Model):
    _name = "contract.contract"
    _inherit = ["contract.contract", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_contract.contract_dms_storage"
    _dms_access_mode = "inherit"
