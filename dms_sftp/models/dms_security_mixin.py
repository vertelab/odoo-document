# Copyright 2017-2019 MuK IT GmbH.
# Copyright 2020 Creu Blanca
# Copyright 2021 Tecnativa - Víctor Martínez
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
import os
import logging
import base64
from odoo import api, models, tools

from odoo.addons.dms.models.dms_security_mixin import DmsSecurityMixin as DMsSecurity

_logger = logging.getLogger(__name__)

ROOT_DIR = os.path.expanduser('/tmp')


class DmsSecurityMixinExtended(models.AbstractModel):
    _inherit = 'dms.security.mixin'

    def create(self, vals_list):
        if vals_list[0].get('storage_id'):
            vals_list[0].update({
                'company_id': self.env.company.id,
                'image_1024': False,
                'image_256': False,
                'storage_id_inherit_access_from_parent_record': True
            })
        # Create as sudo to avoid testing creation permissions before DMS security
        # groups are attached (otherwise nobody would be able to create)
        res = super(DMsSecurity, self.sudo()).create(vals_list)
        # Need to flush now, so all groups are stored in DB and the SELECT used
        # to check access works
        # res.flush()
        # Go back to original sudo state and check we really had creation permission
        res = res.sudo(self.env.su)
        # res.check_access_rights("create")
        # res.check_access_rule("create")
        return res


class DmsDirectory(models.Model):
    _inherit = 'dms.directory'

    def unlink(self, ok=True):
        """Custom cascade unlink.

        Cannot rely on DB backend's cascade because subfolder and subfile unlinks
        must check custom permissions' implementation.
        """
        self.file_ids.unlink()
        if self.child_directory_ids:
            if ok:
                self.remove_remote_dir()
            self.child_directory_ids.unlink()
        if ok:
            self.remove_remote_dir()
        return super().unlink()

    def remove_remote_dir(self):
        if self.complete_name:
            complete_name = self.complete_name.replace(' ', '')
            path = f"{ROOT_DIR}/{complete_name}"
            if path and os.path.exists(path):
                os.rmdir(f"{path}")

    def _sync_with_sftp(self, path_names):
        """
        Synchronize the file with the SFTP server. document.file(10, )
        """
        if path_names:
            os.mkdir(path_names)
        # with open(path, 'wb') as f:
        #     stream = base64.b64decode(content)
        #     f.write(stream)

    @api.model
    def create(self, vals):
        vals.update({
            'company_id': self.env.company.id,
            'image_1024': False,
            'image_256': False,
            'storage_id_inherit_access_from_parent_record': True
        })
        res = super(DmsDirectory, self).create(vals)
        if res:
            complete_name = res.complete_name.replace(' ', '')
            path = f"{ROOT_DIR}/{complete_name}"
            if vals.get('inherit_group_ids'):
                self._sync_with_sftp(path_names=path)
        return res

    def write(self, vals):
        if vals.get('complete_name'):
            new_complete_name = vals.get('complete_name').replace(' ', '')
            old_complete_name = self.complete_name.replace(' ', '')
            new_path = f"{ROOT_DIR}/{new_complete_name}"
            old_path = f"{ROOT_DIR}/{old_complete_name}"
            os.rename(old_path, new_path)
        res = super(DmsDirectory, self).write(vals)
        return res
