from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class Document(models.Model):
    _inherit = 'dms.file'

    document_version = fields.Char(string="Document Version", copy=False, store=True)

    @api.onchange('name', 'extension', 'directory_id', 'storage_id')
    def doc_onchange(self):
        if self.name and self.extension and self.directory_id and self.storage_id:
            existing_doc_id = self.env['dms.file'].search([
                ('name', '=', self.name),
                ('extension', '=', self.extension),
                ('directory_id', '=', self.directory_id.id),
                ('storage_id', '=', self.storage_id.id),
            ], order='id desc', limit=1)
            if existing_doc_id:
                self.write({'document_version': float(existing_doc_id.document_version) + 1.0})
            else:
                self.write({'document_version': 1.0})
        else:
            self.write({'document_version': 1.0})

    @api.depends('name', 'extension', 'directory_id', 'storage_id', 'document_version')
    def _compute_previous_dms_file(self):
        for rec in self:
            previous_doc = self.env['dms.file'].search([
                    ('name', '=', rec.name),
                    ('extension', '=', rec.extension),
                    ('directory_id', '=', rec.directory_id.id),
                    ('storage_id', '=', rec.storage_id.id),
                    ('document_version', '=', float(rec.document_version) - 1.0)
                ], limit=1)
            rec.document_previous_version = previous_doc.id

    document_previous_version = fields.Many2one('dms.file', string="Prev Version",
                                                compute=_compute_previous_dms_file, copy=False)

    @api.depends('name', 'extension', 'directory_id', 'storage_id', 'document_version')
    def _compute_next_dms_file(self):
        for rec in self:
            previous_doc = self.env['dms.file'].search([
                ('name', '=', rec.name),
                ('extension', '=', rec.extension),
                ('directory_id', '=', rec.directory_id.id),
                ('storage_id', '=', rec.storage_id.id),
                ('document_version', '=', float(rec.document_version) + 1.0)
            ], limit=1)
            rec.document_next_version = previous_doc.id

    document_next_version = fields.Many2one('dms.file', string="Next Version",
                                            compute=_compute_next_dms_file, copy=False)

    def action_previous_doc_view(self):
        if not self.document_previous_version:
            raise ValidationError(_("This document does not have a previous version"))
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'dms.file',
            'target': 'self',
            'res_id': self.document_previous_version.id,
            'views': [[False, 'form']],
        }

    def action_next_doc_view(self):
        if not self.document_next_version:
            raise ValidationError(_("This document does not have a next version"))
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'dms.file',
            'target': 'self',
            'res_id': self.document_next_version.id,
            'views': [[False, 'form']],
        }

    @api.constrains("name")
    def _check_name(self):
        for record in self:
            # if not file.check_name(record.name):
            #     raise ValidationError(_("The file name is invalid."))
            files = record.sudo().directory_id.file_ids.name_get()
            list_files = list(filter(lambda file: file[1] == record.name and file[0] != record.id, files))

            for _rec in list_files:
                doc_id = self.browse(_rec[0])
                if float(doc_id.document_version) == float(record.document_version):
                    raise ValidationError(_("A file with the same name already exists."))
