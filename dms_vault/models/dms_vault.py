# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""dms.vault — the key hierarchy.

    master (odoo.conf: dms_vault_master_key)
      -> member_key  = HKDF-SHA256(master, info="vault-member:<uid>")
      -> content_key = random 32 bytes, one per vault, wrapped per member
      -> file bytes  = Fernet(content_key)

WHY THREE LEVELS AND NOT ONE: onboarding and offboarding must not touch
files. Adding a member writes one row (wrap the *existing* content key with
the new member's key); removing a member writes one row (blank the wrapped
key). The content key never changes, so no file is ever re-encrypted for a
membership change.

WHY HKDF AND NOT A STORED MEMBER KEY: a stored member key would have to be
delivered out of band and could be lost. Deriving it from the master means
there is nothing to deliver and nothing to lose. The cost is that the master
key alone decrypts everything — which is already true for the threat model
(a database dump without ``odoo.conf``), so it costs nothing extra.

THE MASTER KEY IS NEVER RETURNED TO A CALLER THAT DOES NOT NEED IT. It is
read from the configuration on demand, never stored on a record, never
logged, never written to the database.
"""

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import config

_logger = logging.getLogger(__name__)

CONFIG_KEY = "dms_vault_master_key"

GENERATE_COMMAND = (
    'python3 -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)

#: HKDF info prefix. The member key is derived from the master with this
#: string and the user id, so the same master gives a distinct key per user
#: and no user can derive another user's key.
MEMBER_INFO = "vault-member:%s"

#: The salt is empty on purpose: HKDF's security comes from the info
#: parameter here, and a fixed salt keeps the derivation reproducible across
#: hosts and restarts. A random salt would have to be stored alongside the
#: wrapped key, which buys nothing for a single-secret hierarchy.
HKDF_SALT = b""


def get_master_key(env=None):
    """Return the master key from ``odoo.conf``, or raise.

    Read from ``odoo.tools.config`` and NOT from ``ir.config_parameter``: the
    whole point of the key is that it is not in the database. A parameter
    would be in the dump, and the dump is what the vault protects against.

    Fails closed: there is no default and no generated fallback. A generated
    fallback would silently encrypt files under a key that disappears on the
    next restart, which is worse than refusing to work — the data would be
    unrecoverable and nobody would know until the first read.

    ``env`` is accepted for call-site symmetry with the model methods and is
    unused.
    """
    raw = config.get(CONFIG_KEY)
    if not raw:
        raise ValidationError(
            _(
                "The configuration key '%(key)s' is not set.\n\n"
                "dms_vault needs a master key in odoo.conf, outside the "
                "database. Without it nothing can be encrypted or decrypted, "
                "and losing it makes every vault file unrecoverable.\n\n"
                "Generate one with:\n  %(command)s\n\n"
                "and add it to odoo.conf as:\n  %(key)s = <the key>",
                key=CONFIG_KEY,
                command=GENERATE_COMMAND,
            )
        )
    # The configured value IS a Fernet key: urlsafe-base64 of 32 bytes.
    # Return it as bytes, ready for Fernet(). It must NOT be passed through
    # _fernet(), which base64-encodes raw key material — doing that to an
    # already-encoded key produces 44 bytes and Fernet rejects it.
    return raw.strip().encode()


def member_key(env, user_id):
    """Derive the key of one member from the master key.

    ``user_id`` is part of the HKDF ``info``, so the derivation is one-way and
    per-user: holding member A's key says nothing about member B's.
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=HKDF_SALT,
        info=(MEMBER_INFO % user_id).encode(),
    ).derive(get_master_key(env))


def _fernet(key):
    """Build a Fernet from either shape of key.

    Two shapes reach this function and they must not be confused:

    * the MASTER key, which is already urlsafe-base64 (a valid Fernet key)
    * a DERIVED or CONTENT key, which is raw 32 bytes from HKDF or os.urandom

    Base64-encoding an already-encoded key yields 44 bytes and Fernet raises
    "Fernet key must be 32 url-safe base64-encoded bytes". Decoding a valid
    Fernet key instead raises inside base64. So: try to decode; if it decodes
    to exactly 32 bytes it was already a Fernet key, otherwise treat the input
    as raw key material.
    """
    if isinstance(key, str):
        key = key.encode()
    try:
        decoded = base64.urlsafe_b64decode(key)
    except (ValueError, TypeError):
        decoded = None
    if decoded is not None and len(decoded) == 32:
        return Fernet(key)
    return Fernet(base64.urlsafe_b64encode(key))


class DmsVault(models.Model):
    _name = "dms.vault"
    _description = "DMS Vault"

    name = fields.Char(required=True)
    directory_id = fields.Many2one(
        "dms.directory",
        string="Directory",
        required=True,
        ondelete="cascade",
        index=True,
        help="The directory whose files are encrypted.",
    )
    storage_id = fields.Many2one(
        "dms.storage",
        string="Storage",
        related="directory_id.storage_id",
        store=True,
        readonly=True,
    )
    content_key = fields.Binary(
        string="Content Key (wrapped)",
        readonly=True,
        copy=False,
        help="The vault's content key, encrypted with the master key.\n"
             "Never the raw key: the raw key exists only in memory during a "
             "request and is never persisted.",
    )
    key_ids = fields.One2many(
        "dms.vault.key",
        "vault_id",
        string="Members",
    )
    member_count = fields.Integer(compute="_compute_member_count")
    file_count = fields.Integer(compute="_compute_file_count")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "directory_uniq",
            "unique(directory_id)",
            "A directory can only be one vault.",
        ),
    ]

    @api.depends("key_ids.state")
    def _compute_member_count(self):
        for record in self:
            record.member_count = len(
                record.key_ids.filtered(lambda k: k.state == "active")
            )

    @api.depends("directory_id")
    def _compute_file_count(self):
        for record in self:
            record.file_count = self.env["dms.file"].search_count(
                [("directory_id", "=", record.directory_id.id)]
            )

    # ── The content key ────────────────────────────────────────────────

    def _generate_content_key(self):
        """Create a fresh random content key and store it wrapped.

        Wrapped with the master key itself, not with a member key: the master
        is the only key guaranteed to exist at creation time, before any
        member has been added. Members get their own wrapping on onboarding.
        """
        self.ensure_one()
        raw = os.urandom(32)
        # Fernet returns raw token bytes; a Binary field stores base64.
        token = _fernet(get_master_key(self.env)).encrypt(raw)
        self.write({"content_key": base64.b64encode(token)})
        self.invalidate_recordset(["content_key"])
        return raw

    def _read_content_key(self):
        """Read the wrapped content key straight from its attachment.

        A Binary field is backed by an ``ir.attachment`` row, and the ORM
        cache for it is not populated by a ``write()`` on the same record in
        the same transaction. Reading the attachment directly is the only way
        to be sure the key that was just written is the key that is used.
        """
        self.ensure_one()
        attachment = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("res_field", "=", "content_key"),
            ],
            limit=1,
        )
        if not attachment:
            return b""
        # ``raw`` is already the decoded bytes of what we wrote into the
        # Binary field — the field layer did the base64 decode. Decoding again
        # raises "Incorrect padding".
        # ``raw`` goes through _storage_file_read, which this module overrides
        # to decrypt. The vault's own key material must never be decrypted, so
        # read the object straight from the storage layer.
        return attachment._storage_file_read_raw(attachment.store_fname) or b""

    def _unwrap_content_key(self):
        """Return the vault's raw content key.

        Unwrapped with the master key; the per-member wrapping is what a
        member uses to prove they may have it (see ``dms.vault.key``), and the
        check happens in ``_content_key_for_user``.
        """
        self.ensure_one()
        wrapped = self._read_content_key()
        if not wrapped:
            raise ValidationError(
                _("Vault '%s' has no content key.", self.name)
            )
        try:
            return _fernet(get_master_key(self.env)).decrypt(wrapped)
        except InvalidToken:
            raise ValidationError(
                _(
                    "The content key of vault '%(vault)s' cannot be unwrapped "
                    "with the configured master key. Either '%(key)s' was "
                    "changed, or this vault was encrypted under another key. "
                    "There is no recovery path for the files in it.",
                    vault=self.name,
                    key=CONFIG_KEY,
                )
            )

    def _content_key_for_user(self, user_id):
        """Return the content key, but only if ``user_id`` is an active member.

        This is the membership check. It is deliberately the only way the
        encryption layer obtains a content key, so a user who is not a member
        cannot read a vault file even if they can read the attachment row.
        """
        self.ensure_one()
        member = self.key_ids.filtered(
            lambda k, uid=user_id: k.user_id.id == uid and k.state == "active"
        )
        if not member:
            raise ValidationError(
                _(
                    "You are not a member of the vault '%s'. Ask an "
                    "administrator to add you before opening its files.",
                    self.name,
                )
            )
        return self._unwrap_content_key()

    # ── Wrapping per member ────────────────────────────────────────────

    def _wrap_content_key(self, user):
        """Return the vault's content key encrypted under ``user``'s key."""
        self.ensure_one()
        raw = self._unwrap_content_key()
        # Fernet returns raw token bytes; a Binary field stores base64.
        token = _fernet(member_key(self.env, user.id)).encrypt(raw)
        return base64.b64encode(token)

    def _unwrap_content_key_for(self, user):
        """Return the content key that ``user``'s wrapping holds.

        Used by the membership test: a revoked member has no wrapping, so the
        test fails for the right reason rather than by accident.
        """
        self.ensure_one()
        member = self.key_ids.filtered(
            lambda k, uid=user.id: k.user_id.id == uid and k.state == "active"
        )
        if not member or not member.wrapped_key:
            raise ValidationError(
                _("User '%(user)s' has no active key for vault '%(vault)s'.",
                  user=user.name, vault=self.name)
            )
        wrapped = base64.b64decode(member.wrapped_key)
        try:
            return _fernet(member_key(self.env, user.id)).decrypt(wrapped)
        except InvalidToken:
            raise ValidationError(
                _("The wrapped key of '%(user)s' for vault '%(vault)s' does "
                  "not unwrap with the configured master key.",
                  user=user.name, vault=self.name)
            )

    # ── Encryption of the bytes ────────────────────────────────────────

    def _encrypt(self, raw, user_id=None):
        """Encrypt ``raw`` with this vault's content key."""
        self.ensure_one()
        key = self._content_key_for_user(user_id or self.env.uid)
        return _fernet(key).encrypt(raw)

    def _decrypt(self, token, user_id=None):
        """Decrypt ``token`` with this vault's content key."""
        self.ensure_one()
        key = self._content_key_for_user(user_id or self.env.uid)
        try:
            return _fernet(key).decrypt(token)
        except InvalidToken:
            raise ValidationError(
                _(
                    "The stored bytes of vault '%s' cannot be decrypted with "
                    "its content key. The file is either corrupt or was "
                    "written under a different key.",
                    self.name,
                )
            )

    # ── Lookup from the attachment layer ───────────────────────────────

    @api.model
    def _vault_for_attachment(self, attachment):
        """Return the vault an attachment belongs to, or an empty recordset.

        The lookup is ``res_model='dms.file'`` + ``res_id`` -> the file's
        ``vault_id``. It runs on the record and not on the path because a
        storage path does not say which vault (if any) wrote it.

        ``dms_version`` creates its snapshots with the same ``res_model`` and
        ``res_id`` as the file, so a version's attachment resolves to the
        file's vault without a field of its own.
        """
        if attachment.res_model != "dms.file" or not attachment.res_id:
            return self.browse()
        dms_file = (
            self.env["dms.file"]
            .sudo()
            .browse(attachment.res_id)
            .exists()
        )
        if not dms_file:
            return self.browse()
        return dms_file.vault_id

    # ── Onboarding / offboarding ───────────────────────────────────────

    def action_add_member(self):
        """Open the wizard that adds one member."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Add Member"),
            "res_model": "dms.vault.member.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_vault_id": self.id, "default_mode": "add"},
        }

    def action_remove_member(self):
        """Open the wizard that revokes one member."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Remove Member"),
            "res_model": "dms.vault.member.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_vault_id": self.id, "default_mode": "remove"},
        }

    def action_migrate_files(self):
        """Open the migration wizard for this vault."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Migrate Files into Vault"),
            "res_model": "dms.vault.migrate.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_vault_id": self.id},
        }


class DmsVaultKey(models.Model):
    """One member's wrapping of a vault's content key.

    Onboarding is a create; offboarding is a write that blanks
    ``wrapped_key``. Neither touches a single file.
    """

    _name = "dms.vault.key"
    _description = "DMS Vault Member Key"

    vault_id = fields.Many2one(
        "dms.vault",
        string="Vault",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        ondelete="cascade",
        index=True,
    )
    wrapped_key = fields.Binary(
        string="Wrapped Key",
        readonly=True,
        copy=False,
        help="The vault's content key, encrypted under this member's key.\n"
             "Cleared on revocation — keeping it would keep the member able "
             "to decrypt everything they can still download.",
    )
    state = fields.Selection(
        [("active", "Active"), ("revoked", "Revoked")],
        default="active",
        required=True,
        index=True,
    )
    revoked_date = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "vault_user_uniq",
            "unique(vault_id, user_id)",
            "A user can only have one key per vault.",
        ),
    ]

    @api.model
    def _grant(self, vault, user):
        """Onboard ``user``: one row, no file touched.

        Idempotent: re-adding a revoked member re-wraps the same content key,
        so their access comes back without any file being rewritten.
        """
        vault.ensure_one()
        wrapped = vault._wrap_content_key(user)
        member = self.search(
            [("vault_id", "=", vault.id), ("user_id", "=", user.id)], limit=1
        )
        if member:
            member.write({
                "wrapped_key": wrapped,
                "state": "active",
                "revoked_date": False,
            })
        else:
            member = self.create({
                "vault_id": vault.id,
                "user_id": user.id,
                "wrapped_key": wrapped,
                "state": "active",
            })
        return member

    def _revoke(self):
        """Offboard: blank the wrapped key. No file is touched.

        The content key is unchanged on purpose — re-keying the vault would
        mean re-encrypting every file, which is exactly what the three-level
        hierarchy exists to avoid.
        """
        for member in self:
            member.write({
                "wrapped_key": False,
                "state": "revoked",
                "revoked_date": fields.Datetime.now(),
            })
        return True
