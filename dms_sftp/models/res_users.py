from odoo import fields, models
from odoo.exceptions import AccessDenied


class ResUsers(models.Model):
    _inherit = "res.users"

    authorized_keys = fields.Text(
        "Authorized keys",
        help="An authorized key file as in ~/.ssh/authorized_keys",
    )

    def _register_hook(self):
        if "authorized_keys" not in self.SELF_WRITEABLE_FIELDS:
            self.SELF_WRITEABLE_FIELDS.append("authorized_keys")
            self.SELF_READABLE_FIELDS.append("authorized_keys")
        return super()._register_hook()

    def _verify_sftp_user(self, password):
        try:
            self._check_credentials({'type': 'password', 'password': password}, self.env)
            return True
        except AccessDenied:
            return False
