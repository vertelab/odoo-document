# -*- coding: utf-8 -*-
# © 2016 Therp BV <http://therp.nl>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # #if VERSION >= "20.0"
    # 20.0: SELF_WRITEABLE_FIELDS/SELF_READABLE_FIELDS are gone. A field a
    # user may change on their own record declares it on the field instead.
    authorized_keys = fields.Text(
        'Authorized keys',
        help='An authorized key file as in ~/.ssh/authorized_keys',
        user_writeable=True,
    )
    # #else
    authorized_keys = fields.Text(
        'Authorized keys',
        help='An authorized key file as in ~/.ssh/authorized_keys')

    def _register_hook(self):
        if 'authorized_keys' not in self.SELF_WRITEABLE_FIELDS:
            self.SELF_WRITEABLE_FIELDS.append('authorized_keys')
            self.SELF_READABLE_FIELDS.append('authorized_keys')
        return super(ResUsers, self)._register_hook()
    # #endif

    def _verify_sftp_user(self, password):
        assert password
        self.env.cr.execute(
            "SELECT COALESCE(password, '') FROM res_users WHERE id=%s",
            [self.env.user.id]
        )
        [hashed] = self.env.cr.fetchone()
        valid, replacement = self._crypt_context().verify_and_update(password, hashed)
        return valid
