import logging

from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.exceptions import AccessDenied
from odoo.service import db

try:
    from paramiko.common import AUTH_SUCCESSFUL, AUTH_FAILED, \
        OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED, OPEN_SUCCEEDED
    from paramiko import RSAKey, ServerInterface
    from paramiko.py3compat import decodebytes
except ImportError:
    pass

_logger = logging.getLogger(__name__)


class DmsSftpServer(ServerInterface):
    def __init__(self, env):
        self.env = env
        self.dbname = env.cr.dbname
        super().__init__()

    def check_auth_password(self, username, password):
        user_login = username
        db_name = self.dbname

        if "@" in username:
            user_login, domain = username.rsplit("@", 1)
            db_candidate = domain.rsplit(".", 1)[0] if "." in domain else domain
            all_dbs = db.exp_list()
            if db_candidate in all_dbs:
                db_name = db_candidate
            elif domain in all_dbs:
                db_name = domain
            else:
                for candidate_db in all_dbs:
                    try:
                        db_registry = Registry.new(candidate_db)
                        with api.Environment.manage(), db_registry.cursor() as cr:
                            env = api.Environment(cr, SUPERUSER_ID, {})
                            user = env["res.users"].search([("login", "=", user_login)])
                            if not user:
                                continue
                            valid = user.with_user(user.id)._verify_sftp_user(password)
                            if valid:
                                with api.Environment.manage(), db_registry.cursor() as cr:
                                    self.env = api.Environment(cr, user.id, {})
                                _logger.info(
                                    "SFTP auth: user=%s db=%s (fallback)",
                                    user_login, candidate_db,
                                )
                                return AUTH_SUCCESSFUL
                    except Exception:
                        continue
                return AUTH_FAILED

        try:
            user = self.env["res.users"].search([("login", "=", user_login)])
            if not user:
                return AUTH_FAILED
            valid = user.with_user(user.id)._verify_sftp_user(password)
            if valid:
                db_registry = Registry.new(db_name)
                with api.Environment.manage(), db_registry.cursor() as cr:
                    self.env = api.Environment(cr, user.id, {})
                _logger.info("SFTP auth: user=%s db=%s", user_login, db_name)
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
            if RSAKey(data=decodebytes(key_data)) == key:
                return AUTH_SUCCESSFUL
        return AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_channel_request(self, kind, chanid):
        if kind in ("session",):
            return OPEN_SUCCEEDED
        return OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
