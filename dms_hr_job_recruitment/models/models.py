# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Job(models.Model):
    _inherit = "hr.job"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for job in self:
            job.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'hr.job'), ('res_id', '=', job.id),
            ])

    def dms_kanban_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'hr.job'),
                ('res_id', 'in', self.ids),
                
            ])
            return action

class Applicant(models.Model):
    _inherit = "hr.applicant"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for applicant in self:
            applicant.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'hr.applicant'), ('res_id', '=', applicant.id),
            ])

    def dms_kanban_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'hr.applicant'),
                ('res_id', 'in', self.ids),
                
            ])
            return action

