# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsPurchase(DmsBridgeCase):
    model = "purchase.order"
    access_mode = "inherit"
    storage_xmlid = "dms_purchase.purchase_order_dms_storage"

    def _create_record_vals(self):
        return {"partner_id": self.env["res.partner"].create({"name": "Lev"}).id}

    def _create_record(self):
        return self.env["purchase.order"].create(self._create_record_vals())
