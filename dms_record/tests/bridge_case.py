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
"""Shared test base for the ``dms_*`` bridges.

A bridge test only has to declare three things::

    from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase

    @tagged("post_install", "-at_install")
    class TestDmsSaleOrder(DmsBridgeCase):
        model = "sale.order"
        access_mode = "inherit"
        storage_xmlid = "dms_sale_order.sale_order_dms_storage"

        def _create_record(self):
            return self.env["sale.order"].create({"partner_id": ...})

The base class then checks the contract every bridge must satisfy: the
directory exists, it is linked by ``res_model``/``res_id``, it sits under the
declared storage's root, files inherit the link, ``doc_count`` counts them,
the access mode matches the storage, and ``_dms_ensure_directory`` is
idempotent.
"""

import base64
import uuid

from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


class DmsBridgeCase(BaseCommon):
    """Contract test for one ``dms_*`` bridge.

    ``allow_inherited_tests_method`` is required: Odoo's test loader only
    collects ``test_*`` methods defined in the class's own ``__dict__``, so
    without it every bridge subclass would report zero tests.
    """

    allow_inherited_tests_method = True

    #: The model the bridge extends.
    model = None
    #: The access mode the bridge declares.
    access_mode = None
    #: XML id of the storage the bridge declares.
    storage_xmlid = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.model is None or cls.access_mode is None or not cls.storage_xmlid:
            raise NotImplementedError(
                f"{cls.__name__} must declare model, access_mode and storage_xmlid"
            )
        cls.record_model = cls.env[cls.model]
        cls.directory_model = cls.env["dms.directory"]
        cls.file_model = cls.env["dms.file"]
        cls.storage = cls.env.ref(cls.storage_xmlid)

    # ------------------------------------------------------------------
    # Helpers a bridge may override
    # ------------------------------------------------------------------
    def _create_record(self):
        """Create one record of the bridged model."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement _create_record()"
        )

    def _create_file(self, directory, name=None):
        return self.file_model.create(
            {
                "name": name or f"{uuid.uuid4().hex}.txt",
                "directory_id": directory.id,
                "content": base64.b64encode(b"\xff data"),
            }
        )

    # ------------------------------------------------------------------
    # The contract
    # ------------------------------------------------------------------
    def test_bridge_declares_an_access_mode(self):
        self.assertIn(
            self.record_model._dms_access_mode,
            ("inherit", "team", "owner"),
            f"{self.model} must declare a known _dms_access_mode",
        )
        self.assertEqual(self.record_model._dms_access_mode, self.access_mode)

    def test_bridge_declares_a_storage(self):
        self.assertEqual(self.record_model._dms_storage_xmlid, self.storage_xmlid)

    def test_access_mode_matches_the_storage(self):
        """The mixin raises UserError on a mismatch; this asserts the pairing."""
        record = self._create_record()
        # _dms_validate_access_mode runs during directory creation, so a
        # successful create already proves the pairing. Assert the storage
        # properties the mode depends on, so a future edit to the data file
        # fails here rather than at runtime.
        if self.access_mode == "inherit":
            self.assertEqual(self.storage.save_type, "attachment")
            self.assertTrue(self.storage.inherit_access_from_parent_record)
        elif self.access_mode == "owner":
            self.assertNotEqual(self.storage.save_type, "attachment")
        self.assertTrue(record.dms_directory_id)

    def test_directory_is_created_with_the_record(self):
        record = self._create_record()
        self.assertTrue(record.dms_directory_id)
        self.assertEqual(record.dms_directory_id.res_model, self.model)
        self.assertEqual(record.dms_directory_id.res_id, record.id)

    def test_directory_sits_under_the_storage_root(self):
        record = self._create_record()
        directory = record.dms_directory_id
        self.assertFalse(directory.is_root_directory)
        self.assertTrue(directory.parent_id.is_root_directory)
        self.assertEqual(directory.storage_id, self.storage)

    def test_ensure_directory_is_idempotent(self):
        record = self._create_record()
        first = record._dms_ensure_directory()
        second = record._dms_ensure_directory()
        self.assertEqual(first, second)
        self.assertEqual(
            self.directory_model.search_count(
                [("res_model", "=", self.model), ("res_id", "=", record.id)]
            ),
            1,
        )

    def test_file_inherits_the_record_link(self):
        record = self._create_record()
        file_ = self._create_file(record.dms_directory_id)
        self.assertEqual(file_.res_model, self.model)
        self.assertEqual(file_.res_id, record.id)

    def test_doc_count_counts_the_directory(self):
        record = self._create_record()
        self._create_file(record.dms_directory_id)
        record.invalidate_recordset(["doc_count"])
        self.assertEqual(record.doc_count, 1)

    def test_action_opens_the_records_files(self):
        record = self._create_record()
        action = record.action_open_dms_files()
        self.assertEqual(action["res_model"], "dms.file")
        self.assertIn(
            ("res_id", "=", record.id),
            [tuple(leaf) for leaf in action["domain"] if isinstance(leaf, tuple)],
        )

    def test_skip_context_creates_no_directory(self):
        record = self.record_model.with_context(
            skip_dms_record_mixin=True
        ).create(self._create_record_vals())
        self.assertFalse(record.dms_directory_id)

    def _create_record_vals(self):
        """Vals for ``_create_record`` — override when the skip test is wanted."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement _create_record_vals() to test "
            "the skip context"
        )
