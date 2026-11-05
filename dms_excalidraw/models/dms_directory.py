# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    def action_new_whiteboard_url(self):
        """Return the URL that creates a whiteboard in this directory.

        The view binds a server action to `dms.directory` that calls this
        method; the controller at `/dms_excalidraw/new/<directory_id>` is what
        actually creates the file and redirects to Excalidraw (design D6).

        The permission check lives in the controller, not here: it answers 404
        on denial rather than disclosing the directory's existence. This method
        only refuses a directory the user cannot write to at all, so the UI
        fails with a readable message instead of a bare 404.
        """
        self.ensure_one()
        if not self.permission_create:
            raise UserError(
                _(
                    "You do not have permission to create a whiteboard in "
                    "“%(directory)s”.",
                    directory=self.complete_name or self.name,
                )
            )
        return {
            "type": "ir.actions.act_url",
            "url": "/dms_excalidraw/new/%s" % self.id,
            "target": "new",
        }

    def action_new_document_wizard(self):
        """Open the shared "New document" prompt for this directory.

        Replaces `action_new_whiteboard_wizard`: the prompt now offers every
        type a module has registered (whiteboard, Word, Excel, PowerPoint),
        not just whiteboards.
        """
        self.ensure_one()
        if not self.permission_create:
            raise UserError(
                _(
                    "You do not have permission to create documents in "
                    "“%(directory)s”.",
                    directory=self.complete_name or self.name,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("New document"),
            "res_model": "dms.document.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_directory_id": self.id},
        }

    def action_new_whiteboard_wizard(self):
        """Open the name prompt for a new whiteboard in this directory.

        This is what the "New whiteboard" button calls since 2026-11-03. The
        old path created the file immediately under a fixed name, which meant
        (a) the user could not name it before opening it, and (b) a second
        click collided with the first file and answered 404.

        The permission check stays here as a readable error: the controller
        answers 404 on denial (so it does not disclose the directory), but a
        button that silently does nothing is worse than one that explains why.
        """
        self.ensure_one()
        if not self.permission_create:
            raise UserError(
                _(
                    "You do not have permission to create a whiteboard in "
                    "“%(directory)s”.",
                    directory=self.complete_name or self.name,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("New whiteboard"),
            "res_model": "dms.excalidraw.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_directory_id": self.id},
        }
