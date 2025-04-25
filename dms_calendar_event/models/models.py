# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class Events(models.Model):
    _inherit = "calendar.event"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Number of documents attached")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for event in self:
            event.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'calendar.event'), ('res_id', '=', event.id),
            ])

    def dms_kanban_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'calendar.event'),
                ('res_id', 'in', self.ids),
            ])
            return action
