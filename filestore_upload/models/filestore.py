import paramiko
import base64
import logging
import urllib.request
import os

from odoo.exceptions import UserError, ValidationError
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class FileStore(models.TransientModel):
    _name = 'upload.filestore'
    _description = 'Upload Large Files'

    host = fields.Char(string="Host")
    port = fields.Char(string="Port")
    request_type = fields.Selection([('wget', 'WGET'), ('sftp', 'SFTP')], string="Request Type", default='wget')
    url = fields.Char(string="URL")
    username = fields.Char(string="Username")
    password = fields.Char(string="Password")
    file_path = fields.Char(string="File Path")
    res_model = fields.Char(string="Model")
    res_id = fields.Char(string="Record ID")

    def action_upload(self):
        if self.request_type == 'sftp':
            self._sftp_sync()
        if self.request_type == 'wget':
            self._wget_sync()

    def _wget_sync(self):
        try:
            filename = urllib.request.urlopen(self.url)
            file_name = os.path.basename(self.url)
            self._create_attachment(file_name, filename)
        except Exception as e:
            _logger.warning(e)
            raise UserError(f'Something went wrong, exception: {e}')

    def _sftp_sync(self):
        host, port = self.host, self.port
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if not port:
                port = 22
            client.connect(hostname=host, username=self.username, password=self.password, port=port)
            sftp_client = client.open_sftp()
            remote_file = sftp_client.open(self.file_path)
            remote_file.prefetch()
            self._create_attachment(self.file_path, remote_file)
        except Exception as e:
            _logger.warning(e)
            raise UserError(f'Something went wrong, exception: {e}')

    def _create_attachment(self, name, datas):
        self.env['ir.attachment'].create({
            'name': name,
            'type': 'binary',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'datas': base64.encodebytes(datas.read()),
        })
