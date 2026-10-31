# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import base64
import datetime

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDmsTrash(TransactionCase):
    """Soft delete and purge behaviour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage = cls.env["dms.storage"].create(
            {"name": "Trash Test Storage", "save_type": "database"}
        )
        cls.root = cls.env["dms.directory"].create(
            {
                "name": "Trash Root",
                "storage_id": cls.storage.id,
                "is_root_directory": True,
            }
        )
        cls.directory = cls.env["dms.directory"].create(
            {
                "name": "Trash Dir",
                "storage_id": cls.storage.id,
                "parent_id": cls.root.id,
                "deletion_delay": 7,
            }
        )

    def _make_file(self, name="trash.txt"):
        return self.env["dms.file"].create(
            {
                "name": name,
                "directory_id": self.directory.id,
                "content": base64.b64encode(b"payload"),
            }
        )

    def test_delete_with_delay_archives(self):
        """A delete with a retention archives instead of removing."""
        record = self._make_file()
        record.unlink()
        found = (
            self.env["dms.file"]
            .with_context(active_test=False)
            .search([("id", "=", record.id)])
        )
        self.assertTrue(found, "the file must still exist")
        self.assertFalse(found.active)
        self.assertTrue(found.deletion_date)

    def test_delete_without_delay_removes(self):
        """deletion_delay = 0 keeps the old immediate behaviour."""
        self.directory.deletion_delay = 0
        record = self._make_file("immediate.txt")
        record_id = record.id
        record.unlink()
        found = (
            self.env["dms.file"]
            .with_context(active_test=False)
            .search([("id", "=", record_id)])
        )
        self.assertFalse(found, "the file must be gone")

    def test_restore_from_trash(self):
        """A trashed file can be brought back."""
        record = self._make_file()
        record.unlink()
        record.action_restore_from_trash()
        record.invalidate_recordset()
        self.assertTrue(record.active)
        self.assertFalse(record.deletion_date)

    def test_purge_removes_only_expired(self):
        """The cron removes expired files and leaves the rest."""
        expired = self._make_file("expired.txt")
        fresh = self._make_file("fresh.txt")
        expired.unlink()
        fresh.unlink()
        expired.write(
            {"deletion_date": fields.Datetime.now() - datetime.timedelta(days=1)}
        )
        # raw SQL in the cron needs the values flushed first
        self.env["dms.file"].flush_recordset(["deletion_date", "active"])
        self.env["dms.file"]._cron_purge_trash()
        remaining = (
            self.env["dms.file"]
            .with_context(active_test=False)
            .search([("id", "in", [expired.id, fresh.id])])
        )
        self.assertEqual(
            remaining.ids,
            [fresh.id],
            "only the expired file may be purged",
        )
