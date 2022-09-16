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
import traceback
import tempfile

from paramiko.common import o644, o777

_logger = logging.getLogger(__name__)


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

            directory_obj_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', dir_name)],
                                                                                         limit=1)

            if directory_obj_id and not file_name.startswith('.giosave'):
                file_obj = self.env['dms.file'].with_user(self.env.user).search(
                    [('name', '=', file_name), ('directory_id', '=', directory_obj_id.id)], limit=1)
                if file_obj:
                    file_obj.with_user(self.env.user).write({
                        'content': base64.b64encode(data),
                        'content_file': base64.b64encode(data),
                        'content_binary': base64.b64encode(data),
                    })
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
        except OSError as e:
            _logger.info("Exception: %s", e)
            return SFTPServer.convert_errno(e.errno)


class DocumentSFTPSftpServerInterface(SFTPServerInterface):
    # ROOT = os.path.expanduser('~')
    ROOT = os.path.expanduser('/tmp')

    def __init__(self, server, env):
        self.env = api.Environment(env.cr, server.env.user.id, env.context)
        # self.ROOT = self._realpath(self.ROOT + f"/{self.env.cr.dbname}")
        # if not path.exists(self.ROOT):
        #     os.mkdir(self.ROOT, mode=o777)
        # os.chmod(self.ROOT, mode=o777)

    def _realpath(self, file_path):
        return self.canonicalize(file_path)

    def list_folder(self, file_path):
        """
            list_folder: is responsible for the display of folders and files in the /tmp dir
            os.listdir: lists all directories, the filter used in the loop can be improved
        """
        if not file_path or file_path in ('/', '.'):
            file_path = self._realpath(self.ROOT)
        else:
            file_path = self._realpath(self.ROOT + file_path)
        try:
            out = []
            flist = os.listdir(file_path)
            for fname in flist:
                if not (fname.startswith(".") or fname.startswith(
                        ("sudo", "snap", "pyr", "systemd", "python", "appI", "tmp", "snap", "hsperfdata", ".",
                         "liblz4", "tracker", "ssh", "config", "Temp-"))):
                    attr = SFTPAttributes.from_stat(os.stat(os.path.join(file_path, fname)))
                    attr.filename = fname
                    out.append(attr)
            return out
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def stat(self, file_path):
        """os.stat return an SFTPAttributes object for a path on the server,"""
        file_path = self._realpath(self.ROOT + file_path)
        try:
            return SFTPAttributes.from_stat(os.stat(file_path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def lstat(self, file_path):
        """Retrieve information about a file on the remote system, without shortcuts"""
        file_path = self._realpath(self.ROOT + file_path)
        try:
            return SFTPAttributes.from_stat(os.lstat(file_path))
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)

    def open(self, f_path, flags, attr):
        x_path = self._realpath(self.ROOT + f_path)
        fd = os.open(x_path, flags, o644)
        try:
            f = os.fdopen(fd, "wb+")
        except OSError as e:
            _logger.info("Error: %s", e)
            return SFTPServer.convert_errno(e.errno)

        fobj = StubSFTPHandle(self.env, x_path, flags)
        fobj.filename = x_path
        fobj.readfile = f
        fobj.writefile = f

        return fobj

    def unlink_on_odoo(self, is_dir=False, file_path=None):
        """
            this is used to handle deleting of files or directory on odoo.
            it is used in the remove func
        """
        try:
            folder_path, file = os.path.split(file_path)  # ('/tmp/Partners/Bloem GmbH', 'goat.jpeg')
            if is_dir:
                folder_name = file.split('/')[-1]
                file = ''
            else:
                folder_name = folder_path.split('/')[-1]

            directory_obj_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', folder_name)],
                                                                                         limit=1)
            if directory_obj_id and file:
                self.env.cr.fetchall()
                file_obj = self.env['dms.file'].with_user(self.env.user).search(
                    [('name', '=', file), ('directory_id.name', '=', directory_obj_id.name)], limit=1)
                if file_obj:
                    file_obj.unlink(ok=False)
            elif directory_obj_id and file == '':
                directory_obj_id.unlink(ok=False)
            self.env.cr.commit()
        except Exception as e:
            return False

    def remove(self, file_path):
        if not file_path or file_path in ('/', '.'):
            file_path = self._realpath(self.ROOT)
        else:
            file_path = self._realpath(self.ROOT + file_path)
        try:
            self.unlink_on_odoo(file_path=file_path)
            self.env.cr.commit()
            os.remove(file_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rename(self, old_path, new_path):
        """responsible for renaming file on the remote sever."""
        old_path = self._realpath(self.ROOT + old_path)
        new_path = self._realpath(self.ROOT + new_path)
        try:
            os.rename(old_path, new_path)
            stfp_handle = StubSFTPHandle(env=self.env, doc_path=new_path)
            if new_path and os.path.isfile(new_path):
                stfp_handle._upload_file_to_odoo(data=open(new_path, 'rb').read())
            elif new_path and os.path.isdir(new_path):
                self.mk_update_dir_odoo(dir_path=old_path, new_path=new_path)
            if old_path:
                self.unlink_on_odoo(file_path=old_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def mkdir(self, file_path, attr):
        """responsible for creating directory on the remote sever. no relationship with odoo yet"""
        file_path = self._realpath(self.ROOT + file_path)
        try:
            dir_id = self.mk_update_dir_odoo(file_path)
            if dir_id:
                os.mkdir(file_path)
            if attr is not None:
                SFTPServer.set_file_attr(file_path, attr)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rmdir(self, file_path):
        """responsible for deleting directory on the remote sever. no relationship with odoo yet"""
        file_path = self._realpath(self.ROOT + file_path)
        try:
            self.unlink_on_odoo(is_dir=True, file_path=file_path)
            os.rmdir(file_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def chattr(self, file_path, attr):
        file_path = self._realpath(self.ROOT)
        try:
            SFTPServer.set_file_attr(file_path, attr)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def symlink(self, target_path, file_path):
        file_path = self._realpath(self.ROOT + file_path)
        if (len(target_path) > 0) and (target_path[0] == '/'):
            # absolute symlink
            target_path = os.path.join(self.ROOT, target_path[1:])
            if target_path[:2] == '//':
                # bug in os.path.join
                target_path = target_path[1:]
        else:
            # compute relative to path
            abspath = os.path.join(os.path.dirname(file_path), target_path)
            if abspath[:len(self.ROOT)] != self.ROOT:
                # this symlink isn't going to work anyway -- just break it immediately
                target_path = '<error>'
        try:
            os.symlink(target_path, file_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def readlink(self, file_path):
        file_path = self._realpath(self.ROOT + file_path)
        try:
            symlink = os.readlink(file_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        # if it's absolute, remove the root
        # if os.path.isabs(symlink):
        #     if symlink[:len(self.ROOT)] == self.ROOT:
        #         symlink = symlink[len(self.ROOT):]
        #         if (len(symlink) == 0) or (symlink[0] != '/'):
        #             symlink = '/' + symlink
        #     else:
        #         symlink = '<error>'
        return symlink

    def session_ended(self):
        self.env.cr.close()
        return super(DocumentSFTPSftpServerInterface, self).session_ended()

    def session_started(self):
        self.env = self.env(cr=self.env.registry.cursor())
        self._create_directory(self.ROOT, data=self.dms_directories())

    def _create_directory(self, dir_path, data):
        def create_dir(x_dir_path):
            if not path.exists(x_dir_path):
                try:
                    os.mkdir(x_dir_path)
                except OSError as error:
                    _logger.info('OSError %s', error)
            return x_dir_path

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
        root_directory = self.env['dms.directory'].with_user(self.env.user).search(
            [("is_hidden", "=", False), ("parent_id", "=", False)])

        dir_list = []

        for rec in root_directory:
            def get_child_directory(in_rec):
                child_directory_obj = self.env['dms.directory'].with_user(self.env.user).search(
                    [("is_hidden", "=", False), ("parent_id", "=", in_rec.id)])
                child_directory_list = []
                for child in child_directory_obj:
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
                'file_ids': rec.file_ids.ids,
                'model': rec.model_id.model,
            })
        return dir_list

    def mk_update_dir_odoo(self, dir_path=None, new_path=None):
        if not dir_path == self.ROOT:
            parent_dir_path = ''.join(dir_path.split(self.ROOT))  # ('/Media/Music')
            split_dir = list(filter(None, parent_dir_path.split('/')))
            new_dir = split_dir[-1]
            directory_obj_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', new_dir)],
                                                                                         limit=1)
            if not directory_obj_id:
                storage_id = self.env.ref('dms.storage_demo')
                dir_vals = {'name': new_dir}

                if len(split_dir) == 1:
                    dir_vals.update({
                        'is_root_directory': True,
                        'storage_id': storage_id.id,
                        'group_ids': [(6, False, [self.env.ref('dms.access_group_01_demo').id])],
                    })
                elif len(split_dir) > 1:
                    parent_directory_obj_id = self.env['dms.directory'].with_user(self.env.user).search([
                        ('name', '=', split_dir[-2])], limit=1)
                    dir_vals.update({
                        'is_root_directory': False,
                        'storage_id': parent_directory_obj_id.storage_id.id,
                        'parent_id': parent_directory_obj_id.id,
                        'group_ids': parent_directory_obj_id.group_ids.ids,
                    })
                directory_obj_id = self.env['dms.directory'].with_user(self.env.user).create(dir_vals)
                self.env.cr.commit()
            else:
                new_dir_path = ''.join(new_path.split(self.ROOT))  # ('/Media/Music')
                split_dir = list(filter(None, new_dir_path.split('/')))
                new_dir = split_dir[-1]

                directory_obj_id.write({
                    'name': new_dir
                })
                self.env.cr.commit()
            return directory_obj_id


class DocumentSFTPSftpServer(SFTPServer):
    def start_subsystem(self, name, transport, channel):
        with api.Environment.manage():
            return super(DocumentSFTPSftpServer, self).start_subsystem(name, transport, channel)
