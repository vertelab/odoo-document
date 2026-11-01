# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


class _Upload:
    """Minimal stand-in for werkzeug's FileStorage.

    ``pwa_capture_store`` only calls ``.read()`` and reads ``.filename``, so
    the tests do not need a real request to exercise it.
    """

    def __init__(self, filename, payload):
        self.filename = filename
        self._payload = payload

    def read(self):
        return self._payload


@tagged("post_install", "-at_install")
class TestMobileCapture(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage = cls.env["dms.storage"].create({
            "name": "Mobile Test Storage",
            "save_type": "database",
        })
        cls.root = cls.env["dms.directory"].create({
            "name": "Mobile Root",
            "storage_id": cls.storage.id,
            "is_root_directory": True,
        })
        cls.directory = cls.env["dms.directory"].create({
            "name": "Fältfoton",
            "parent_id": cls.root.id,
            "mobile_target": True,
        })

    def test_pwa_app_is_registered(self):
        """Task 4.2: the capture app exists and points at our method."""
        app = self.env["web.pwa.app"].search(
            [("key", "=", "dms-capture")], limit=1)
        self.assertTrue(app, "dms-capture app was not created")
        self.assertTrue(app.capture_enabled)
        self.assertEqual(app.capture_model, "dms.file")
        self.assertEqual(app.capture_method, "pwa_capture_store")
        self.assertEqual(app.start_url, "/dms/mobile")
        self.assertEqual(app.scope, "/dms/")

    def test_capture_stores_file_with_source(self):
        """Task 4.3: one dms.file per upload, flagged as pwa."""
        result = self.env["dms.file"].pwa_capture_store(
            [_Upload("skada.jpg", b"fake jpeg bytes")],
            directory_id=self.directory.id,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["ids"]), 1)
        record = self.env["dms.file"].browse(result["ids"])
        self.assertEqual(record.name, "skada.jpg")
        self.assertEqual(record.directory_id, self.directory)
        self.assertEqual(record.capture_source, "pwa")
        self.assertEqual(
            base64.b64decode(record.content), b"fake jpeg bytes")

    def test_multiple_files_in_one_call(self):
        result = self.env["dms.file"].pwa_capture_store(
            [
                _Upload("a.jpg", b"aaa"),
                _Upload("b.pdf", b"bbb"),
            ],
            directory_id=self.directory.id,
        )
        self.assertEqual(len(result["ids"]), 2)
        self.assertEqual(sorted(result["names"]), ["a.jpg", "b.pdf"])

    def test_empty_upload_is_skipped(self):
        """A zero-byte upload must not create an empty document."""
        result = self.env["dms.file"].pwa_capture_store(
            [_Upload("empty.jpg", b"")],
            directory_id=self.directory.id,
        )
        self.assertEqual(result["ids"], [])

    def test_missing_directory_is_an_error(self):
        with self.assertRaises(UserError):
            self.env["dms.file"].pwa_capture_store(
                [_Upload("x.jpg", b"x")], directory_id=None)

    def test_unknown_directory_is_an_error(self):
        with self.assertRaises(UserError):
            self.env["dms.file"].pwa_capture_store(
                [_Upload("x.jpg", b"x")], directory_id=999999)

    def test_capture_source_defaults_to_manual(self):
        """Task 4.4: a normal upload is not marked as mobile."""
        record = self.env["dms.file"].create({
            "name": "vanlig.txt",
            "directory_id": self.directory.id,
            "content": base64.b64encode(b"x"),
        })
        self.assertEqual(record.capture_source, "manual")

    def test_mobile_target_defaults_to_false(self):
        """Task 4.4: directories are not mobile targets unless asked."""
        self.assertFalse(self.root.mobile_target)
        self.assertTrue(self.directory.mobile_target)

    def test_user_without_create_rights_is_refused(self):
        """Task 5.2: no sudo in the callback, so access rules apply.

        A user who cannot create in the directory must get AccessError
        rather than a file they cannot see.
        """
        internal = self.env.ref("base.group_user")
        # group_ids is not a writable field on create in Odoo 18; groups are
        # assigned through the _group relation after the user exists.
        outsider = self.env["res.users"].create({
            "name": "Outsider",
            "login": "outsider_mobile_test",
        })
        outsider.sudo().write({"groups_id": [(6, 0, [internal.id])]})
        with self.assertRaises(AccessError):
            self.env["dms.file"].with_user(outsider).pwa_capture_store(
                [_Upload("x.jpg", b"x")],
                directory_id=self.directory.id,
            )
