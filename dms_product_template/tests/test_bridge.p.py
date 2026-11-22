# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsProductTemplate(DmsBridgeCase):
    model = "product.template"
    access_mode = "inherit"
    storage_xmlid = "dms_product_template.product_template_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test produkt"}

    def _create_record(self):
        return self.env["product.template"].create(self._create_record_vals())
