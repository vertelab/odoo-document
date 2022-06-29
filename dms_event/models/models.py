# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class Event(models.Model):
    _inherit = "event.event"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for event in self:
            event.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'event.event'), ('res_id', '=', event.id),
            ])

    def dms_tree_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'event.event'),
                ('res_id', 'in', self.ids),
                
            ])
            action['view_mode'] = 'kanban, form'
            action['binding_view_types'] = 'kanban, form'
            return action
