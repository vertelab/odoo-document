# -*- coding: utf-8 -*-
import base64
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The documented minimum scene from
# `excalidraw/packages/excalidraw/data/blob.ts`.
#
# This is a constant, not a template. Excalidraw refuses to load a file that is
# not a valid scene: an empty file or `{}` gives "Error: invalid scene" in the
# client with no hint about what is wrong. A new whiteboard must therefore be
# born with this shape, not with empty content.
EMPTY_SCENE = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": [],
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}

WHITEBOARD_EXTENSION = "excalidraw"


class DmsFile(models.Model):
    _inherit = "dms.file"

    can_open_in_excalidraw = fields.Boolean(
        string="Can open in Excalidraw",
        compute="_compute_can_open_in_excalidraw",
    )

    is_document_template = fields.Boolean(
        string="Is a template",
        default=False,
        help="Offer this file as a starting point when creating a new "
        "document of the same type. A template is a normal document: it "
        "inherits the directory's access groups, retention and backup, and "
        "is maintained like any other file.",
    )

    @api.depends("extension")
    def _compute_can_open_in_excalidraw(self):
        for record in self:
            extension = (record.extension or "").lower().lstrip(".")
            record.can_open_in_excalidraw = extension == WHITEBOARD_EXTENSION

    # ------------------------------------------------------------------
    # Path building
    # ------------------------------------------------------------------

    def _excalidraw_directory_chain(self):
        """Return the path segments from the WebDAV mount point down.

        The first segment is the *storage* name, because that is what
        `dms_webdav`'s resolver treats as the mount point: it resolves
        `/{storage_name}/{directory_path}/{file_name}` and looks the first
        segment up in `dms.storage`, not in `dms.directory`
        (`dms_webdav/models/dms_webdav_path.py`).

        Root directories are *children* of a storage in that resolver --
        `list_storage()` returns them as directories under `/{storage_name}` --
        so a root directory does contribute its own segment. A whiteboard in a
        root directory called `Whiteboards` on storage `DMS` therefore lives at
        `/webdav/DMS/Whiteboards/ritning.excalidraw`.

        A `seen` set stops a cyclic parent chain. `_check_directory_recursion`
        rejects cycles created through the ORM, but a corrupted `parent_id`
        must not hang a request -- so the walk stops, logs, and returns what it
        has.
        """
        self.ensure_one()
        names = []
        seen = set()
        directory = self.directory_id
        while directory:
            if directory.id in seen:
                _logger.warning(
                    "Cyclic directory chain at dms.directory %s while building "
                    "the Excalidraw path for dms.file %s; stopping the walk.",
                    directory.id,
                    self.id,
                )
                break
            seen.add(directory.id)
            names.append(directory.name)
            directory = directory.parent_id

        names.reverse()

        # `storage_id` is a related field on dms.file, so it is available even
        # on a record whose directory chain is broken.
        storage = self.storage_id
        if storage:
            names.insert(0, storage.name)
        return names

    def _excalidraw_webdav_path(self, webdav_root="/webdav"):
        """Return the WebDAV path of this whiteboard.

        Derived from the directory chain, never stored: a directory rename
        must not break the link (design D4). `webdav_root` is the route prefix
        and appears exactly once; everything after it is the resolver's own
        path.
        """
        self.ensure_one()
        segments = self._excalidraw_directory_chain()
        segments.append(self.name)
        root = (webdav_root or "").rstrip("/")
        return "%s/%s" % (root, "/".join(segments))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _excalidraw_service_url(self):
        """Return the configured Excalidraw service URL, or raise.

        An empty URL must not produce a broken link: a broken link looks like a
        bug in the whiteboard, not like a missing configuration (design D7).
        """
        url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dms_excalidraw.url", "")
        )
        if not url or not url.strip():
            raise UserError(
                _(
                    "The Excalidraw service URL is not configured.\n\n"
                    "Set 'dms_excalidraw.url' under Settings > Documents > "
                    "Excalidraw before opening a whiteboard."
                )
            )
        return url.strip()

    def _excalidraw_webdav_root(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dms_excalidraw.webdav_path", "/webdav")
        )

    def open_in_excalidraw_action(self):
        """Return an `ir.actions.act_url` that opens this whiteboard.

        The URL points the browser at the Excalidraw service with the WebDAV
        path of the file. The browser fetches the file itself, with the user's
        own session; the server never reads it (design D2).
        """
        self.ensure_one()
        if not self.can_open_in_excalidraw:
            raise UserError(
                _(
                    "“%(name)s” cannot be opened in Excalidraw: its extension is "
                    "“%(extension)s”, not “excalidraw”.",
                    name=self.name,
                    extension=self.extension or _("none"),
                )
            )
        # The action opens the HOST PAGE, not the bare Excalidraw service.
        #
        # The service at `<host>/whiteboard` is a built SPA: it reads
        # `#url=`/`#json=`/`#room=` from the hash and has no `onChange` hook we
        # can attach to, because we are not its host app. A drawing opened
        # there can only be saved with "Save to disk" -- a download, not a
        # write back to the document.
        #
        # The host page at `/dms_excalidraw/whiteboard/<id>` renders
        # `<Excalidraw>` itself and owns the callbacks, so a save goes to the
        # same `dms.file`. It is served by Odoo (it needs the session, the file
        # id and the access check) and fills the viewport.
        #
        # `_excalidraw_service_url()` is still called: it raises a user-facing
        # error naming the setting when the service is not configured.
        self._excalidraw_service_url()

        return {
            "type": "ir.actions.act_url",
            "url": "/dms_excalidraw/whiteboard/%s" % self.id,
            "target": "new",
        }

    def action_new_document_from_selection(self):
        """Open the shared "New document" prompt next to the selected file.

        Bound to the Action menu on `dms.file` (list and kanban), which is
        also what Odoo shows on right-click. The directory comes from the
        selected row; with nothing selected it falls back to the directory
        the user is browsing.
        """
        directory = self[:1].directory_id if self else False

        if not directory:
            directory_id = self.env.context.get("active_directory_id") or (
                self.env.context.get("default_directory_id")
            )
            if directory_id:
                directory = self.env["dms.directory"].browse(directory_id)

        if not directory:
            # No directory in context and nothing selected. Rather than
            # refusing, open the wizard with a directory PICKER: the user
            # clicked "New document", so they want a document — asking which
            # folder is a better answer than an error.
            #
            # The picker is the same wizard, with `directory_id` left for the
            # user to fill in. `permission_create` is checked when they pick.
            return {
                "type": "ir.actions.act_window",
                "name": _("New document"),
                "res_model": "dms.document.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {},
            }

        if not directory.permission_create:
            raise UserError(
                _(
                    "You do not have permission to create documents in "
                    "“%(directory)s”.",
                    directory=directory.complete_name or directory.name,
                )
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("New document"),
            "res_model": "dms.document.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_directory_id": directory.id},
        }

    def action_new_whiteboard_from_selection(self):
        """Open the name prompt for a whiteboard next to the selected file.

        Bound to the Action menu on `dms.file` (list and kanban), which is
        also what Odoo shows on right-click. The user is usually in the Files
        list, not in a directory form, so the directory has to come from the
        selection.

        Falls back to the active directory in context when nothing is
        selected — that is the folder the user is browsing.
        """
        directory = self[:1].directory_id if self else False

        if not directory:
            directory_id = self.env.context.get("active_directory_id") or (
                self.env.context.get("default_directory_id")
            )
            if directory_id:
                directory = self.env["dms.directory"].browse(directory_id)

        if not directory:
            raise UserError(
                _(
                    "Select a file (so the directory is known) or open the "
                    "directory you want the whiteboard in."
                )
            )

        if not directory.permission_create:
            raise UserError(
                _(
                    "You do not have permission to create a whiteboard in "
                    "“%(directory)s”.",
                    directory=directory.complete_name or directory.name,
                )
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("New whiteboard"),
            "res_model": "dms.excalidraw.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_directory_id": directory.id},
        }

    def action_new_whiteboard(self, name=None, directory=None):
        """Create a whiteboard and return the action that opens it.

        Two call sites, two shapes:

        * From a `dms.file` record (the list/kanban action menu): no
          `directory` argument, so the file's own directory is used. The
          recordset must hold exactly one record.
        * From the controller ("New whiteboard" on a directory): the
          recordset is EMPTY -- the file does not exist yet -- and the
          directory is passed explicitly.

        So `ensure_one()` is only applied when the directory has to be
        derived from the record. An empty recordset with an explicit
        directory is a valid call; an empty recordset without one is a user
        error, not a ValueError.
        """
        if directory is None:
            if not self:
                raise UserError(
                    _(
                        "Select a file or a directory before creating a "
                        "whiteboard."
                    )
                )
            self.ensure_one()
            directory = self.directory_id

        if not directory:
            raise UserError(
                _(
                    "A whiteboard must be created in a directory, and no "
                    "directory was given."
                )
            )
        name = (name or _("Whiteboard")).strip()
        if not name.lower().endswith(".%s" % WHITEBOARD_EXTENSION):
            name = "%s.%s" % (name, WHITEBOARD_EXTENSION)

        whiteboard = self.create(
            {
                "name": name,
                "directory_id": directory.id,
                # `content` is a non-stored computed Binary with an inverse
                # that runs `base64.b64decode(record.content)`. It therefore
                # expects BASE64 TEXT, not raw bytes: raw bytes raise
                # `binascii.Error: Incorrect padding` on create.
                "content": base64.b64encode(
                    json.dumps(EMPTY_SCENE).encode("utf-8")
                ),
            }
        )
        return whiteboard.open_in_excalidraw_action()
