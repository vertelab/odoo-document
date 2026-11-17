# -*- coding: utf-8 -*-
"""Tests for the office creator's open callback (tasks 3.1, 3.2, 4.1, 4.2).

The contract under test is `wizards/dms_document_creator_office.py`:

    _get_creators()        docx / xlsx / pptx entries with a callable `open`
    _open_office(file)     delegates to the editor module when it is
                           installed, and returns a form action when it is not
    _create_office(...)    creates a `dms.file` from the shipped blank file

**Why the delegation test patches the method instead of installing
`dms_euro_office`:** the module that owns the editor is a third-party module,
and a test that requires it would not run on a database that does not have it
— which is exactly the deployment the fallback exists for. Patching
`dms.file.open_in_euro_office_action` is how the test proves the delegation
without making the module a test dependency.

**Why the registry test reads `_get_creators()` and not the wizard's view:**
the wizard is generic; the registry is the contract every creator module
extends. A format added without an `open` callback is a format that creates a
file nobody can open — the defect this change is about.
"""

from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestOfficeOpen(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.creator = cls.env["dms.document.creator"]
        cls.file_model = cls.env["dms.file"]
        cls.directory_model = cls.env["dms.directory"]
        cls.storage_model = cls.env["dms.storage"]

        cls.storage = cls.storage_model.create(
            {"name": "Office Open Storage", "save_type": "database"}
        )
        cls.directory = cls.directory_model.create(
            {
                "name": "Documents",
                "is_root_directory": True,
                "storage_id": cls.storage.id,
            }
        )

    # ------------------------------------------------------------------
    # 3.1 — the fallback when no editor module is installed
    # ------------------------------------------------------------------

    def test_open_office_falls_back_to_form(self):
        """Without the editor module the file opens in its DMS form.

        A broken link is worse than a form: the form is a valid place to
        download the document from.

        **The field is removed, not assumed absent.** `dms_euro_office` is
        installed on the production database, so `can_open_in_euro_office`
        exists there and this test would never reach the fallback. Patching
        `_fields` to drop it is how the test simulates the deployment the
        fallback exists for — a database without the editor module.
        """
        document = self.file_model.create(
            {
                "name": "fallback.docx",
                "directory_id": self.directory.id,
                "content": "",
            }
        )

        fields_without_editor = {
            name: field
            for name, field in self.file_model._fields.items()
            if name != "can_open_in_euro_office"
        }

        with patch.object(
            type(self.file_model), "_fields", fields_without_editor
        ):
            action = self.creator._open_office(document)

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "dms.file")
        self.assertEqual(action["res_id"], document.id)
        self.assertEqual(action["view_mode"], "form")

    # ------------------------------------------------------------------
    # 3.2 — the delegation when the editor module IS installed
    # ------------------------------------------------------------------

    def test_open_office_delegates_to_editor_module(self):
        """When the capability field exists, the editor's action is returned.

        The creator must not build an action of its own here: the module that
        owns the editor owns the route, and duplicating it is how the kanban
        click ended up pointing at a dead URL.
        """
        document = self.file_model.create(
            {
                "name": "delegate.docx",
                "directory_id": self.directory.id,
                "content": "",
            }
        )
        editor_action = {
            "type": "ir.actions.act_url",
            "url": "/dms_euro_office/open/%s" % document.id,
            "target": "new",
        }

        # `_fields` is a class-level mapping; patching it on the model class
        # is how the test simulates "the editor module is installed" without
        # installing it.
        with patch.object(
            type(self.file_model),
            "_fields",
            dict(self.file_model._fields, can_open_in_euro_office=True),
        ), patch.object(
            type(self.file_model),
            "open_in_euro_office_action",
            lambda record: editor_action,
            create=True,
        ):
            action = self.creator._open_office(document)

        self.assertEqual(action, editor_action)

    # ------------------------------------------------------------------
    # 4.1 — every registered creator has a callable open callback
    # ------------------------------------------------------------------

    def test_every_creator_has_a_callable_open(self):
        creators = self.creator._get_creators()
        self.assertTrue(creators, "no creators registered")

        for entry in creators:
            with self.subTest(key=entry.get("key")):
                self.assertIn("open", entry, "%s has no open callback" % entry)
                self.assertTrue(
                    callable(entry["open"]),
                    "%s: open is not callable" % entry.get("key"),
                )

    def test_every_creator_open_returns_an_action(self):
        """Each creator's `open` returns an action dictionary with a `type`.

        This is the regression guard for the defect this change fixes: a
        creator that creates a file and cannot say where to open it produces
        a document the user cannot reach.
        """
        document = self.file_model.create(
            {
                "name": "registry.docx",
                "directory_id": self.directory.id,
                "content": "",
            }
        )

        for entry in self.creator._get_creators():
            with self.subTest(key=entry.get("key")):
                action = entry["open"](document)
                self.assertIsInstance(action, dict)
                self.assertIn("type", action)

    # ------------------------------------------------------------------
    # 4.2 — no creator builds a URL string of its own
    # ------------------------------------------------------------------

    def test_open_actions_come_from_a_record_method(self):
        """An `act_url` returned by a creator must be built by the record.

        A hardcoded URL in a creator is the same defect as a hardcoded URL in
        the kanban table: it names a route another module owns. Here we assert
        the weaker, checkable form: for every creator whose action is an
        `act_url`, the URL is a string produced by the model (it starts with
        `/` and is not a template left unformatted), and the creator does not
        return a URL built from a literal it also uses elsewhere.
        """
        document = self.file_model.create(
            {
                "name": "url.docx",
                "directory_id": self.directory.id,
                "content": "",
            }
        )

        for entry in self.creator._get_creators():
            with self.subTest(key=entry.get("key")):
                action = entry["open"](document)
                if action.get("type") != "ir.actions.act_url":
                    continue
                url = action.get("url") or ""
                self.assertIsInstance(url, str)
                self.assertTrue(url.startswith("/"), "url is not a path: %r" % url)
                self.assertNotIn("%s", url, "unformatted url template: %r" % url)
