# -*- coding: utf-8 -*-
# © 2016 Therp BV <http://therp.nl>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import base64
import os
from odoo import api, models, SUPERUSER_ID
from odoo.modules.registry import Registry
import os.path
from os import path
import pathlib

try:
    from paramiko import SFTP_NO_SUCH_FILE, SFTP_PERMISSION_DENIED
except ImportError:   # pragma: no cover
    pass


class DocumentSFTPRootByModel(models.Model):
    _inherit = 'document.sftp.root'
    _name = 'document.sftp.root.by_model'
    _virtual_root = 'By model'
    _virtual_root_by_id = 'By id'
    _description = 'Document SFTP Root'

    @api.model
    def _get_root_attributes(self):
        return self._directory(self._virtual_root)

    @api.model
    def _stat(self, path):
        path = path.strip('/')
        if not path.startswith(self._virtual_root):
            return SFTP_NO_SUCH_FILE
        components = path.split('/')
        if len(components) == 1:
            return self._get_root_attributes()
        elif len(components) in (2, 3):
            return self._directory(components[-1])
        elif len(components) == 4:
            return self._file(self.env['ir.attachment'].search([
                ('res_model', '=', components[-3]),
                ('res_id', '=', components[-2]),
                '|',
                ('datas_fname', '=', components[-1]),
                ('name', '=', components[-1]),
            ], limit=1))
        return SFTP_NO_SUCH_FILE

    @api.model
    def _list_folder(self, path):
        path = path.strip('/')
        components = path.split('/')
        result = []
        if len(components) == 1:
            for model in self.env['ir.model'].search([
                ('osv_memory', '=', False),
            ]):
                if not self.env['ir.model.access'].check(
                    model.model, raise_exception=False
                ):
                    continue
                result.append(self._directory(model.model))
        elif len(components) == 2:
            model = components[-1]
            seen = set([])
            if model not in self.env.registry:
                return SFTP_NO_SUCH_FILE
            for attachment in self.env['ir.attachment'].search([
                ('res_model', '=', model),
                ('res_id', '!=', False),
            ], order='res_id asc'):
                # TODO: better lump ids together in steps of 100 or something?
                if attachment.res_id not in seen:
                    seen.add(attachment.res_id)
                    result.append(self._directory(str(attachment.res_id)))
        elif len(components) == 3:
            model = components[-2]
            res_id = int(components[-1])
            for attachment in self.env['ir.attachment'].search([
                ('res_model', '=', model),
                ('res_id', '=', res_id),
            ]):
                result.append(self._file(attachment))
        else:
            return SFTP_NO_SUCH_FILE
        return result

    @api.model
    def _open(self, path, flags, attr):
        if flags & os.O_WRONLY or flags & os.O_RDWR:
            # TODO: do something more sensible here
            return SFTP_PERMISSION_DENIED
        path = path.strip('/')
        components = path.split('/')
        if len(components) == 4:
            return self._file_handle(self.env['ir.attachment'].search([
                ('res_model', '=', components[-3]),
                ('res_id', '=', components[-2]),
                '|',
                ('datas_fname', '=', components[-1]),
                ('name', '=', components[-1]),
            ], limit=1))
        return SFTP_PERMISSION_DENIED

    def _upload(self, f, path):
        try:
            split_path = path.split('/')
            filename = split_path[-1]
            res_data = split_path[-2].split('-')
            res_id = res_data[-1]
            res_model = res_data[-2]
        except IndexError:
            filename = 'SFTP Attachment'
            res_id = False
            res_model = False

        db_name = self._cr.dbname
        db_registry = Registry.new(db_name)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env['ir.attachment'].create({
                'res_model': res_model,
                'res_id': res_id,
                'datas': base64.b64encode(f.read()),
                'name': filename,
                'type': 'binary'
            })

    # cron job to upload to odoo frequently
    def _upload_attachments_to_crm(self):
        document_sftp_path = self.env['ir.config_parameter'].sudo().get_param('document_sftp.path')
        team_id = self.env['crm.team'].search([])

        for rec in team_id:
            sale_dir_path = f"{document_sftp_path}/{rec.name}-{rec._name}-{rec.id}"
            if path.exists(sale_dir_path):
                for x_dir in os.listdir(sale_dir_path):
                    attachment_id = self.env['ir.attachment'].search([('name', '=', x_dir)])
                    f = open(f"{sale_dir_path}/{x_dir}", 'rb')
                    if not attachment_id:
                        self._upload(f, f"{sale_dir_path}/{x_dir}")

