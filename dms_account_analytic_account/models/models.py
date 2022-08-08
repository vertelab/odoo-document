# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Analytic(models.Model):
    _inherit = "account.analytic.account"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for account in self:
            account.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'account.analytic.account'), ('res_id', '=', account.id),
            ])

    def dms_tree_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'account.analytic.account'),
                ('res_id', 'in', self.ids),
                
            ])
            return action
