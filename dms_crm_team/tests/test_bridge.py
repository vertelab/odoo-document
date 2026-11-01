# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsCrmTeam(DmsBridgeCase):
    model = "crm.team"
    access_mode = "team"
    storage_xmlid = "dms_crm_team.crm_team_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test team"}

    def _create_record(self):
        return self.env["crm.team"].create(self._create_record_vals())
