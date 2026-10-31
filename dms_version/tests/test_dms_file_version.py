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
        cls.directory = cls.env["dms.directory"].create(
            {"name": "Version Test Dir", "storage_id": cls.storage.id}
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
        self._write_content(self.file, b"second", source="form")
        self.assertEqual(len(self.file.version_ids), 1)
        version = self.file.version_ids
        self.assertEqual(version.content_source, "form")
        self.assertEqual(base64.b64decode(version._get_content()), b"initial")

    def test_version_source_webdav(self):
        """The source is taken from the dms_source context key."""
        self._write_content(self.file, b"second", source="webdav")
        self.assertEqual(self.file.version_ids.content_source, "webdav")

    def test_version_source_defaults_to_form(self):
        """Without a context key the source falls back to form."""
        self._write_content(self.file, b"second")
        self.assertEqual(self.file.version_ids.content_source, "form")

    def test_version_number_sequence(self):
        """Version numbers are sequential per file and never reused (task 3.6)."""
        for payload in (b"second", b"third", b"fourth"):
            self._write_content(self.file, payload)
        numbers = sorted(self.file.version_ids.mapped("version_number"))
        self.assertEqual(numbers, [1, 2, 3])

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
        self.assertEqual(self.file.version_ids.version_number, 1)
        self.assertEqual(other.version_ids.version_number, 1)

    def test_restore_creates_new_version(self):
        """Restoring keeps the replaced content as a new version (task 3.7)."""
        self._write_content(self.file, b"second")
        first_version = self.file.version_ids
        first_version.action_restore()
        self.assertEqual(base64.b64decode(self.file.content), b"initial")
        self.assertEqual(len(self.file.version_ids), 2)
        restored = self.file.version_ids.filtered(
            lambda v: v.content_source == "restore"
        )
        self.assertEqual(len(restored), 1)
        self.assertEqual(base64.b64decode(restored._get_content()), b"second")

    def test_retention_keeps_latest(self):
        """Retention prunes old versions but never the latest (task 3.8)."""
        self.directory.version_retention_count = 2
        for payload in (b"second", b"third", b"fourth"):
            self._write_content(self.file, payload)
        self.assertEqual(len(self.file.version_ids), 3)
        self.env["dms.file.version"]._cron_prune_versions()
        remaining = self.file.version_ids.sorted("version_number")
        self.assertEqual(len(remaining), 2)
        self.assertEqual(remaining.mapped("version_number"), [2, 3])

    def test_retention_zero_means_unlimited(self):
        """A retention count of 0 keeps everything."""
        self.directory.version_retention_count = 0
        for payload in (b"second", b"third", b"fourth"):
            self._write_content(self.file, payload)
        self.env["dms.file.version"]._cron_prune_versions()
        self.assertEqual(len(self.file.version_ids), 3)
