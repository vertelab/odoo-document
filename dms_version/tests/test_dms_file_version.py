# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import base64

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDmsFileVersion(TransactionCase):
    """Version history behaviour of dms.file.content."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage = cls.env["dms.storage"].create(
            {"name": "Version Test Storage", "save_type": "database"}
        )
        # dms.directory requires a parent: the root directory of the storage.
        cls.root_directory = cls.env["dms.directory"].create(
            {
                "name": "Version Test Root",
                "storage_id": cls.storage.id,
                "is_root_directory": True,
            }
        )
        cls.directory = cls.env["dms.directory"].create(
            {
                "name": "Version Test Dir",
                "storage_id": cls.storage.id,
                "parent_id": cls.root_directory.id,
            }
        )
        cls.file = cls.env["dms.file"].create(
            {
                "name": "test.txt",
                "directory_id": cls.directory.id,
                "content": base64.b64encode(b"initial"),
            }
        )

    def _write_content(self, file_record, raw, source=None):
        ctx = {"dms_source": source} if source else {}
        file_record.with_context(**ctx).write(
            {"content": base64.b64encode(raw)}
        )

    def test_no_version_on_create(self):
        """A brand new file must not get a version of itself (task 3.5)."""
        self.assertEqual(
            self.file.version_ids,
            self.env["dms.file.version"],
            "create() must not produce a version",
        )

    def test_version_created_on_write(self):
        """Overwriting content keeps the previous content as a version."""
        before = len(self.file.version_ids)
        self._write_content(self.file, b"second", source="form")
        self.assertEqual(len(self.file.version_ids), before + 1)
        version = self.file.version_ids.sorted("version_number")[-1]
        self.assertEqual(version.content_source, "form")
        self.assertEqual(base64.b64decode(version._get_content()), b"initial")

    def test_version_source_webdav(self):
        """The source is taken from the dms_source context key."""
        self._write_content(self.file, b"second", source="webdav")
        version = self.file.version_ids.sorted("version_number")[-1]
        self.assertEqual(version.content_source, "webdav")

    def test_version_source_defaults_to_form(self):
        """Without a context key the source falls back to form."""
        self._write_content(self.file, b"second")
        version = self.file.version_ids.sorted("version_number")[-1]
        self.assertEqual(version.content_source, "form")

    def test_version_number_sequence(self):
        """Version numbers are sequential per file and never reused (task 3.6)."""
        before = len(self.file.version_ids)
        for payload in (b"second", b"third", b"fourth"):
            self._write_content(self.file, payload)
        numbers = sorted(self.file.version_ids.mapped("version_number"))
        self.assertEqual(len(numbers), before + 3)
        self.assertEqual(numbers, list(range(1, before + 4)))

    def test_version_numbers_are_per_file(self):
        """Two files each start at version 1."""
        other = self.env["dms.file"].create(
            {
                "name": "other.txt",
                "directory_id": self.directory.id,
                "content": base64.b64encode(b"other"),
            }
        )
        self._write_content(self.file, b"second")
        self._write_content(other, b"second")
        self.assertEqual(
            min(self.file.version_ids.mapped("version_number")), 1
        )
        self.assertEqual(min(other.version_ids.mapped("version_number")), 1)

    def test_restore_creates_new_version(self):
        """Restoring keeps the replaced content as a new version (task 3.7)."""
        before = len(self.file.version_ids)
        self._write_content(self.file, b"second")
        first_version = self.file.version_ids.sorted("version_number")[-1]
        first_version.action_restore()
        self.assertEqual(base64.b64decode(self.file.content), b"initial")
        self.assertEqual(len(self.file.version_ids), before + 2)
        restored = self.file.version_ids.filtered(
            lambda v: v.content_source == "restore"
        )
        self.assertEqual(len(restored), 1)
        self.assertEqual(base64.b64decode(restored._get_content()), b"second")

    def test_retention_keeps_latest(self):
        """Retention prunes old versions but never the latest (task 3.8)."""
        self.directory.version_retention_count = 2
        # The prune runs raw SQL, so the policy must be in the database first.
        self.directory.flush_recordset(["version_retention_count"])
        before = len(self.file.version_ids)
        for payload in (b"second", b"third", b"fourth"):
            self._write_content(self.file, payload)
        self.assertEqual(len(self.file.version_ids), before + 3)
        self.env["dms.file.version"]._cron_prune_versions()
        remaining = self.file.version_ids.sorted("version_number")
        self.assertEqual(len(remaining), 2)
        self.assertEqual(
            remaining.mapped("version_number"),
            [before + 2, before + 3],
        )

    def test_retention_zero_means_unlimited(self):
        """A retention count of 0 keeps everything."""
        self.directory.version_retention_count = 0
        self.directory.flush_recordset(["version_retention_count"])
        before = len(self.file.version_ids)
        for payload in (b"second", b"third", b"fourth"):
            self._write_content(self.file, payload)
        self.env["dms.file.version"]._cron_prune_versions()
        self.assertEqual(len(self.file.version_ids), before + 3)
