import string
from odoo import models, fields, api, _
import os
import base64


ROOT_DIR = os.path.expanduser('/tmp')

class DMSFile(models.Model):
    _inherit = 'dms.file'


    def _sync_with_sftp(self, file_rec):
        """
        Synchronize the file with the SFTP server. document.file(10, )
        """
        path = f"{ROOT_DIR}/{file_rec.path_names}"

        if not os.path.exists(path):
            with open(path, 'wb') as f:
                stream = base64.b64decode(file_rec.content)
                f.write(stream)


    def write(self, vals):
        path = f"{ROOT_DIR}/{self.path_names}"
        if path and os.path.exists(path):
            os.remove(f"{path}")

        rec = super(DMSFile, self).write(vals)
        self._sync_with_sftp(self)
        return rec
        

    @api.model
    def create(self, vals):
        res = super(DMSFile, self).create(vals)
        if vals.get('content'):
            self._sync_with_sftp(res)
        return res
