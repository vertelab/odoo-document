# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
try:
    from paramiko import SFTP_PERMISSION_DENIED, SFTPServerInterface,\
        SFTPServer
except ImportError:
    pass
from odoo import api
import os
import os.path
from os import path
import pathlib
import base64
from io import BytesIO
from PIL import Image, ImageFile


class DocumentSFTPSftpServerInterface(SFTPServerInterface):
    def __init__(self, server, env):
        self.env = env

    def list_folder(self, path):
        if not path or path in ('/', '.'):
            return self.env['document.sftp']._get_root_entries()
        handler = self.env['document.sftp']._get_handler_for(path)
        if handler is None:
            return SFTP_PERMISSION_DENIED
        return handler._list_folder(path)

    def lstat(self, path):
        if path == '.':
            return self.env['document.sftp.root']._directory('/')
        handler = self.env['document.sftp']._get_handler_for(path)
        if handler is None:
            return SFTP_PERMISSION_DENIED
        return handler._lstat(path)

    def stat(self, path):
        handler = self.env['document.sftp']._get_handler_for(path)
        if handler is None:
            return SFTP_PERMISSION_DENIED
        return handler._stat(path)

    def open(self, path, flags, attr):
        handler = self.env['document.sftp']._get_handler_for(path)
        if handler is None:
            return SFTP_PERMISSION_DENIED
        return handler._open(path, flags, attr)

    def session_ended(self):
        self.env.cr.close()
        return super(DocumentSFTPSftpServerInterface, self).session_ended()

    def session_started(self):
        self.env = self.env(cr=self.env.registry.cursor())
        self._sales_team()

    def _sales_team(self):
        self.env = self.env(cr=self.env.registry.cursor())
        team_id = self.env['crm.team'].search([])

        for rec in team_id:
            current_dir = pathlib.Path().resolve()
            sale_dir_path = f"{current_dir}/{rec.name}-{rec._name}-{rec.id}"
            if not path.exists(sale_dir_path):
                try:
                    os.mkdir(sale_dir_path)
                except OSError as error:
                    print(error)
            self._get_sales_team_attachment(rec._name, rec.id, sale_dir_path)

    def _get_sales_team_attachment(self, model, res_id, dir_path):
        ir_attachment = self.env['ir.attachment'].search([
            ('res_model', '=', model),
            ('res_id', '=', res_id)
        ])
        if ir_attachment:
            for attachment in ir_attachment:
                team_attachment = f"{dir_path}/{attachment.name}"
                if not path.exists(team_attachment):
                    with open(team_attachment, 'wb') as f:
                        stream = base64.b64decode(attachment.datas)
                        f.write(stream)


class DocumentSFTPSftpServer(SFTPServer):
    def start_subsystem(self, name, transport, channel):
        with api.Environment.manage():
            return super(DocumentSFTPSftpServer, self).start_subsystem(
                name, transport, channel)
