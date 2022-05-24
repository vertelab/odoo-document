# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Project(models.Model):
    _inherit = "project.project"


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

    def dms_tree_view(self):
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
            action['view_mode'] = 'kanban, form'
            action['binding_view_types'] = 'kanban, form'
            return action

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

    def dms_tree_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'project.task'),
                ('res_id', '=', self.id)
            ])
            action['view_mode'] = 'kanban, form'
            action['binding_view_types'] = 'kanban, form'
            return action
