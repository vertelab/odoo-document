# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsAccountAsset(DmsBridgeCase):
    model = "account.asset"
    access_mode = "inherit"
    storage_xmlid = "dms_account_asset.asset_dms_storage"

    def _create_record_vals(self):
        # Minimal valid asset; business logic is not what this test is about.
        # OCA ships no demo profile, so build the smallest one that validates.
        account = self.env["account.account"].create(
            {
                "name": "Test asset account",
                "code": "TESTASSET",
                "account_type": "asset_fixed",
            }
        )
        profile = self.env["account.asset.profile"].create(
            {
                "name": "Test profile",
                "account_asset_id": account.id,
                "account_depreciation_id": account.id,
                "account_expense_depreciation_id": account.id,
                "journal_id": self.env["account.journal"].search(
                    [("type", "=", "general")], limit=1
                ).id,
                "method": "linear",
                "method_number": 5,
                "method_period": "year",
            }
        )
        return {
            "name": "Test asset",
            "code": "TEST001",
            "profile_id": profile.id,
            "purchase_value": 1000.0,
            "salvage_value": 100.0,
            "date_start": "2026-01-01",
        }

    def _create_record(self):
        return self.env["account.asset"].create(self._create_record_vals())
