# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsSaleOrder(DmsBridgeCase):
    model = "sale.order"
    access_mode = "inherit"
    storage_xmlid = "dms_sale_order.sale_order_dms_storage"

    def _create_record_vals(self):
        return {"partner_id": self.env["res.partner"].create({"name": "Kund"}).id}

    def _create_record(self):
        return self.env["sale.order"].create(self._create_record_vals())
