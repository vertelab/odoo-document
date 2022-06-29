# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class CRMLead(models.Model):
    _inherit = "crm.lead"
    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Doc count")

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for crm_lead in self:
            crm_lead.doc_count = Document.search_count([
                '&',
                ('res_model', '=', 'crm.lead'), ('res_id', '=', crm_lead.id),
            ])

    def dms_tree_view(self):
            action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
            action['domain'] = str([
                '&',
                ('res_model', '=', 'crm.lead'),
                ('res_id', 'in', self.ids),
                
            ])
            action['view_mode'] = 'kanban, form'
            action['binding_view_types'] = 'kanban, form'
            return action
