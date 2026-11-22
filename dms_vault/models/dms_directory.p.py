# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""dms.directory — the vault flag and the two guards it carries.

``is_vault`` is not a preference. Turning it on writes ``extract_enabled =
False`` in the SAME write, because a vault file's content decrypts on read
and the extractor would happily index plaintext. One setting is not enough
(``dms_extract`` also checks ``vault_id`` in code), but the setting is the
one a user sees, so it must not be left lying.

``_check_vault_storage`` refuses a storage without filename obfuscation. A
vault that stores ``Persongalleri-korrektur.docx`` as an object key has leaked
the filename to anyone who can list the bucket, which defeats a large part of
the purpose. The vault cannot fix this from ``ir.attachment`` — it is a
property of the storage — so it refuses instead.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    is_vault = fields.Boolean(
        string="Vault",
        default=False,
        copy=False,
        help="Encrypt every file in this directory before it reaches "
             "storage.\n"
             "WHAT IS LOST: no search, no preview without decryption, no "
             "re-scanning after the fact, and no recovery if the master key "
             "is lost. Read the module README before turning this on.",
    )
    vault_id = fields.Many2one(
        "dms.vault",
        string="Vault Record",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )

    @api.constrains("is_vault", "storage_id")
    def _check_vault_storage(self):
        """A vault's storage must obfuscate filenames."""
        for record in self:
            if not record.is_vault:
                continue
            record._assert_storage_obfuscates()

    def _assert_storage_obfuscates(self):
        """Raise unless the storage hides the filename in the object key."""
        self.ensure_one()
        storage = self.storage_id
        if not storage:
            return
        code = storage._dms_attachment_storage_code()
        if not code:
            # The files are not stored through fs_attachment at all (save_type
            # 'database' keeps them in the database, where the vault's
            # encryption still applies). There is no object key to leak.
            return
        fs_storage = self.env["fs.storage"].sudo().get_by_code(code)
        if fs_storage and not fs_storage.use_filename_obfuscation:
            raise ValidationError(
                _(
                    "The storage '%(storage)s' does not obfuscate filenames.\n\n"
                    "A vault stores ciphertext, but an object key built from "
                    "the filename still exposes the document name to anyone "
                    "who can list the bucket. Turn on 'Use Filename "
                    "Obfuscation' on the storage '%(fs)s' before making this "
                    "directory a vault.",
                    storage=storage.name,
                    fs=fs_storage.name,
                )
            )

    def write(self, vals):
        """Keep ``is_vault``, ``extract_enabled`` and the vault row in step."""
        if "is_vault" in vals and vals["is_vault"]:
            # The storage check runs before anything is written: a directory
            # must never end up flagged as a vault on a storage that leaks
            # filenames, not even for the duration of one transaction.
            for record in self:
                record._assert_storage_obfuscates()
            # extract_enabled is forced in the SAME write. A separate write
            # would leave a window (and a crash path) where the directory is a
            # vault and still extracts.
            vals = dict(vals, extract_enabled=False)
        res = super().write(vals)
        if vals.get("is_vault"):
            self._dms_vault_ensure()
        elif "is_vault" in vals and not vals["is_vault"]:
            self._dms_vault_drop()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """A directory created as a vault gets the same treatment as a write."""
        for vals in vals_list:
            if vals.get("is_vault"):
                vals.setdefault("extract_enabled", False)
        records = super().create(vals_list)
        records.filtered("is_vault")._dms_vault_ensure()
        return records

    def _dms_vault_ensure(self):
        """Create the ``dms.vault`` row for every directory that lacks one."""
        Vault = self.env["dms.vault"].sudo()
        for record in self:
            if record.vault_id:
                continue
            vault = Vault.create({
                "name": record.complete_name or record.name,
                "directory_id": record.id,
            })
            vault._generate_content_key()
            # The creator is the first member: a vault nobody can open is not
            # a feature, and the person who made it is the one who can hand
            # out access.
            if self.env.uid != self.env.ref("base.public_user").id:
                self.env["dms.vault.key"].sudo()._grant(vault, self.env.user)
            record.vault_id = vault
            _logger.info(
                "dms_vault: directory %s (%s) is now a vault (id=%s)",
                record.id, record.complete_name, vault.id,
            )

    def _dms_vault_drop(self):
        """Unset the flag: keep the vault row, but stop claiming encryption.

        The row is kept on purpose. Deleting it would discard the content key,
        and any file still encrypted under it would become unreadable with no
        trace of why. Turning the flag off is "stop encrypting new writes",
        not "forget the key".
        """
        for record in self:
            if record.vault_id:
                _logger.warning(
                    "dms_vault: directory %s (%s) is no longer flagged as a "
                    "vault, but vault %s and its content key are kept. Files "
                    "already encrypted stay encrypted.",
                    record.id, record.complete_name, record.vault_id.id,
                )
