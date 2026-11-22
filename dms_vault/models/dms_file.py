# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""dms.file — the vault a file belongs to, and the migration guard.

``vault_id`` is a stored related field on the directory. Stored because both
the extractor and the OKF mixin filter on it in SQL, and because the
attachment layer resolves it for every write.

``needs_vault_migration`` answers a question the existing fields cannot:
``require_migration`` compares save types and says nothing about encryption.
A file moved into a vault directory keeps its plaintext bytes until something
reads and writes them back, so it looks migrated while lying in the clear.
"""

import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DmsFile(models.Model):
    _inherit = "dms.file"

    vault_id = fields.Many2one(
        "dms.vault",
        string="Vault",
        related="directory_id.vault_id",
        store=True,
        readonly=True,
        index=True,
    )
    needs_vault_migration = fields.Boolean(
        string="Needs Vault Migration",
        compute="_compute_needs_vault_migration",
        store=True,
        compute_sudo=True,
        help="The file is in a vault, but its stored bytes were never "
             "encrypted — it was moved in without being read and written "
             "back. It looks migrated and is plaintext.",
    )

    @api.depends("vault_id", "storage_id", "storage_id.save_type", "checksum")
    def _compute_needs_vault_migration(self):
        """A vault file whose bytes were never re-written needs migration.

        There is no field that records "these bytes are ciphertext", so the
        test is structural: a vault file stored through a storage backend
        (``save_type='attachment'``) was encrypted at write time, and a file
        whose ``store_fname`` is empty is stored in the database where the
        vault's write path never ran either. Both cases are plaintext until
        ``action_migrate()`` re-writes them.

        The check is conservative on purpose: reporting a file that is
        already encrypted costs one redundant re-write, while missing one
        leaves plaintext in a directory that claims to be encrypted.
        """
        for record in self:
            if not record.vault_id:
                record.needs_vault_migration = False
                continue
            record.needs_vault_migration = not record._dms_vault_bytes_are_ciphertext()

    def _dms_vault_bytes_are_ciphertext(self):
        """Whether this file's stored bytes were written by the vault.

        True only when the file went through ``ir.attachment`` after the
        directory became a vault. A file moved in from outside has a
        ``store_fname`` that predates the vault, and re-writing it is the only
        way to know.
        """
        self.ensure_one()
        if not self.vault_id:
            return True
        attachment = self._dms_vault_content_attachment()
        if not attachment:
            return False
        # A file that carries a plaintext checksum match against its own
        # stored object was written before the vault existed. Reading through
        # the vault layer would decrypt (and fail on plaintext), so the
        # comparison is done on the raw object instead.
        return attachment._dms_vault_raw_is_ciphertext()

    def _dms_vault_content_attachment(self):
        """The attachment that holds this file's bytes, if any.

        ``content_file`` is preferred over ``attachment_id``: a migration
        re-writes the content, which creates a NEW ``content_file``
        attachment, while ``attachment_id`` keeps pointing at the object that
        was written before the file entered the vault. Reading the wrong one
        would report a migrated file as still plaintext.
        """
        self.ensure_one()
        if self.storage_id.save_type == "attachment":
            # The newest attachment that actually holds bytes. A migration
            # clears ``content`` and writes it back, which leaves an empty
            # ``content_file`` row behind; picking by id alone would return
            # that one and report the file as unreadable.
            attachment = self.env["ir.attachment"].sudo().search(
                [
                    ("res_model", "=", "dms.file"),
                    ("res_id", "=", self.id),
                    ("res_field", "=", "content_file"),
                    ("file_size", ">", 0),
                ],
                limit=1,
                order="id desc",
            )
            if attachment:
                return attachment
        if self.attachment_id:
            return self.attachment_id
        return self.env["ir.attachment"].browse()

    @api.model_create_multi
    def create(self, vals_list):
        """Create the file with its vault in the context.

        The vault has to be known BEFORE ``ir.attachment`` writes the bytes,
        and at that point the file row does not exist yet. ``dms`` creates the
        attachment inside ``_create_model_attachment``, before ``super()``, so
        the vault is resolved from the DIRECTORY in ``vals_list`` and carried
        in the context through the whole create.
        """
        decorated = []
        for vals in vals_list:
            directory_id = vals.get("directory_id")
            if not directory_id and self.env.context.get("default_directory_id"):
                directory_id = self.env.context["default_directory_id"]
            vault = self.env["dms.vault"].sudo().search(
                [("directory_id", "=", directory_id)], limit=1
            ) if directory_id else self.env["dms.vault"].browse()
            decorated.append((vals, vault.id or False))
        # dms creates one attachment per file; the context is per-call, so the
        # common case (one vault for the whole batch) is handled directly and
        # a mixed batch falls back to one create per vault.
        vault_ids = {vault_id for _vals, vault_id in decorated}
        if len(vault_ids) == 1:
            return super(
                DmsFile,
                self.with_context(
                    dms_file_vault_write=next(iter(vault_ids)) or False,
                ),
            ).create(vals_list)
        records = self.browse()
        for vals, vault_id in decorated:
            records |= super(
                DmsFile,
                self.with_context(dms_file_vault_write=vault_id),
            ).create([vals])
        return records

    def write(self, vals):
        """Write with the vault in the context, so the bytes get encrypted.

        ``ir.attachment._storage_file_write`` runs before the attachment row
        exists and on an empty recordset; the only channel that survives is
        the context.

        ``directory_id`` is honoured when it is being CHANGED in this very
        write: that is the migration case, where the file is moving into the
        vault and the vault must be resolved from the new directory, not from
        the one it is leaving.
        """
        new_directory_id = vals.get("directory_id")
        if new_directory_id:
            vault = self.env["dms.vault"].sudo().search(
                [("directory_id", "=", new_directory_id)], limit=1
            )
            vault_id = vault.id or False
            directory_id = new_directory_id
        else:
            # A caller that already knows the vault wins: during a migration
            # the record's own ``vault_id`` is still empty while the bytes are
            # being written into the vault.
            vault_id = (
                self.env.context.get("dms_file_vault_write")
                or self[:1].vault_id.id
                or False
            )
            directory_id = self[:1].directory_id.id or False
        return super(
            DmsFile,
            self.with_context(
                dms_file_vault_write=vault_id,
                dms_file_directory_id=directory_id,
            ),
        ).write(vals)

    @api.model
    def _dms_vault_context(self, vault_id):
        """Context that tells the attachment layer which vault is writing."""
        return {"dms_file_vault_write": vault_id or False}

    def action_migrate(self, should_logging=True):
        """Re-write the bytes so the vault encrypts them.

        This is the ONLY path that encrypts an existing file. A plain
        ``wizard.dms.file.move`` changes ``directory_id`` and nothing else, so
        the bytes stay where they were — in the clear — while the file claims
        to be in a vault. Reading and writing ``content`` back forces
        ``_update_content_vals()`` to re-place the bytes, and the vault
        encrypts in ``_storage_file_write``.

        After the write the result is verified by reading the file back and
        comparing the plaintext SHA-1 with the checksum taken before the
        migration. A mismatch raises: reporting success on a file that is
        still plaintext is the worst outcome available here.
        """
        # OCA's ``action_migrate`` writes ``content`` back with the value it
        # already has, and Odoo skips unchanged values — ``_inverse_content``
        # never runs, the bytes are never re-placed, and the file keeps its
        # plaintext object while claiming to be in the vault.
        #
        # The bytes are therefore re-written on the attachment that holds
        # them. ``content_file`` is an ``attachment=True`` field, so the bytes
        # live in ``ir.attachment``, and writing that row's ``raw`` puts them
        # through ``_file_write`` — where the vault encrypts. Clearing
        # ``content`` first (the obvious approach) creates a second, empty
        # attachment and leaves two rows disagreeing about which object is
        # the file.
        vault_id = self[:1].vault_id.id or False
        for record in self:
            if not record.vault_id:
                continue
            attachment = record._dms_vault_content_attachment()
            if not attachment:
                raise ValidationError(
                    _(
                        "File '%s' has no attachment to migrate.",
                        record.name,
                    )
                )
            plaintext = record.content
            if not plaintext:
                continue
            attachment.with_context(
                dms_file_vault_write=vault_id
            ).write({"raw": base64.b64decode(plaintext)})
            # Version snapshots are separate ir.attachment rows holding their
            # own copy of the bytes. They were written before the file entered
            # the vault, so they are still plaintext — migrating only the
            # current content would leave every earlier revision readable.
            for version in record.version_ids:
                snapshot = version.attachment_id
                if not snapshot or not snapshot.store_fname:
                    continue
                # Read the stored object WITHOUT the vault layer: a snapshot
                # written before the file entered the vault is plaintext, and
                # ``_storage_file_read`` would try to decrypt it and raise.
                raw = self.env["ir.attachment"]._storage_file_read_raw(
                    snapshot.store_fname
                )
                if not raw:
                    continue
                snapshot.with_context(
                    dms_file_vault_write=vault_id
                ).write({"raw": raw})
        result = super(
            DmsFile,
            self.with_context(dms_file_vault_write=vault_id),
        ).action_migrate(should_logging=should_logging)
        self._dms_vault_verify_migration()
        return result

    def _dms_vault_verify_migration(self):
        """Read back and compare the plaintext checksum; raise on mismatch."""
        for record in self.filtered("vault_id"):
            expected = record.checksum
            content = record.content
            if not content:
                raise ValidationError(
                    _(
                        "File '%s' could not be read back after migration; "
                        "refusing to report it as migrated.",
                        record.name,
                    )
                )
            read_back = self._get_checksum(base64.b64decode(content))
            if expected and read_back != expected:
                raise ValidationError(
                    _(
                        "File '%(file)s' did not survive the migration: the "
                        "plaintext read back hashes to %(got)s, the checksum "
                        "before migration was %(expected)s. The file is not "
                        "reported as migrated.",
                        file=record.name,
                        got=read_back,
                        expected=expected,
                    )
                )
            # A read-back through ``content`` decrypts transparently, so it
            # proves the bytes are readable — NOT that they are ciphertext.
            # Check the stored object itself; a plaintext file that survived
            # the migration must be reported, not cleared.
            attachment = record._dms_vault_content_attachment()
            if not attachment or not attachment._dms_vault_raw_is_ciphertext():
                raise ValidationError(
                    _(
                        "File '%s' is still stored as plaintext after the "
                        "migration. The move changed the directory but the "
                        "bytes were never re-written.",
                        record.name,
                    )
                )
            record.needs_vault_migration = False
        return True

    def _dms_vault_assert_migrated(self):
        """Raise if any file in the set still holds plaintext in a vault."""
        pending = self.filtered("needs_vault_migration")
        if pending:
            raise ValidationError(
                _(
                    "These files are in a vault but were never re-written, so "
                    "their bytes are still plaintext: %s.\n\n"
                    "Moving a file into a vault directory does not encrypt "
                    "it. Run the vault migration (or 'Migrate' on the file) "
                    "so the content is read and written back.",
                    ", ".join(pending.mapped("name")),
                )
            )
        return True
