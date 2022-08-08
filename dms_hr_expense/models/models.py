# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Event(models.Model):
    _inherit = "hr.expense"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for expense in self:
            expense.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'hr.expense'), ('res_id', '=', expense.id),
            ])

    def dms_tree_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'hr.expense'),
                ('res_id', 'in', self.ids),        
            ])
            return action
