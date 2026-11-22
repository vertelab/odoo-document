# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""ir.attachment — the single point where bytes leave Odoo.

WHY HERE AND NOT IN dms.file: ``_storage_file_write`` is the only place the
raw bytes are handed to a storage backend. Overriding it covers every
consumer without any of them knowing:

* ``dms.file.content_file`` (the ``attachment=True`` field)
* ``dms_version``'s snapshots — they create their own ``ir.attachment`` with
  ``res_model='dms.file'`` + ``res_id``, so the same lookup finds them
* anything else that stores a file through ``ir.attachment``

Encrypting at ``dms.file`` instead would have left ``dms_version`` writing
PLAINTEXT copies into ``ir.attachment`` — the exact leak the vault exists to
prevent.

THE CHECKSUM DESCRIBES THE PLAINTEXT, DELIBERATELY. ``_get_datas_related_values``
computes ``checksum = sha1(bin_data)`` before ``_file_write``, so the checksum
is the hash of the plaintext even though the stored object is ciphertext. Two
consequences, both intended:

1. ``ir.attachment.checksum`` will not match the hash of the object in the
   bucket. It identifies the document, not its storage encoding.
2. ``_get_fs_path()`` uses the checksum as the object key, so identical files
   share one object even across vaults. That is deduplication, and it is safe:
   the object is ciphertext under a key the sharing party may not hold.

The read side must therefore decrypt before anything compares bytes to the
checksum — which is exactly what ``_storage_file_read`` does.
"""

import base64
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _dms_vault(self):
        """The vault this attachment belongs to, or an empty recordset.

        Empty for every attachment that is not a ``dms.file``'s content, which
        is the overwhelming majority — the lookup is a single indexed browse
        and it must stay cheap.
        """
        if self.res_model != "dms.file" or not self.res_id:
            return self.env["dms.vault"].browse()
        return self.env["dms.vault"].sudo()._vault_for_attachment(self)

    def _file_write(self, bin_data, checksum):
        """Encrypt before the bytes reach the storage backend.

        WHY NOT ``_storage_file_write``: that method only receives the bytes,
        and its return value is the object key. ``_get_datas_related_values``
        stores BOTH ``checksum`` (of the plaintext, deliberately) and
        ``store_fname``. Encrypting one layer down left ``store_fname``
        pointing at the plaintext object's key, so a plaintext copy already on
        disk was read back instead of the ciphertext. Encrypting here means the
        ciphertext is what gets hashed into the key, while the checksum column
        still describes the plaintext.

        The vault arrives through the context (``dms_file_vault_write``), set
        by ``dms.file``'s ``write`` override: this method runs before the
        attachment row exists, so neither ``self`` nor the row can identify the
        document.
        """
        if self._dms_vault_is_key_material():
            return super()._file_write(bin_data, checksum)
        vault = self._dms_vault_for_write()
        if not vault or not bin_data:
            # An empty file has nothing to encrypt, and Fernet refuses an
            # empty plaintext. Storing the empty object as-is leaks nothing.
            return super()._file_write(bin_data, checksum)
        ciphertext = vault._encrypt(bin_data)
        return super()._file_write(
            ciphertext, self._compute_checksum(ciphertext)
        )

    def _dms_vault_for_write(self):
        """The vault of the attachment currently being written.

        ``_storage_file_write`` is ``@api.model`` in ``fs_attachment`` and is
        called on an EMPTY recordset. Worse, it runs BEFORE the attachment row
        exists: ``_get_datas_related_values`` computes ``store_fname`` through
        ``_file_write`` precisely so the row can be created with it. There is
        therefore no attachment id to look up, at any point.

        The only identification available is the context that ``fs_attachment``
        sets around the write: ``attachment_res_model`` and
        ``attachment_res_field``. For ``dms.file.content_file`` the res_model
        is ``dms.file``, and the res_id is the file being written — which is
        in the context too, set by ``dms`` itself (``active_id`` /
        ``default_directory_id``) or by our own ``create``/``write`` override.

        ``dms_file_vault_write`` is set by this module's ``create`` and
        ``write`` overrides and carries the vault id directly; that is the
        reliable path. The res_model/res_field route is the fallback.
        """
        vault_id = self.env.context.get("dms_file_vault_write")
        if vault_id:
            return self.env["dms.vault"].sudo().browse(vault_id).exists()
        # ``_set_attachment_data`` calls ``_get_datas_related_values`` on the
        # recordset it is writing, so ``self`` DOES carry res_model/res_id on
        # the update path (an attachment=True field being re-written). Only
        # the create path arrives empty.
        if self:
            vault = self._dms_vault()
            if vault:
                return vault
        return self._dms_vault_for_res(
            self.env.context.get("attachment_res_model"),
            self.env.context.get("attachment_res_id"),
        ) or self._dms_vault_for_directory(
            self.env.context.get("dms_file_directory_id")
        )

    @api.model_create_multi
    def create(self, vals_list):
        """Carry the vault into the write of an ``attachment=True`` field.

        A Binary field with ``attachment=True`` creates its attachment through
        ``ir.attachment.create``, which does NOT go through ``dms.file.write``
        and therefore loses the context that names the vault. The vault is
        recovered from the ``res_model``/``res_id`` in the values — for
        ``dms.file.content_file`` that is the file being written.
        """
        vault = self.env["dms.vault"].browse()
        for vals in vals_list:
            if vals.get("res_model") == "dms.file" and vals.get("res_id"):
                vault = self._dms_vault_for_res(
                    vals["res_model"], vals["res_id"]
                )
                break
        if not vault:
            # A Binary field on dms.file does not always carry res_model in
            # vals; the vault is then in the context, set by dms.file.write.
            vault = self._dms_vault_for_write()
        if not vault:
            return super().create(vals_list)
        # ``_get_datas_related_values`` runs ``_file_write`` on an EMPTY
        # recordset before the row exists, so the context is the only channel
        # that reaches it. Set it here, where the vault is known.
        return super(
            IrAttachment,
            self.with_context(dms_file_vault_write=vault.id),
        ).create(vals_list)

    def _dms_vault_for_res(self, res_model, res_id):
        """The vault of a ``dms.file`` by its own id, if it has one.

        Reads the DIRECTORY rather than ``dms_file.vault_id``: that field is a
        stored related, and during a migration the directory is changed and
        the bytes written in the same transaction — the related value in the
        database is still the old one when ``content_file`` is created.
        """
        if res_model != "dms.file" or not res_id:
            return self.env["dms.vault"].browse()
        dms_file = self.env["dms.file"].sudo().browse(res_id).exists()
        if not dms_file:
            return self.env["dms.vault"].browse()
        return dms_file.directory_id.vault_id or dms_file.vault_id

    def _dms_vault_for_directory(self, directory_id):
        """The vault of the directory a file is being written into."""
        if not directory_id:
            return self.env["dms.vault"].browse()
        directory = self.env["dms.directory"].sudo().browse(directory_id).exists()
        return directory.vault_id if directory else self.env["dms.vault"].browse()

    def _storage_file_read(self, fname):
        """Decrypt what the storage backend returns for a vault attachment.

        Unlike the write path, the read runs on a record that EXISTS, so the
        vault is resolved from ``self`` (res_model + res_id). The context is
        only a fallback for a caller that already knows the vault.
        """
        data = super()._storage_file_read(fname)
        if self._dms_vault_is_key_material():
            return data
        vault = self._dms_vault() or self._dms_vault_for_write()
        if not vault or not data:
            return data
        return vault._decrypt(data)

    def _dms_vault_is_key_material(self):
        """True for the vault's own key fields — never encrypted, never read
        through the vault.

        ``dms.vault.content_key`` and ``dms.vault.key.wrapped_key`` are Binary
        fields, so they are stored as ``ir.attachment`` rows like any other
        file. Encrypting them would be circular: the key that decrypts a vault
        cannot itself be encrypted under that vault's key. Reading them through
        the vault layer would also recurse.
        """
        return self.res_field in ("content_key", "wrapped_key")

    def _dms_vault_raw_is_ciphertext(self):
        """Whether the stored object is Fernet ciphertext, without decrypting.

        Used by the migration check, which must not raise on a plaintext file
        — the whole point is to FIND the plaintext ones. A Fernet token is
        ``version(1) || timestamp(8) || iv(16) || ciphertext || hmac(32)``,
        urlsafe-base64 encoded, and always starts with the version byte
        ``0x80``. A plaintext document does not.

        This is a shape test, not a proof. It can only be wrong in the
        direction of calling a genuine Fernet token "plaintext" (which costs a
        redundant re-write) or a plaintext file "ciphertext" (which would need
        a document that happens to start with exactly that header).
        """
        self.ensure_one()
        if not self.store_fname:
            return False
        raw = self.env["ir.attachment"]._storage_file_read_raw(self.store_fname)
        if not raw:
            return False
        try:
            token = base64.urlsafe_b64decode(raw)
        except (ValueError, TypeError):
            return False
        return len(token) > 57 and token[:1] == b"\x80"

    @api.model
    def _storage_file_read_raw(self, fname):
        """Read a stored object WITHOUT the vault's decryption.

        The vault decrypts in ``_storage_file_read`` for every attachment that
        belongs to a vault. The migration check needs the bytes as they are on
        disk, so it calls the storage layer directly and skips the override.
        """
        return super(IrAttachment, self)._storage_file_read(fname)
