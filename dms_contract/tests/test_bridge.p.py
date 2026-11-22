# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsContract(DmsBridgeCase):
    model = "contract.contract"
    access_mode = "inherit"
    storage_xmlid = "dms_contract.contract_dms_storage"

    def _create_record_vals(self):
        return {
            "name": "Test contract",
            "partner_id": self.env["res.partner"].create({"name": "Test customer"}).id,
        }

    def _create_record(self):
        return self.env["contract.contract"].create(self._create_record_vals())
