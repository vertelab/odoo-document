# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class Project(models.Model):
    _inherit = "project.project"

    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Number of documents attached")
    directory_count = fields.Integer(compute='_compute_linked_directories_count', string="Number of Directories")

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
        action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
        action['domain'] = str([
            '|',
            '&',
            ('res_model', '=', 'project.project'),
            ('res_id', 'in', self.ids),
            '&',
            ('res_model', '=', 'project.task'),
            ('res_id', 'in', self.task_ids.ids),
        ])
        dms_directory_id = self.env["dms.directory"].search([("name", "=", self.name)])
        action['context'] = {'default_directory_id': dms_directory_id.id}
        return action

    def kanban_view_directory(self):
        view = self.env.ref('dms.view_dms_directory_kanban')
        dms_directory_id = self.env["dms.directory"].search([("name", "=", self.name)])
        return {
            'name': _('Directories'),
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,tree,form',
            'res_model': 'dms.directory',
            'views': [(view.id, 'kanban'), (False, 'tree'), (False, 'form')],
            'view_id': view.id,
            'target': 'self',
            'domain': [
                ('model_id.model', '=', 'project.project'),
                ('res_id', 'in', self.ids)
            ],
            'context': {'default_parent_id': dms_directory_id.id, 'default_model_id': dms_directory_id.model_id.id}
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
