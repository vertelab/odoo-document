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

from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestDmsProject(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project_model = cls.env["project.project"]
        cls.directory_model = cls.env["dms.directory"]
        cls.file_model = cls.env["dms.file"]

    def _create_file(self, directory, name=None):
        return self.file_model.create(
            {
                "name": name or f"{uuid.uuid4().hex}.txt",
                "directory_id": directory.id,
                "content": base64.b64encode(b"\xff data"),
            }
        )

    # ------------------------------------------------------------------
    # The contract from specs/dms-record-bridge
    # ------------------------------------------------------------------
    def test_directory_created_with_project(self):
        project = self.project_model.create({"name": "Alpha"})
        self.assertTrue(project.dms_directory_id)
        self.assertEqual(project.dms_directory_id.res_model, "project.project")
        self.assertEqual(project.dms_directory_id.res_id, project.id)

    def test_directory_parent_is_the_storage_root(self):
        project = self.project_model.create({"name": "Alpha"})
        directory = project.dms_directory_id
        self.assertFalse(directory.is_root_directory)
        self.assertTrue(directory.parent_id.is_root_directory)
        self.assertEqual(
            directory.storage_id,
            self.env.ref("dms_project.project_documents_storage"),
        )

    def test_ensure_directory_is_idempotent(self):
        project = self.project_model.create({"name": "Alpha"})
        first = project._dms_ensure_directory()
        second = project._dms_ensure_directory()
        self.assertEqual(first, second)
        self.assertEqual(
            self.directory_model.search_count(
                [("res_model", "=", "project.project"), ("res_id", "=", project.id)]
            ),
            1,
        )

    def test_file_inherits_the_project_link(self):
        project = self.project_model.create({"name": "Alpha"})
        file_ = self._create_file(project.dms_directory_id)
        self.assertEqual(file_.res_model, "project.project")
        self.assertEqual(file_.res_id, project.id)

    def test_doc_count_counts_the_project_directory(self):
        project = self.project_model.create({"name": "Alpha"})
        self._create_file(project.dms_directory_id)
        project.invalidate_recordset(["doc_count"])
        self.assertEqual(project.doc_count, 1)

    # ------------------------------------------------------------------
    # The defects this change fixes
    # ------------------------------------------------------------------
    def test_two_projects_with_the_same_name_get_separate_directories(self):
        first = self.project_model.create({"name": "Same"})
        second = self.project_model.create({"name": "Same"})
        self.assertNotEqual(first.dms_directory_id, second.dms_directory_id)
        self.assertEqual(first.dms_directory_id.res_id, first.id)
        self.assertEqual(second.dms_directory_id.res_id, second.id)

    def test_rename_follows_the_directory(self):
        project = self.project_model.create({"name": "Alpha"})
        directory = project.dms_directory_id
        self.assertEqual(directory.name, "Alpha")
        project.write({"name": "Beta"})
        self.assertEqual(directory.name, "Beta")

    def test_kanban_view_uses_the_directory_id(self):
        project = self.project_model.create({"name": "Alpha"})
        action = project.dms_kanban_view()
        self.assertEqual(
            action["context"]["default_directory_id"], project.dms_directory_id.id
        )
        self.assertIn(
            ("res_id", "=", project.id),
            [tuple(leaf) for leaf in action["domain"] if isinstance(leaf, tuple)],
        )

    def test_kanban_view_directory_uses_the_directory_id(self):
        project = self.project_model.create({"name": "Alpha"})
        action = project.kanban_view_directory()
        self.assertEqual(
            action["context"]["default_parent_id"], project.dms_directory_id.id
        )

    # ------------------------------------------------------------------
    # The post-init hook
    # ------------------------------------------------------------------
    def test_post_init_hook_creates_missing_directories(self):
        from odoo.addons.dms_project.hooks import post_init_hook

        project = self.project_model.create({"name": "Alpha"})
        project.dms_directory_id.unlink()
        project.invalidate_recordset(["dms_directory_id"])
        self.assertFalse(project.dms_directory_id)

        post_init_hook(self.env)

        project.invalidate_recordset(["dms_directory_id"])
        self.assertTrue(project.dms_directory_id)
        self.assertEqual(project.dms_directory_id.res_id, project.id)
    def test_post_init_hook_is_idempotent(self):
        from odoo.addons.dms_project.hooks import post_init_hook

        project = self.project_model.create({"name": "Alpha"})
        post_init_hook(self.env)
        post_init_hook(self.env)
        self.assertEqual(
            self.directory_model.search_count(
                [("res_model", "=", "project.project"), ("res_id", "=", project.id)]
            ),
            1,
        )

    def test_post_init_hook_adopts_an_orphan_directory(self):
        """A directory left by the old name-based code has no res_id."""
        from odoo.addons.dms_project.hooks import post_init_hook

        project = self.project_model.create({"name": "Alpha"})
        directory = project.dms_directory_id
        # Simulate the old code: directory named after the project, no res_id.
        directory.write({"res_id": False})
        project.invalidate_recordset(["dms_directory_id"])

        post_init_hook(self.env)

        self.assertEqual(directory.res_id, project.id)
        self.assertEqual(
            self.directory_model.search_count(
                [("res_model", "=", "project.project"), ("res_id", "=", project.id)]
            ),
            1,
        )
