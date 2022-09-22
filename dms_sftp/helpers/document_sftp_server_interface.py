try:
    from paramiko import SFTPServerInterface, SFTPServer, SFTPAttributes, SFTPHandle
    from paramiko.sftp import SFTP_OK
except ImportError:
    pass
from email.mime import base
from odoo import api
import os, stat
import os.path
from os import path
import base64
import logging
from paramiko.common import o644, o777
from .document_sftp_sftp_server import StubSFTPHandle

_logger = logging.getLogger(__name__)


class DocumentSFTPSftpServerInterface(SFTPServerInterface):
    ROOT = os.path.expanduser('/tmp')

    def __init__(self, server, env):
        self.env = api.Environment(env.cr, server.env.user.id, env.context)

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
        fd = os.open(x_path, os.O_CREAT | os.O_RDWR)
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

    def remove(self, file_path):
        if not file_path or file_path in ('/', '.'):
            file_path = self._realpath(self.ROOT)
        else:
            file_path = self._realpath(self.ROOT + file_path)
        try:
            stfp_handle = StubSFTPHandle(env=self.env, doc_path=file_path)
            stfp_handle._odoo_file_sync(action="Unlink")
            self.env.cr.commit()
            os.remove(file_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rename(self, old_path, new_path):
        print("paste rename")
        """responsible for renaming file on the remote sever."""
        old_path = self._realpath(self.ROOT + old_path)
        new_path = self._realpath(self.ROOT + new_path)
        try:
            os.rename(old_path, new_path)
            stfp_handle = StubSFTPHandle(env=self.env, doc_path=new_path)
            if new_path and os.path.isfile(new_path):
                stfp_handle._odoo_file_sync(data=open(new_path, 'rb').read(), action="CreateWrite")
            elif new_path and os.path.isdir(new_path):
                self._rename_odoo_dir(old_dir=old_path, new_dir=new_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def mkdir(self, file_path, attr):
        """responsible for creating directory on the remote sever. no relationship with odoo yet"""
        file_path = self._realpath(self.ROOT + file_path)
        try:
            dir_id = self._sync_odoo_dir(file_path)
            if dir_id:
                os.mkdir(file_path)
            if attr is not None:
                SFTPServer.set_file_attr(file_path, attr)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def rmdir(self, dir_path):
        """responsible for deleting directory on the remote sever. no relationship with odoo yet"""
        dir_path = self._realpath(self.ROOT + dir_path)
        try:
            self._unlink_dir(dir_path=dir_path)
            os.rmdir(dir_path)
        except OSError as e:
            return SFTPServer.convert_errno(e.errno)
        return SFTP_OK

    def session_ended(self):
        self.env.cr.close()
        return super(DocumentSFTPSftpServerInterface, self).session_ended()

    def session_started(self):
        self.env = self.env(cr=self.env.registry.cursor())
        self.ROOT = f"{self.ROOT}/{self.env.user.login}"
        if not path.exists(self.ROOT):
            os.mkdir(self.ROOT, mode=o777)
        os.chmod(self.ROOT, mode=o777)
        self._download_dms_directory(self.ROOT, data=self._fetch_dms_directories())

    def _download_dms_directory(self, dir_path, data):
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
                self._download_dms_directory(x_path, dir_data.get('child_directory_ids'))

            if dir_data.get('file_ids'):
                self._download_dms_files(x_path, dir_data.get('file_ids'))

    def _download_dms_files(self, dir_path, file_ids):
        file_obj_ids = self.env['dms.file'].with_user(self.env.user).browse(file_ids)
        for file in file_obj_ids:
            dms_directory_file = f"{dir_path}/{file.name}"
            with open(dms_directory_file, 'wb') as f:
                stream = base64.b64decode(file.content)
                f.write(stream)

    def _fetch_dms_directories(self):
        dms_directory = self.env['dms.directory']
        if dms_directory.check_access_rights('read', raise_exception=False):
            root_directory = dms_directory.with_user(self.env.user).search(
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

    def _sync_odoo_dir(self, dir_path=None):
        if not dir_path == self.ROOT:

            # /tmp/admin/Documents/Media/Test  ---> ('/tmp/admin/Documents/Media', 'Test')
            # /tmp/admin/Test  ---> ('/tmp/admin', 'Test')
            path_split = os.path.split(dir_path)

            # ('/tmp/admin/Documents/Media', 'Test') --> Test
            # ('/tmp/admin', 'Test') ---> Test
            new_dir_name = path_split[-1]

            # ('/tmp/admin/Documents/Media') split with  /tmp/admin ---> '/Documents/Media'
            # ('/tmp/admin')  split with  /tmp/admin ---> ''
            parent_dir_strip = ''.join(path_split[0].split(self.ROOT))

            # '/Documents/Media' --> Media
            # '' --> None
            parent_dir_name = os.path.split(parent_dir_strip)[-1] if parent_dir_strip else None

            storage_id = self.env.ref('dms.storage_demo')  # storage

            parent_dir_details = parent_dir_id = False
            if parent_dir_name:
                parent_dir_details, parent_dir_id = self._get_parent_dir_details(parent_dir_name)

            new_dir_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', new_dir_name)],
                                                                                   limit=1)

            if not parent_dir_details and not new_dir_id:
                directory_obj_id = self.env['dms.directory'].create({
                    "name": new_dir_name,
                    "is_root_directory": True,
                    "inherit_group_ids": True,
                    "storage_id": storage_id.id,
                    "storage_id_inherit_access_from_parent_record": storage_id.inherit_access_from_parent_record,
                    "group_ids": [(6, False, [self.env.ref('dms.access_group_01_demo').id])],
                })
            elif parent_dir_details and not new_dir_id:
                parent_dir_details.update({"name": new_dir_name})
                directory_obj_id = self.env['dms.directory'].create(parent_dir_details)
            else:
                directory_obj_id = new_dir_id.write({
                    'name': new_dir_name
                })
            self.env.cr.commit()
            return directory_obj_id

    def _get_parent_dir_details(self, parent_dir_name):
        parent_dir_id = self.env['dms.directory'].with_user(self.env.user).search([
            ('name', '=', parent_dir_name)], limit=1)
        if parent_dir_id.storage_id.save_type == "attachment":
            parent_dir_details = {
                "model_id": parent_dir_id.model_id.id,
                "storage_id": parent_dir_id.storage_id.id,
                "parent_id": parent_dir_id.id,
                "inherit_group_ids": True,
                "storage_id_inherit_access_from_parent_record":
                    parent_dir_id.storage_id.inherit_access_from_parent_record
            }
        else:
            parent_dir_details = {
                "model_id": parent_dir_id.model_id.id,
                "storage_id": parent_dir_id.storage_id.id,
                "parent_id": parent_dir_id.id,
                'group_ids': [(6, False, parent_dir_id.group_ids.ids)],
                "inherit_group_ids": True,
                "storage_id_inherit_access_from_parent_record":
                    parent_dir_id.storage_id.inherit_access_from_parent_record
            }
        return parent_dir_details, parent_dir_id

    def _unlink_dir(self, dir_path):
        try:
            folder_path, folder_name = os.path.split(dir_path)
            directory_obj_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', folder_name)],
                                                                                         limit=1)
            if directory_obj_id:
                directory_obj_id.unlink(os_delete=False)
            self.env.cr.commit()
        except Exception as e:
            _logger.info("Problem: %s", e)

    def _rename_odoo_dir(self, old_dir, new_dir):
        old_dir_path, old_dir_name = os.path.split(old_dir)
        new_dir_path, new_dir_name = os.path.split(new_dir)

        old_dir_id = self.env['dms.directory'].with_user(self.env.user).search([('name', '=', old_dir_name)], limit=1)
        if old_dir_id:
            old_dir_id.write({
                'name': new_dir_name
            })
        self.env.cr.commit()
