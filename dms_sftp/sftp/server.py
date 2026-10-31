import base64
import logging

from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.exceptions import AccessDenied

try:
    from paramiko.common import AUTH_SUCCESSFUL, AUTH_FAILED, \
        OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED, OPEN_SUCCEEDED
    from paramiko import RSAKey, ServerInterface
except ImportError:
    pass

_logger = logging.getLogger(__name__)


class DmsSftpServer(ServerInterface):
    def __init__(self, dbname):
        self.dbname = dbname
        self._env = None
        super().__init__()

    def _get_env(self):
        if self._env is None:
            db_registry = Registry.new(self.dbname)
            cr = db_registry.cursor()
            self._env = api.Environment(cr, SUPERUSER_ID, {})
        return self._env

    env = property(_get_env)

    def __del__(self):
        if self._env is not None:
            try:
                self._env.cr.close()
            except Exception:
                pass

    def check_auth_password(self, username, password):
        """Authenticate a password login.

        The database is fixed when the server starts and never changed here.
        The previous implementation called db.exp_list() and, on a login of the
        form user@domain, reconnected the whole session to whichever database
        happened to hold that login. That made the database a property of the
        login attempt rather than of the connection: a typo, or a login that
        exists in two databases, silently served another customer's data.

        A user@domain login is still accepted, but only as a login name - the
        domain no longer selects a database.
        """
        user_login = username
        try:
            user = self.env["res.users"].search([("login", "=", user_login)])
            if not user:
                return AUTH_FAILED
            valid = user.with_user(user.id)._verify_sftp_user(password)
            if valid:
                db_registry = Registry.new(self.dbname)
                with db_registry.cursor() as cr:
                    self.env = api.Environment(cr, user.id, {})
                _logger.info("SFTP auth: user=%s db=%s", user_login, self.dbname)
                return AUTH_SUCCESSFUL
        except AccessDenied:
            pass
        return AUTH_FAILED

    def check_auth_publickey(self, username, key):
        user = self.env["res.users"].search([("login", "=", username)])
        if not user:
            return AUTH_FAILED
        for line in (user.authorized_keys or "").split("\n"):
            if not line or line.startswith("#"):
                continue
            key_type, key_data = line.split(" ", 2)[:2]
            if key_type != "ssh-rsa":
                continue
            if RSAKey(data=base64.b64decode(key_data)) == key:
                return AUTH_SUCCESSFUL
        return AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_channel_request(self, kind, chanid):
        if kind in ("session",):
            return OPEN_SUCCEEDED
        return OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
