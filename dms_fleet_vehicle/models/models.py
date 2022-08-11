# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Fleet(models.Model):
    _inherit = "fleet.vehicle"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for vehicle in self:
            vehicle.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'fleet.vehicle'), ('res_id', '=', vehicle.id),
            ])

    def dms_tree_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'fleet.vehicle'),
                ('res_id', 'in', self.ids),
                
            ])
            return action
