import pysftp
import paramiko
import io
import base64
import tempfile
from odoo.exceptions import UserError, ValidationError
from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)


class FileStore(models.TransientModel):
    _name = 'upload.filestore'
    _description = 'Upload Large Files'

    host = fields.Char(string="Host")
    port = fields.Char(string="Port")
    username = fields.Char(string="Username")
    password = fields.Char(string="Password")
    file_path = fields.Char(string="File Path")
    res_model = fields.Char(string="Model")
    res_id = fields.Char(string="Record ID")

    def action_upload(self):
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

            self.env['ir.attachment'].create({
                'name': self.file_path,
                'type': 'binary',
                'res_model': self.res_model,
                'res_id': self.res_id,
                'datas': base64.encodebytes(remote_file.read()),
            })
        except Exception as e:
                _logger.warning(e)
                raise UserError(f'Something went wrong, exception: {e}')
                pass


