from odoo import models, fields, api


class Partner(models.Model):
    _inherit = 'res.partner'

    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Partner's Attachment")

    def _compute_attached_docs_count(self):
        document_obj = self.env['dms.file']
        for rec in self:
            rec.doc_count = document_obj.search_count([('res_model', '=', 'res.partner'), ('res_id', '=', rec.id)])

    def action_view_dms(self):
        action = self.env['ir.actions.act_window']._for_xml_id('dms.action_dms_file')
        action['domain'] = str([
            ('res_model', '=', 'res.partner'),
            ('res_id', 'in', self.ids),
        ])
        return action
