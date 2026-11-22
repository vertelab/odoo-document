# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsCrmLead(DmsBridgeCase):
    model = "crm.lead"
    access_mode = "inherit"
    storage_xmlid = "dms_crm_lead.crm_lead_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test lead"}

    def _create_record(self):
        return self.env["crm.lead"].create(self._create_record_vals())
