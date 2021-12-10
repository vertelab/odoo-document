from odoo import models, fields, api, _


class Document(models.Model):
    _inherit = 'dms.file'

    document_version = fields.Char(string="Document Version")
    document_previous_version = fields.Many2one('dms.file', string="Prev Version")
    document_current_version = fields.Many2one('dms.file', string="Current Version")

    @api.depends('name', 'extension', 'directory_id', 'storage_id')
    def _compute_version(self):
        for _rec in self:
            pass

    def search_document(self, name, extension, directory_id):
        return self.env['dms.file'].search([
            ('name', '=', name),
            ('extension', '=', extension),
            ('directory_id', '=', directory_id),
            # ('storage_id', '=', storage_id),
        ])

    @api.model
    def create(self, vals):
        document_id = self.search_document(
            vals.get('name'),
            vals.get('extension'),
            vals.get('directory_id')
        )
        return super(Document, self).create(vals)

    def action_previous_doc_view(self):
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'dms.file',
            'target': 'new',
            'res_id': self.document_previous_version.id,
            'views': [[False, 'form']],
        }

    def action_next_doc_view(self):
        pass
