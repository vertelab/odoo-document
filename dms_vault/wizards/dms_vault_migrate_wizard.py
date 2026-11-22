# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Migrating existing files into a vault.

``wizard.dms.file.move`` does exactly one thing::

    items.write({"directory_id": self.directory_id})

It does not touch ``content``. ``storage_id`` is related to
``directory_id.storage_id`` so it *appears* to change, but the bytes stay
where they were — in plaintext. A naive move produces a file that claims to
be in a vault while lying in the clear. That is the worst kind of bug: it
looks like it works.

The correct path is ``dms.file.action_migrate()``, which reads ``content`` and
writes it back. That forces ``_update_content_vals()`` to re-place the bytes,
and the vault encrypts in ``_storage_file_write``.

This wizard therefore does the move AND the re-write, then verifies each file
by reading it back and comparing the plaintext SHA-1 with the checksum taken
before the migration. It refuses to report success on a mismatch.

``action_verify()`` is the safety net for files that were moved by some other
path: it reports every vault file whose stored object is not ciphertext.
"""

import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DmsVaultMigrateWizard(models.TransientModel):
    _name = "dms.vault.migrate.wizard"
    _description = "Migrate Files into a Vault"

    vault_id = fields.Many2one(
        "dms.vault", required=True, ondelete="cascade"
    )
    file_ids = fields.Many2many(
        "dms.file",
        string="Files",
        help="Files to move into the vault and encrypt. Leave empty to "
             "migrate every file already in the vault directory.",
    )
    pending_count = fields.Integer(
        string="Files Needing Migration",
        compute="_compute_pending_count",
    )
    result = fields.Text(readonly=True)

    def _compute_pending_count(self):
        for wizard in self:
            wizard.pending_count = self.env["dms.file"].search_count(
                [
                    ("directory_id", "=", wizard.vault_id.directory_id.id),
                    ("needs_vault_migration", "=", True),
                ]
            )

    def _target_files(self):
        """The files this run should migrate."""
        self.ensure_one()
        if self.file_ids:
            return self.file_ids
        return self.env["dms.file"].search([
            ("directory_id", "=", self.vault_id.directory_id.id),
            ("needs_vault_migration", "=", True),
        ])

    def action_migrate(self):
        """Move the files into the vault directory and re-write their bytes."""
        self.ensure_one()
        vault = self.vault_id
        files = self._target_files()
        if not files:
            self.result = _("Nothing to migrate.")
            return self._reload()

        files.write({"directory_id": vault.directory_id.id})
        # action_migrate() is the only call that encrypts: it reads content
        # and writes it back, so the vault's _storage_file_write runs. It also
        # verifies the read-back and raises on a mismatch, which is why the
        # loop does not swallow exceptions.
        files.action_migrate(should_logging=False)
        files._dms_vault_assert_migrated()

        self.result = _(
            "%(count)s file(s) migrated into vault '%(vault)s' and verified: "
            "the plaintext read back matches the checksum taken before the "
            "migration.",
            count=len(files),
            vault=vault.name,
        )
        return self._reload()

    def action_verify(self):
        """Report every vault file whose stored bytes are still plaintext."""
        self.ensure_one()
        vault = self.vault_id
        files = self.env["dms.file"].search([
            ("directory_id", "=", vault.directory_id.id),
        ])
        pending = files.filtered("needs_vault_migration")
        if pending:
            self.result = _(
                "%(count)s file(s) in vault '%(vault)s' are still plaintext "
                "and must be migrated:\n%(names)s",
                count=len(pending),
                vault=vault.name,
                names="\n".join(
                    "- %s" % name for name in pending.mapped("name")
                ),
            )
        else:
            self.result = _(
                "All %(count)s file(s) in vault '%(vault)s' hold ciphertext.",
                count=len(files),
                vault=vault.name,
            )
        return self._reload()

    def _reload(self):
        """Re-open the wizard so the result text is visible."""
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_check_files(self):
        """Raise if the given files are in a vault but still plaintext.

        Exposed so a caller that moved files by some other path (a script, an
        import, the generic move wizard) can assert the result instead of
        assuming it.
        """
        self.ensure_one()
        files = self.file_ids or self._target_files()
        if not files:
            raise ValidationError(_("No files selected."))
        return files._dms_vault_assert_migrated()
