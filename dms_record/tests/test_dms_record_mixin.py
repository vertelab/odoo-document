# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2022- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
##############################################################################

import base64
import uuid
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


class DmsRecordMixinBaseCase(BaseCommon):
    """The test models live in ``models/dms_record_test_models.py``.

    Their storages are created here rather than shipped as data: a test that
    depends on ``demo`` being installed is a test that silently passes
    without exercising anything.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.directory_model = cls.env["dms.directory"]
        cls.file_model = cls.env["dms.file"]
        cls.storage_model = cls.env["dms.storage"]
        cls.access_group_model = cls.env["dms.access.group"]
        cls.inherit_model = cls.env["dms.record.test.inherit"]
        cls.team_model = cls.env["dms.record.test.team"]
        cls.owner_model = cls.env["dms.record.test.owner"]
        cls.no_storage_model = cls.env["dms.record.test.no.storage"]
        cls.bad_mode_model = cls.env["dms.record.test.bad.mode"]

        cls.access_group = cls.access_group_model.create(
            {
                "name": "DMS Record Test Team",
                "perm_create": True,
                "perm_write": True,
                "perm_unlink": True,
            }
        )

        cls.storage_inherit = cls._make_storage(
            "dms_record.test_storage_inherit",
            cls.inherit_model,
            save_type="attachment",
            inherit_access=True,
        )
        cls.storage_team = cls._make_storage(
            "dms_record.test_storage_team",
            cls.team_model,
            save_type="attachment",
            inherit_access=False,
        )
        cls.storage_owner = cls._make_storage(
            "dms_record.test_storage_owner",
            cls.owner_model,
            save_type="file",
            inherit_access=False,
        )

    @classmethod
    def _make_storage(cls, xmlid, model, save_type, inherit_access):
        """Create a storage plus its root directory and expose it as ``xmlid``.

        The mixin resolves ``_dms_storage_xmlid`` through ``env.ref``, so the
        test has to register an ir.model.data row rather than set an
        attribute on the class.
        """
        # model_ids only on an attachment storage. dms_field rejects a
        # non-attachment storage that declares model_ids while its root
        # directory has no res_id, and a root directory never has one. The
        # owner mode resolves nothing from a model, so it needs neither.
        is_attachment = save_type == "attachment"
        storage = cls.storage_model.create(
            {
                "name": xmlid,
                "save_type": save_type,
                "inherit_access_from_parent_record": inherit_access,
                "model_ids": [(6, 0, [cls.env["ir.model"]._get_id(model._name)])]
                if is_attachment
                else [(5, 0, 0)],
            }
        )
        cls.directory_model.create(
            {
                "name": f"{xmlid} root",
                "is_root_directory": True,
                "storage_id": storage.id,
                "model_id": cls.env["ir.model"]._get_id(model._name)
                if is_attachment
                else False,
            }
        )
        cls.env["ir.model.data"].create(
            {
                "module": "dms_record",
                "name": xmlid.split(".", 1)[1],
                "model": "dms.storage",
                "res_id": storage.id,
                "noupdate": True,
            }
        )
        return storage

    @classmethod
    def _create_file(cls, directory, name=None, content=b"\xff data"):
        return cls.file_model.create(
            {
                "name": name or f"{uuid.uuid4().hex}.txt",
                "directory_id": directory.id,
                "content": base64.b64encode(content),
            }
        )


@tagged("post_install", "-at_install")
class TestDmsRecordMixin(DmsRecordMixinBaseCase):
    # ------------------------------------------------------------------
    # Requirement: One directory per record
    # ------------------------------------------------------------------
    def test_directory_created_with_record(self):
        record = self.inherit_model.create({"name": "Alpha"})
        directory = self.directory_model.search(
            [
                ("res_model", "=", record._name),
                ("res_id", "=", record.id),
            ]
        )
        self.assertEqual(len(directory), 1)
        self.assertEqual(directory.res_model, record._name)
        self.assertEqual(directory.res_id, record.id)

    def test_directory_reachable_from_record(self):
        record = self.inherit_model.create({"name": "Alpha"})
        self.assertTrue(record.dms_directory_id)
        self.assertEqual(record.dms_directory_id.res_id, record.id)

    def test_ensure_directory_is_idempotent(self):
        record = self.inherit_model.create({"name": "Alpha"})
        first = record._dms_ensure_directory()
        second = record._dms_ensure_directory()
        self.assertEqual(first, second)
        self.assertEqual(
            self.directory_model.search_count(
                [("res_model", "=", record._name), ("res_id", "=", record.id)]
            ),
            1,
        )

    # ------------------------------------------------------------------
    # Requirement: The storage is declared, never guessed
    # ------------------------------------------------------------------
    def test_missing_storage_xmlid_raises(self):
        record = self.no_storage_model.create({"name": "No storage"})
        with self.assertRaises(UserError):
            record._dms_get_storage()

    def test_unresolvable_storage_xmlid_raises(self):
        record = self.inherit_model.create({"name": "Alpha"})
        # Odoo asserts after the suite that a model carries no unexpected
        # attributes, so the class attribute is patched and restored rather
        # than left behind.
        with patch.object(
            type(record), "_dms_storage_xmlid", "dms_record.does_not_exist"
        ):
            with self.assertRaises(UserError):
                record._dms_get_storage()

    def test_storage_is_not_created_on_the_fly(self):
        record = self.inherit_model.create({"name": "Alpha"})
        before = self.storage_model.search_count([])
        record._dms_get_storage()
        self.assertEqual(self.storage_model.search_count([]), before)

    # ------------------------------------------------------------------
    # Requirement: The directory is placed under the storage's root directory
    # ------------------------------------------------------------------
    def test_directory_parent_is_root_directory(self):
        record = self.inherit_model.create({"name": "Alpha"})
        directory = record.dms_directory_id
        self.assertFalse(directory.is_root_directory)
        self.assertTrue(directory.parent_id)
        self.assertTrue(directory.parent_id.is_root_directory)
        self.assertEqual(directory.parent_id.storage_id, directory.storage_id)

    def test_storage_without_root_directory_raises(self):
        record = self.inherit_model.create({"name": "Alpha"})
        storage = record._dms_get_storage()
        storage.root_directory_ids.unlink()
        with self.assertRaises(UserError):
            record._dms_get_root_directory(storage)

    # ------------------------------------------------------------------
    # Requirement: Access mode is declared per bridge
    # ------------------------------------------------------------------
    def test_inherit_requires_attachment_storage(self):
        record = self.inherit_model.create({"name": "Alpha"})
        storage = record._dms_get_storage()
        storage.save_type = "file"
        with self.assertRaises(UserError):
            record._dms_validate_access_mode(storage)

    def test_inherit_requires_inherit_flag(self):
        record = self.inherit_model.create({"name": "Alpha"})
        storage = record._dms_get_storage()
        storage.inherit_access_from_parent_record = False
        with self.assertRaises(UserError):
            record._dms_validate_access_mode(storage)

    def test_owner_requires_non_attachment_storage(self):
        record = self.owner_model.create({"name": "Alpha"})
        storage = record._dms_get_storage()
        self.assertEqual(storage.save_type, "file")
        storage.save_type = "attachment"
        with self.assertRaises(UserError):
            record._dms_validate_access_mode(storage)

    def test_team_sets_access_group(self):
        record = self.team_model.create({"name": "Alpha"})
        directory = record.dms_directory_id
        self.assertIn(self.access_group, directory.group_ids)
        self.assertFalse(directory.inherit_group_ids)

    def test_inherit_leaves_directory_acl_free(self):
        record = self.inherit_model.create({"name": "Alpha"})
        self.assertFalse(record.dms_directory_id.group_ids)

    def test_unknown_access_mode_raises(self):
        record = self.bad_mode_model.create({"name": "Alpha"})
        with self.assertRaises(UserError):
            record._dms_validate_access_mode(record._dms_get_storage())

    # ------------------------------------------------------------------
    # Requirement: The directory name is cosmetic
    # ------------------------------------------------------------------
    def test_rename_follows_the_record(self):
        record = self.inherit_model.create({"name": "Alpha"})
        directory = record.dms_directory_id
        self.assertEqual(directory.name, "Alpha")
        record.write({"name": "Beta"})
        self.assertEqual(directory.name, "Beta")

    def test_hand_edited_name_is_left_alone(self):
        record = self.inherit_model.create({"name": "Alpha"})
        directory = record.dms_directory_id
        directory.write({"name": "Renamed by hand"})
        record.write({"name": "Beta"})
        self.assertEqual(directory.name, "Renamed by hand")

    def test_two_records_with_same_name(self):
        first = self.inherit_model.create({"name": "Same"})
        second = self.inherit_model.create({"name": "Same"})
        self.assertNotEqual(first.dms_directory_id, second.dms_directory_id)
        self.assertEqual(first.dms_directory_id.res_id, first.id)
        self.assertEqual(second.dms_directory_id.res_id, second.id)
        # Sibling directories must have unique names, so the second one is
        # disambiguated. Without this both records would try to claim "Same"
        # and the second directory would fail to be created.
        self.assertNotEqual(
            first.dms_directory_id.name, second.dms_directory_id.name
        )

    def test_lookup_never_uses_the_name(self):
        record = self.inherit_model.create({"name": "Alpha"})
        directory = record.dms_directory_id
        directory.write({"name": "Something else entirely"})
        self.assertEqual(record._dms_find_directory(), directory)

    # ------------------------------------------------------------------
    # Requirement: Files inherit the record link
    # ------------------------------------------------------------------
    def test_file_inherits_record_link(self):
        record = self.inherit_model.create({"name": "Alpha"})
        file_ = self._create_file(record.dms_directory_id)
        self.assertEqual(file_.res_model, record._name)
        self.assertEqual(file_.res_id, record.id)

    # ------------------------------------------------------------------
    # Requirement: Generic document count
    # ------------------------------------------------------------------
    def test_doc_count_counts_subdirectories(self):
        record = self.inherit_model.create({"name": "Alpha"})
        directory = record.dms_directory_id
        # An attachment storage requires model_id and res_id on every
        # non-root directory, so the subdirectory points at the same record.
        subdirectory = self.directory_model.create(
            {
                "name": "Sub",
                "parent_id": directory.id,
                "storage_id": directory.storage_id.id,
                "res_model": record._name,
                "res_id": record.id,
            }
        )
        self._create_file(directory)
        self._create_file(subdirectory)
        self._create_file(subdirectory)
        record.invalidate_recordset(["doc_count"])
        self.assertEqual(record.doc_count, 3)

    def test_doc_count_does_not_count_other_records(self):
        first = self.inherit_model.create({"name": "Alpha"})
        second = self.inherit_model.create({"name": "Beta"})
        self._create_file(first.dms_directory_id)
        self._create_file(second.dms_directory_id)
        first.invalidate_recordset(["doc_count"])
        second.invalidate_recordset(["doc_count"])
        self.assertEqual(first.doc_count, 1)
        self.assertEqual(second.doc_count, 1)

    # ------------------------------------------------------------------
    # Context escape hatch
    # ------------------------------------------------------------------
    def test_skip_context_creates_no_directory(self):
        record = self.inherit_model.with_context(
            skip_dms_record_mixin=True
        ).create({"name": "Alpha"})
        self.assertFalse(
            self.directory_model.search(
                [("res_model", "=", record._name), ("res_id", "=", record.id)]
            )
        )
