# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
try:
    from paramiko import SFTPServerInterface, SFTPServer, SFTPAttributes, SFTPHandle
    from paramiko.sftp import SFTP_OK
except ImportError:
    pass
from email.mime import base
from odoo import api
import os
import os.path
from os import path
import base64
import logging
import tempfile

from paramiko.common import o644

_logger = logging.getLogger(__name__)

# --log-handler=paramiko:DEBUG


class StubSFTPHandle(SFTPHandle):

    def __init__(self, env, doc_path, flags=0):
        self.env = env
        self.doc_path = doc_path
        self.flags = flags
        super(StubSFTPHandle, self).__init__(flags)

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

    def write(self, offset, data):
        res = super().write(offset, data)
        self._upload_file_to_odoo(data=open(self.doc_path, 'rb').read())
        return res

    def _upload_file_to_odoo(self, data=None):
        try:
            folder_path, file_name = os.path.split(self.doc_path)  # ('/tmp/Media', 'goat.jpeg')

            dir_name = folder_path.split('/')[-1]

            directory_obj_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', dir_name)], limit=1)  

            if directory_obj_id:
                file_obj = self.env['dms.file'].with_user(self.env.user).search([('name', '=', file_name), ('directory_id', '=', directory_obj_id.id)], limit=1)
                if file_obj:
                    file_obj.write({'content': base64.b64encode(data)})
                else:
                    self.env['dms.file'].with_user(self.env.user).create({
                        'name': file_name,
                        'directory_id': directory_obj_id.id,
                        'res_model': directory_obj_id.model_id.id,
                        'res_id': directory_obj_id.res_id,
                        'content': base64.b64encode(data),
                        'content_file': base64.b64encode(data),
                        'content_binary': base64.b64encode(data),
                    })
                self.env.cr.commit()
        except Exception as e:
            _logger.info("Exception: %s", e)
            return SFTPServer.convert_errno(e)    
    

class DocumentSFTPSftpServerInterface(SFTPServerInterface):
    # ROOT = os.path.expanduser('~') 
    ROOT = os.path.expanduser('/tmp') 

    def __init__(self, server, env):
        self.env = api.Environment(env.cr, server.env.user.id, env.context)
        

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
                if not (fname.startswith(".") or fname.startswith(("sudo", "snap", "pyr", "systemd", "python", "appI"))):
                    attr = SFTPAttributes.from_stat(os.stat(os.path.join(path, fname)))
                    attr.filename = fname
                    out.append(attr)
            return out
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)


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


    def open(self, f_path, flags, attr):
        x_path = self._realpath(self.ROOT + f_path)
        
        try:
            binary_flag = getattr(os, "O_BINARY", 0)
            flags |= binary_flag
            mode = getattr(attr, "st_mode", None)
            if mode is not None:
                fd = os.open(x_path, flags, mode)
            else:
                # os.open() defaults to 0777 which is
                # an odd default mode for files
                fd = os.open(x_path, flags, o644)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        if (flags & os.O_CREAT) and (attr is not None):
            attr._flags &= ~attr.FLAG_PERMISSIONS
            SFTPServer.set_file_attr(x_path, attr)
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
            fstr = "rb"
        
        try:
            f = os.fdopen(fd, fstr)
        except OSError as e:
            _logger.info("Error: %s", e)
            return SFTPServer.convert_errno(e.errno)
        
        fobj = StubSFTPHandle(self.env, x_path, flags)

        fobj.filename = x_path
        fobj.readfile = f
        fobj.writefile = f

        return fobj

    def unlink_on_odoo(self, file_path):
        try:
            folder_path, file = os.path.split(file_path)  # ('/tmp/Partners/Bloem GmbH', 'goat.jpeg')
            folder_name = folder_path.split('/')[-1]
            
            directory_obj_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', folder_name)], limit=1)
            if directory_obj_id and file:
                self.env.cr.fetchall()
                file_obj = self.env['dms.file'].with_user(self.env.user).search([('name', '=', file), ('directory_id', '=', directory_obj_id.id)], limit=1)
                if file_obj:
                    file_obj.unlink()
            elif directory_obj_id and file == '':
                directory_obj_id.unlink()
        except Exception as e:
            return False


    def remove(self, path):
        if not path or path in ('/', '.'):
            path = self._realpath(self.ROOT)
        else:
            path = self._realpath(self.ROOT + path)
        try:
            self.unlink_on_odoo(path)
            self.env.cr.commit()
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
        self.env = self.env(cr=self.env.registry.cursor())        
        self._create_directory(self.ROOT, data=self.dms_directories())

    
    def _create_directory(self, dir_path, data):
        def create_dir(dir_path):
            if not path.exists(dir_path):
                try:
                    os.mkdir(dir_path)
                except OSError as error:
                    _logger.info('OSError %s', error)
            return dir_path
        
        for dir_data in data:
            x_path = create_dir(f"{dir_path}/{dir_data.get('name')}")


            if dir_data.get('child_directory_ids'):
                self._create_directory(x_path, dir_data.get('child_directory_ids'))
            
            if dir_data.get('file_ids'):
                self._dms_files(x_path, dir_data.get('file_ids'))


    def _dms_files(self, dir_path, file_ids):
        file_obj_ids = self.env['dms.file'].with_user(self.env.user).browse(file_ids)
        for file in file_obj_ids:
            dms_directory_file = f"{dir_path}/{file.name}"
            if not path.exists(dms_directory_file):
                with open(dms_directory_file, 'wb') as f:
                    stream = base64.b64decode(file.content)
                    f.write(stream)


    def dms_directories(self):
        root_directory = self.env['dms.directory'].with_user(self.env.user).search([("is_hidden", "=", False), ("parent_id", "=", False)])

        dir_list = []

        for rec in root_directory:
            def get_child_directory(rec):
                child_directory = self.env['dms.directory'].with_user(self.env.user).search([("is_hidden", "=", False), ("parent_id", "=", rec.id)])
                child_directory_list = []
                for child in child_directory:
                    if child.child_directory_ids:
                        child_directory_list.append({
                            'id': child.id,
                            'name': child.name,
                            'child_directory_ids': get_child_directory(child),
                            'file_ids': child.file_ids.ids,
                            'model': child.model_id.model,
                        })
                    else:
                        child_directory_list.append({
                            'id': child.id,
                            'name': child.name,
                            'child_directory_ids': [],
                            'file_ids': child.file_ids.ids,
                            'model': child.model_id.model,
                        })
                return child_directory_list

            child_directory = get_child_directory(rec)
            dir_list.append({
                'id': rec.id,
                'name': rec.name,
                'child_directory_ids': child_directory,
                'file_ids' : rec.file_ids.ids,
                'model': rec.model_id.model,
            })
        return dir_list


class DocumentSFTPSftpServer(SFTPServer):
    def start_subsystem(self, name, transport, channel):
        with api.Environment.manage():
            return super(DocumentSFTPSftpServer, self).start_subsystem(name, transport, channel)

