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
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class Project(models.Model):
    _name = "project.project"
    _inherit = ["project.project", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_project.project_documents_storage"
    _dms_access_mode = "inherit"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def dms_kanban_view(self):
        """Open the documents of this project.

        The directory is resolved through ``dms_directory_id``, which is
        keyed on ``res_model``/``res_id``. The previous implementation looked
        it up by ``name``, which orphaned the directory on rename, collided
        for two projects with the same name, and raised ``Expected
        singleton`` when the search matched more than one row.
        """
        self.ensure_one()
        kanban_view = self.env.ref("dms.view_dms_file_kanban")
        form_view = self.env.ref("dms_project.view_dms_file_form_from_project")
        domain = [
            "|",
            "&",
            ("res_model", "=", "project.project"),
            ("res_id", "=", self.id),
            "&",
            ("res_model", "=", "project.task"),
            ("res_id", "in", self.task_ids.ids),
        ]
        context_vals = {
            "default_directory_id": self.dms_directory_id.id,
            "related_dir_ids": self.dms_directory_id.ids,
        }
        return {
            "name": _("Files"),
            "type": "ir.actions.act_window",
            "view_mode": "kanban,list,form",
            "res_model": "dms.file",
            "views": [
                (kanban_view.id, "kanban"),
                (False, "list"),
                (form_view.id, "form"),
            ],
            "view_id": kanban_view.id,
            "target": "self",
            "domain": domain,
            "context": context_vals,
        }

    def kanban_view_directory(self):
        """Open the directories of this project."""
        self.ensure_one()
        kanban_view = self.env.ref("dms.view_dms_directory_kanban")
        form_view = self.env.ref("dms_project.view_dms_directory_form_from_project")
        context_vals = {
            "default_parent_id": self.dms_directory_id.id,
            "default_model_id": self.dms_directory_id.model_id.id,
            "related_dir_ids": self.dms_directory_id.ids,
        }
        return {
            "name": _("Directories"),
            "type": "ir.actions.act_window",
            "view_mode": "kanban,list,form",
            "res_model": "dms.directory",
            "views": [
                (kanban_view.id, "kanban"),
                (False, "list"),
                (form_view.id, "form"),
            ],
            "view_id": kanban_view.id,
            "target": "self",
            "domain": [
                ("model_id.model", "=", "project.project"),
                ("res_id", "=", self.id),
            ],
            "context": context_vals,
        }

    def _compute_linked_directories_count(self):
        for project in self:
            project.directory_count = self.env["dms.directory"].search_count(
                [
                    ("res_model", "=", "project.project"),
                    ("res_id", "=", project.id),
                ]
            )

    directory_count = fields.Integer(
        compute="_compute_linked_directories_count",
        string="Number of Directories",
    )


class ProjectTask(models.Model):
    _inherit = "project.task"

    def _compute_attached_docs_count(self):
        """Count the files attached to this task.

        Tasks do not get their own directory in this change: they are not a
        ``dms.record.mixin`` model, so there is nothing for the mixin to key
        on. The count is kept as a direct ``res_model``/``res_id`` lookup,
        which is what a task's files carry when they are created inside the
        project's directory tree.
        """
        Document = self.env["dms.file"]
        for task in self:
            task.doc_count = Document.search_count(
                [
                    ("res_model", "=", "project.task"),
                    ("res_id", "=", task.id),
                ]
            )

    doc_count = fields.Integer(
        compute="_compute_attached_docs_count",
        string="Number of documents attached",
    )

    def dms_kanban_view(self):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "dms.action_dms_file"
        )
        action["domain"] = [
            ("res_model", "=", "project.task"),
            ("res_id", "=", self.id),
        ]
        return action
