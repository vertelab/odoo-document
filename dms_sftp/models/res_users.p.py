from odoo import fields, models
from odoo.exceptions import AccessDenied


class ResUsers(models.Model):
    _inherit = "res.users"

    # #if VERSION >= "20.0"
    # 20.0: SELF_WRITEABLE_FIELDS/SELF_READABLE_FIELDS are gone. A field a
    # user may change on their own record declares it on the field instead.
    authorized_keys = fields.Text(
        "Authorized keys",
        help="An authorized key file as in ~/.ssh/authorized_keys",
        user_writeable=True,
    )
    # #else
    authorized_keys = fields.Text(
        "Authorized keys",
        help="An authorized key file as in ~/.ssh/authorized_keys",
    )

    def _register_hook(self):
        if "authorized_keys" not in self.SELF_WRITEABLE_FIELDS:
            self.SELF_WRITEABLE_FIELDS.append("authorized_keys")
            self.SELF_READABLE_FIELDS.append("authorized_keys")
        return super()._register_hook()
    # #endif

    def _verify_sftp_user(self, password):
        try:
            self._check_credentials({'type': 'password', 'password': password}, self.env)
            return True
        except AccessDenied:
            return False
