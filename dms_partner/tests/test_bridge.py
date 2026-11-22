# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsPartner(DmsBridgeCase):
    model = "res.partner"
    access_mode = "inherit"
    storage_xmlid = "dms_partner.partner_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test partner"}

    def _create_record(self):
        return self.env["res.partner"].create(self._create_record_vals())
