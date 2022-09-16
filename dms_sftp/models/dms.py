import string
from odoo import models, fields, api, _
import os
import base64

ROOT_DIR = os.path.expanduser('/tmp')


class DMSFile(models.Model):
    _inherit = 'dms.file'

    def _storage_location(self):
        sftp_storage_location = ROOT_DIR
        return sftp_storage_location

    def _sync_with_sftp(self, path_names, content):
        """
        Synchronize the file with the SFTP server. document.file(10, )
        """
        path = f"{self._storage_location()}/{path_names}"
        with open(path, 'wb') as f:
            stream = base64.b64decode(content)
            f.write(stream)

    def write(self, vals):
        full_path = f"{self._storage_location()}/{self.path_names}"
        if vals and os.path.exists(full_path):
            os.remove(path=full_path)
        rec = super(DMSFile, self).write(vals)
        if vals.get('content') or vals.get('name'):
            self._sync_with_sftp(path_names=self.path_names, content=self.content)
        return rec

    @api.model
    def create(self, vals):
        res = super(DMSFile, self).create(vals)
        if vals.get('content'):
            self._sync_with_sftp(path_names=res.path_names, content=res.content)
        return res

    def unlink(self, ok=True):
        for rec in self:
            path = f"{self._storage_location()}/{rec.path_names}"
            if path and os.path.exists(path) and ok:
                os.remove(f"{path}")
        return super(DMSFile, self).unlink()
