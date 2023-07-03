# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class Project(models.Model):
    _inherit = "project.project"

    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Number of documents attached")

    directory_count = fields.Integer(compute='_compute_linked_directories_count', string="Number of Directories")

    def _set_project_parent_dir(self):
        for rec in self:
            dms_directory_id = self.env["dms.directory"].search([
                ("name", "=", rec.name),
                ("is_root_directory", "=", False),
                ("res_id", "=", rec.id),
                ("model_id.model", "=", "project.project"),
            ], limit=1)
            if dms_directory_id:
                rec.has_project_parent_dir = True
            else:
                rec.has_project_parent_dir = False

    has_project_parent_dir = fields.Boolean(string="Has Parent Dir", compute=_set_project_parent_dir)

    def create_parent_dir(self):
        self.env["dms.directory"].create({
            'name': self.name,
            'parent_id': self.env["dms.directory"].search([
                ('model_id.model', '=', 'project.project'), ("res_id", "=", False)], limit=1).id,
            'model_id': self.env["ir.model"].search([
                ('model', '=', 'project.project')
            ], limit=1).id,
            'record_ref': "{},{}".format("project.project", self.id),
            'res_model': "project.project",
            'res_id': self.id,
        })

    def _compute_linked_directories_count(self):
        directory_id = self.env['dms.directory']
        for project in self:
            project.directory_count = directory_id.search_count([
                ('model_id.model', '=', 'project.project'), ('res_id', '=', project.id),
            ])

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for project in self:
            project.doc_count = Document.search_count([
                '|',
                '&',
                ('res_model', '=', 'project.project'), ('res_id', '=', project.id),
                '&',
                ('res_model', '=', 'project.task'), ('res_id', 'in', project.task_ids.ids)
            ])

    def dms_kanban_view(self):
        kanban_view = self.env.ref('dms.view_dms_file_kanban')
        form_view = self.env.ref('dms_project.view_dms_file_form_from_project')
        domain = [
            '|',
            '&',
            ('res_model', '=', 'project.project'),
            ('res_id', 'in', self.ids),
            '&',
            ('res_model', '=', 'project.task'),
            ('res_id', 'in', self.task_ids.ids),
        ]

        context_vals = {
            'default_directory_id': self.env["dms.directory"].search([("name", "=", self.name)]).id,
            'related_dir_ids': self.env["dms.directory"].search([
                ("model_id", "=", "project.project"),
                ("res_id", "=", self.id),
            ]).ids
        }

        return {
            'name': _('Files'),
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,tree,form',
            'res_model': 'dms.file',
            'views': [(kanban_view.id, 'kanban'), (False, 'tree'), (form_view.id, 'form')],
            'view_id': kanban_view.id,
            'target': 'self',
            'domain': domain,
            'context': context_vals
        }

    def kanban_view_directory(self):
        kanban_view = self.env.ref('dms.view_dms_directory_kanban')
        form_view = self.env.ref('dms_project.view_dms_directory_form_from_project')
        dms_directory_id = self.env["dms.directory"].search([("name", "=", self.name)])
        if self.directory_count == 0:
            context_vals = {
                'default_parent_id': self.env["dms.directory"].search([
                    ('model_id.model', '=', 'project.project'), ("res_id", "=", False)
                ], limit=1).id,
                'default_model_id': self.env["ir.model"].search([
                    ('model', '=', 'project.project')
                ], limit=1).id,
                'default_record_ref': "{},{}".format("project.project", self.id),
                'default_res_model': "project.project",
                'special_res_id': self.id,
                'special': True,
                'related_dir_ids': self.env["dms.directory"].search([
                    ("model_id", "=", "project.project"),
                    ("res_id", "=", self.id),
                ]).ids
            }
        else:
            context_vals = {
                'default_parent_id': dms_directory_id.id,
                'default_model_id': dms_directory_id.model_id.id,
                'related_dir_ids': self.env["dms.directory"].search([
                    ("model_id", "=", "project.project"),
                    ("res_id", "=", self.id),
                ]).ids

            }
        return {
            'name': _('Directories'),
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,tree,form',
            'res_model': 'dms.directory',
            'views': [(kanban_view.id, 'kanban'), (False, 'tree'), (form_view.id, 'form')],
            'view_id': kanban_view.id,
            'target': 'self',
            'domain': [
                ('model_id.model', '=', 'project.project'),
                ('res_id', 'in', self.ids)
            ],
            'context': context_vals
        }


class Project(models.Model):
    _inherit = "project.task"

    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Number of documents attached")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for task in self:
            task.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'project.task'), ('res_id', '=', task.id)
            ])

    def dms_kanban_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'project.task'),
                ('res_id', '=', self.id)
            ])
            return action
