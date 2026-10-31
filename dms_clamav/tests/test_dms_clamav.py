# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import base64
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDmsClamav(TransactionCase):
    """Scan behaviour of dms.file writes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage = cls.env["dms.storage"].create(
            {"name": "ClamAV Test Storage", "save_type": "database"}
        )
        cls.root = cls.env["dms.directory"].create(
            {
                "name": "ClamAV Root",
                "storage_id": cls.storage.id,
                "is_root_directory": True,
            }
        )
        cls.directory = cls.env["dms.directory"].create(
            {
                "name": "ClamAV Dir",
                "storage_id": cls.storage.id,
                "parent_id": cls.root.id,
            }
        )

    def _make_file(self, payload=b"clean"):
        return self.env["dms.file"].create(
            {
                "name": "scan.txt",
                "directory_id": self.directory.id,
                "content": base64.b64encode(payload),
            }
        )

    def test_clean_file_is_stored(self):
        """A clean file passes the scan."""
        with patch.object(
            type(self.env["dms.file"]), "_clamav_scan", return_value=None
        ):
            record = self._make_file()
        self.assertTrue(record.id)

    def test_infected_file_is_rejected(self):
        """An infected file raises and is never stored."""
        with patch.object(
            type(self.env["dms.file"]),
            "_clamav_scan",
            return_value="Eicar-Test-Signature",
        ):
            with self.assertRaises(ValidationError):
                self._make_file()
        self.assertFalse(
            self.env["dms.file"].search([("name", "=", "scan.txt")]),
            "the rejected file must not exist",
        )

    def test_infected_overwrite_is_rejected(self):
        """An infected overwrite leaves the original content untouched."""
        with patch.object(
            type(self.env["dms.file"]), "_clamav_scan", return_value=None
        ):
            record = self._make_file(b"original")
        with patch.object(
            type(self.env["dms.file"]),
            "_clamav_scan",
            return_value="Eicar-Test-Signature",
        ):
            with self.assertRaises(ValidationError):
                record.write({"content": base64.b64encode(b"infected")})
        record.invalidate_recordset()
        self.assertEqual(base64.b64decode(record.content), b"original")

    def test_infected_file_creates_no_version(self):
        """The scan runs before the version snapshot (task 5.2).

        A rejected write must not leave a version behind: the whole point of
        scanning before storing is that the infected bytes never enter the
        system, and a version is a stored copy.
        """
        if "dms.file.version" not in self.env:
            self.skipTest("dms_version is not installed")
        with patch.object(
            type(self.env["dms.file"]), "_clamav_scan", return_value=None
        ):
            record = self._make_file(b"original")
        before = len(record.version_ids)
        with patch.object(
            type(self.env["dms.file"]),
            "_clamav_scan",
            return_value="Eicar-Test-Signature",
        ):
            with self.assertRaises(ValidationError):
                record.write({"content": base64.b64encode(b"infected")})
        record.invalidate_recordset()
        self.assertEqual(
            len(record.version_ids),
            before,
            "a rejected write must not create a version",
        )

    def test_fail_open_when_clamd_unavailable(self):
        """clamd down means store and warn, not block (task 5.1)."""
        with patch(
            "odoo.addons.dms_clamav.models.dms_file.DmsFile._clamav_config",
            return_value=("127.0.0.1", 1),  # nothing listens on port 1
        ):
            record = self._make_file(b"clean")
        self.assertTrue(record.id, "fail-open must store the file")

    def test_disabled_skips_scan(self):
        """Turning the scan off skips it entirely."""
        self.env["ir.config_parameter"].sudo().set_param(
            "dms_clamav.enabled", "False"
        )
        with patch.object(
            type(self.env["dms.file"]),
            "_clamav_scan",
            side_effect=AssertionError("scan must not run"),
        ):
            record = self._make_file()
        self.assertTrue(record.id)
