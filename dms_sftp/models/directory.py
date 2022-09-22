import os
import logging
import shutil
from odoo import api, models, tools

_logger = logging.getLogger(__name__)

ROOT_DIR = os.path.expanduser('/tmp')


class DmsDirectory(models.Model):
    _inherit = 'dms.directory'

    def _storage_location(self):
        sftp_storage_location = f"{ROOT_DIR}/{self.env.user.login}"
        return sftp_storage_location

    def _sync_with_sftp(self, path_names):
        """
        Synchronize the file with the SFTP server. document.file(10, )
        """
        if path_names:
            os.mkdir(path_names)

    def unlink(self, os_delete=True):
        """Custom cascade unlink.

        Cannot rely on DB backend's cascade because subfolder and subfile unlinks
        must check custom permissions' implementation.
        """
        self.file_ids.unlink()
        if self.child_directory_ids:
            if os_delete:
                self.remove_remote_dir()
            self.child_directory_ids.unlink()
        if os_delete:
            self.remove_remote_dir()
        return super().unlink()

    def remove_remote_dir(self):
        if self.complete_name:
            complete_name = self.complete_name.replace(' ', '')
            path = f"{self._storage_location()}/{complete_name}"
            if path and os.path.exists(path):
                shutil.rmtree(f"{path}", ignore_errors=True)

    @api.model
    def create(self, vals):
        vals.update({
            'company_id': self.env.company.id,
            'image_1024': False,
            'image_256': False,
            'is_hidden': False
        })
        res = super(DmsDirectory, self.sudo()).create(vals)
        if res:
            complete_name = res.complete_name.replace(' ', '')
            path = f"{self._storage_location()}/{complete_name}"
            if vals.get('__last_update'):
                self._sync_with_sftp(path_names=path)
        return res

    def write(self, vals):
        if vals.get('complete_name'):
            new_complete_name = vals.get('complete_name').replace(' ', '')
            old_complete_name = self.complete_name.replace(' ', '')
            new_path = f"{self._storage_location()}/{new_complete_name}"
            old_path = f"{self._storage_location()}/{old_complete_name}"
            os.rename(old_path, new_path)
        res = super(DmsDirectory, self).write(vals)
        return res
