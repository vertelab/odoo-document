# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsAccountMove(DmsBridgeCase):
    model = "account.move"
    access_mode = "inherit"
    storage_xmlid = "dms_account_move.account_move_dms_storage"

    def _create_record_vals(self):
        return {"move_type": "entry", "ref": "Test"}

    def _create_record(self):
        return self.env["account.move"].create(self._create_record_vals())
