# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
try:
    from paramiko import SFTPServerInterface,\
        SFTPServer, SFTPAttributes, SFTPHandle
    # from paramiko.sftp_client import SFTPClient
    from paramiko.sftp import SFTP_PERMISSION_DENIED, SFTP_NO_SUCH_FILE, SFTP_PERMISSION_DENIED, SFTP_OK
except ImportError:
    pass
from odoo import api, SUPERUSER_ID
# from requests import request
from odoo.http import request
from odoo.exceptions import UserError, AccessError
import os
from rich import print
import os.path
from os import path
import pathlib
import base64
import io
from shutil import copyfile
import logging
import tempfile
from io import BytesIO
import pwd
import stat
import grp
from PIL import Image, ImageFile

from paramiko.common import o666, o777

_logger = logging.getLogger(__name__)


class StubSFTPHandle(SFTPHandle):
    def stat(self):
        try:
            return SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def chattr(self, attr):
        # python doesn't have equivalents to fchown or fchmod, so we have to
        # use the stored filename
        try:
            SFTPServer.set_file_attr(self.filename, attr)
            return SFTP_OK
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)


class DocumentSFTPSftpServerInterface(SFTPServerInterface):
    ROOT = os.path.expanduser('~') # os.getcwd()
    # ROOT = tempfile.gettempdir()

    def __init__(self, server, env):
        self.env = env

    def _realpath(self, path):
        return self.canonicalize(path)

    def create_temp_file(self):
        fd, path = tempfile.mkstemp()
        f = os.fdopen(fd, "wb")
        return f, path

    def list_folder(self, path):
        if not path or path in ('/', '.'):
            path = self._realpath(self.ROOT)
        else:
            path = self._realpath(self.ROOT + path)
        try:
            out = []
            flist = os.listdir(path)
            for fname in flist:
                if not (fname.startswith(".") or fname.startswith("sudo")):
                    attr = SFTPAttributes.from_stat(os.stat(os.path.join(path, fname)))
                    attr.filename = fname
                    out.append(attr)
            return out
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    
    # def list_folder(self, path):
    #     if not path or path in ('/', '.'):
    #         path = self._realpath(self.ROOT)
    #     else:
    #         path = self._realpath(self.ROOT + path)
    #     try:
    #         out = []
    #         team = self.env['crm.team'].search([]).mapped('name')
    #         print(team)
    #         with tempfile.TemporaryDirectory() as temp_dir:
    #             for team_name in team:
    #                 print(team_name)
    #                 attr = os.stat(os.path.join(temp_dir, team_name))
    #                 print(attr)
    #                 # attr.filename = team_name
    #                 out.append(attr)
    #                 # os.path.join(temp_dir, 'named_file')
    #         print(out)
    #         return out
    #     except OSError as e:
    #         return SFTPServer.convert_errno(e.errno)

    def stat(self, path):
        path = self._realpath(self.ROOT + path)
        try:
            return SFTPAttributes.from_stat(os.stat(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def lstat(self, path):
        path = self._realpath(self.ROOT + path)
        try:
            return SFTPAttributes.from_stat(os.lstat(path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    
    def open(self, path, flags, attr):
        path = self._realpath(self.ROOT + path)
        try:
            binary_flag = getattr(os, "O_BINARY", 0)
            flags |= binary_flag
            mode = getattr(attr, "st_mode", None)
            if mode is not None:
                fd = os.open(path, flags, mode)
            else:
                # os.open() defaults to 0777 which is
                # an odd default mode for files
                fd = os.open(path, flags, o666)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        if (flags & os.O_CREAT) and (attr is not None):
            attr._flags &= ~attr.FLAG_PERMISSIONS
            SFTPServer.set_file_attr(path, attr)
        if flags & os.O_WRONLY:
            if flags & os.O_APPEND:
                fstr = "ab"
            else:
                fstr = "wb"
        elif flags & os.O_RDWR:
            if flags & os.O_APPEND:
                fstr = "a+b"
            else:
                fstr = "r+b"
        else:
            # O_RDONLY (== 0)
            fstr = "rb"
        try:
            f = os.fdopen(fd, fstr)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        fobj = StubSFTPHandle(flags)
        fobj.filename = path
        fobj.readfile = f
        fobj.writefile = f
        return fobj
    
    
    
    
    
    
    # def open(self, path, flags, attr):
    #     path = self._realpath(self.ROOT + path)
    #     try:
    #         binary_flag = getattr(os, "O_BINARY", 0)
    #         flags |= binary_flag
    #         mode = getattr(attr, "st_mode", None)

    #         print('st_uid', getattr(attr, "st_uid"))
    #         print('st_gid', getattr(attr, "st_gid"))
    #         print('st_mode', getattr(attr, "st_mode"))

    #         # 'st_atime',
    #         # 'st_gid',
    #         # 'st_mode',
    #         # 'st_mtime',
    #         # 'st_size',
    #         # 'st_uid'

    #         if mode is not None:
    #             fd = os.open(path, flags, mode)
    #         else:
    #             # os.open() defaults to 0777 which is
    #             # an odd default mode for files
    #             fd = os.open(path, flags, o777)
    #     except OSError as e:
    #         return SFTPServer.convert_errno(e.errno)


    #     # if (flags & os.O_CREAT) and (attr is not None):
    #     #     attr._flags &= ~attr.FLAG_PERMISSIONS
    #     #     SFTPServer.set_file_attr(path, attr)

    #     return self.write_handler(path, fd, "wb", flags)
    #     # if flags & os.O_WRONLY:
    #     #     if flags & os.O_APPEND:
    #     #         fstr = "ab"
    #     #     else:
    #     #         fstr = "wb"
    #     #     return self.write_handler(path, fd, fstr, flags)
    #     # elif flags & os.O_RDWR:
    #     #     if flags & os.O_APPEND:
    #     #         fstr = "a+b"
    #     #     else:
    #     #         fstr = "r+b"
    #     # else:
    #     #     fstr = "rb"
    #     #     return self.read_handler(fd, fstr, flags)
        
    # def write_handler(self, path, fd, fstr, flags):
    #     # try:
    #     #     with os.fdopen(path, 'wb') as f:
    #     #         f.write(fd)
    #     # except OSError as e:
    #     #     return SFTPServer.convert_errno(e.errno)
    #     # fobj = StubSFTPHandle(flags)
    #     # fobj.filename = path
    #     # fobj.readfile = f
    #     # fobj.writefile = f
    #     # return fobj  

    #     try:
    #         f = os.fdopen(fd, fstr)
    #     except OSError as e:
    #         return SFTPServer.convert_errno(e.errno)
    #     fobj = StubSFTPHandle(flags)
    #     fobj.filename = path
    #     fobj.writefile = f
    #     st = os.stat(path)
    #     os.chmod(path, st.st_mode | stat.S_IWOTH)
    #     return fobj  

    # def read_handler(self, fd, fstr, flags):
    #     try:
    #         f = os.fdopen(fd, fstr)
    #     except OSError as e:
    #         return SFTPServer.convert_errno(e.errno)
    #     fobj = StubSFTPHandle(flags)
    #     fobj.filename = path
    #     fobj.readfile = f
    #     fobj.writefile = f
    #     return fobj



    def remove(self, path):
        if not path or path in ('/', '.'):
            path = self._realpath(self.ROOT)
        else:
            path = self._realpath(self.ROOT + path)
        try:
            os.remove(path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rename(self, oldpath, newpath):
        oldpath = self._realpath(self.ROOT + oldpath)
        newpath = self._realpath(self.ROOT + newpath)
        try:
            os.rename(oldpath, newpath)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def mkdir(self, path, attr):
        path = self._realpath(self.ROOT + path)
        try:
            os.mkdir(path)
            if attr is not None:
                SFTPServer.set_file_attr(path, attr)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rmdir(self, path):
        path = self._realpath(self.ROOT + path)
        try:
            os.rmdir(path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def chattr(self, path, attr):
        path = self._realpath(self.ROOT)
        try:
            SFTPServer.set_file_attr(path, attr)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def symlink(self, target_path, path):
        path = self._realpath(self.ROOT + path)
        if (len(target_path) > 0) and (target_path[0] == '/'):
            # absolute symlink
            target_path = os.path.join(self.ROOT, target_path[1:])
            if target_path[:2] == '//':
                # bug in os.path.join
                target_path = target_path[1:]
        else:
            # compute relative to path
            abspath = os.path.join(os.path.dirname(path), target_path)
            if abspath[:len(self.ROOT)] != self.ROOT:
                # this symlink isn't going to work anyway -- just break it immediately
                target_path = '<error>'
        try:
            os.symlink(target_path, path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def readlink(self, path):
        path = self._realpath(self.ROOT)
        try:
            symlink = os.readlink(path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        # if it's absolute, remove the root
        if os.path.isabs(symlink):
            if symlink[:len(self.ROOT)] == self.ROOT:
                symlink = symlink[len(self.ROOT):]
                if (len(symlink) == 0) or (symlink[0] != '/'):
                    symlink = '/' + symlink
            else:
                symlink = '<error>'
        return symlink

    def session_ended(self):
        self.env.cr.close()
        return super(DocumentSFTPSftpServerInterface, self).session_ended()

    def session_started(self):
        # self.env = self.env(cr=self.env.registry.cursor())
        self._sales_team()

    def _sales_team(self):
        print(self.env.user.id)
        print(self.env.user.name)
        # self.env = self.env(cr=self.env.registry.cursor())
        # document_sftp_path = self.env['ir.config_parameter'].sudo().get_param('document_sftp.path')
        # team_id = self.env['crm.team'].search([])

        # for rec in team_id:
        #     current_dir = pathlib.Path().resolve()
        #     sale_dir_path = f"{document_sftp_path}/{rec.name}-{rec._name}-{rec.id}"
        #     _logger.info('sale_dir_path %s', sale_dir_path)
        #     if not path.exists(sale_dir_path):
        #         try:
        #             os.mkdir(sale_dir_path)
        #         except OSError as error:
        #             _logger.info('OSError %s', error)
        #     self._get_sales_team_attachment(rec._name, rec.id, sale_dir_path)

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


    def _document_check_access(self, model_name, document_id, access_token=None):
        document = self.env[model_name].browse([document_id])
        document_sudo = document.with_user(SUPERUSER_ID).exists()
        if not document_sudo:
            raise SFTP_NO_SUCH_FILE
        try:
            document.check_access_rights('read')
            document.check_access_rule('read')
        except AccessError:
            return SFTP_PERMISSION_DENIED
        return document_sudo


class DocumentSFTPSftpServer(SFTPServer):
    def start_subsystem(self, name, transport, channel):
        with api.Environment.manage():
            print('transport', transport.session_id)
            return super(DocumentSFTPSftpServer, self).start_subsystem(
                name, transport, channel)
