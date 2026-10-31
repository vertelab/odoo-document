# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDmsOcaFixes(TransactionCase):
    """The three fixes that used to be source patches."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage = cls.env["dms.storage"].create(
            {"name": "OCA Fixes Storage", "save_type": "database"}
        )
        cls.root = cls.env["dms.directory"].create(
            {
                "name": "OCA Fixes Root",
                "storage_id": cls.storage.id,
                "is_root_directory": True,
            }
        )

    def test_duplicate_name_rejected_by_default(self):
        """Without the context flag a duplicate name still raises."""
        self.env["dms.directory"].create(
            {
                "name": "dup",
                "storage_id": self.storage.id,
                "parent_id": self.root.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["dms.directory"].create(
                {
                    "name": "dup",
                    "storage_id": self.storage.id,
                    "parent_id": self.root.id,
                }
            )

    def test_check_name_false_allows_duplicate(self):
        """check_name=False must skip the duplicate check too (fix 1).

        This is the whole point of the flag: a caller that creates a
        colliding name on purpose should not be blocked by the check it
        explicitly opted out of.
        """
        self.env["dms.directory"].create(
            {
                "name": "dup",
                "storage_id": self.storage.id,
                "parent_id": self.root.id,
            }
        )
        second = (
            self.env["dms.directory"]
            .with_context(check_name=False)
            .create(
                {
                    "name": "dup",
                    "storage_id": self.storage.id,
                    "parent_id": self.root.id,
                }
            )
        )
        self.assertTrue(second.id)

    def test_invalid_name_still_rejected_without_flag(self):
        """The character check keeps working."""
        with self.assertRaises(ValidationError):
            self.env["dms.directory"].create(
                {
                    "name": "bad/name",
                    "storage_id": self.storage.id,
                    "parent_id": self.root.id,
                }
            )

    def test_unique_name_suffixes_on_collision(self):
        """unique_name appends a suffix instead of returning a duplicate."""
        from odoo.addons.dms.tools.file import unique_name

        self.assertEqual(unique_name("Anna", []), "Anna")
        self.assertNotEqual(unique_name("Anna", ["Anna"]), "Anna")
