# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Onboarding and offboarding — one row, no file touched.

Adding a member wraps the vault's existing content key with the member's
derived key: one ``dms.vault.key`` row. Removing a member blanks the wrapped
key: one write. Neither re-encrypts anything, because the content key never
changes.

WHAT REVOCATION DOES NOT DO: it does not take back what the member already
downloaded. The client form says so, because a revocation that looks like a
recall is worse than no revocation at all.
"""

import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DmsVaultMemberWizard(models.TransientModel):
    _name = "dms.vault.member.wizard"
    _description = "Add or Remove a Vault Member"

    vault_id = fields.Many2one(
        "dms.vault", required=True, ondelete="cascade"
    )
    mode = fields.Selection(
        [("add", "Add"), ("remove", "Remove")],
        required=True,
        default="add",
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        ondelete="cascade",
    )
    note = fields.Text(compute="_compute_note")

    def _compute_note(self):
        for wizard in self:
            if wizard.mode == "remove":
                wizard.note = _(
                    "Removing a member blanks their key and stops them from "
                    "decrypting anything they fetch from now on.\n\n"
                    "It does NOT re-encrypt the vault, and it does NOT take "
                    "back files the member has already downloaded. Those "
                    "copies stay readable to them forever."
                )
            else:
                wizard.note = _(
                    "Adding a member wraps the vault's existing content key "
                    "with their key. No file is re-encrypted."
                )

    def action_apply(self):
        self.ensure_one()
        vault = self.vault_id
        if self.mode == "add":
            member = self.env["dms.vault.key"].sudo()._grant(
                vault, self.user_id
            )
            _logger.info(
                "dms_vault: user %s added to vault %s (key %s)",
                self.user_id.login, vault.name, member.id,
            )
            return {"type": "ir.actions.act_window_close"}

        member = vault.key_ids.filtered(
            lambda k: k.user_id == self.user_id
        )
        if not member:
            raise ValidationError(
                _(
                    "'%s' is not a member of vault '%s'.",
                    self.user_id.name, vault.name,
                )
            )
        member._revoke()
        _logger.info(
            "dms_vault: user %s removed from vault %s",
            self.user_id.login, vault.name,
        )
        return {"type": "ir.actions.act_window_close"}
