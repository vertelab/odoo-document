# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Repair(models.Model):
    _inherit = "repair.order"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for order in self:
            order.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'repair.order'), ('res_id', '=', order.id),
            ])

    def dms_tree_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'repair.order'),
                ('res_id', 'in', self.ids),
                
            ])
            return action

  
