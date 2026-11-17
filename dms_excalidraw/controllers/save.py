# -*- coding: utf-8 -*-
"""Save-back endpoints for the Excalidraw host page.

Why these routes exist rather than WebDAV:

`dms_webdav`'s PUT authenticates with **Basic auth** — it decodes an
`Authorization: Basic` header and calls `session.authenticate()`. A same-origin
SPA cannot use it without holding the user's password in JavaScript.

Odoo's `/jsonrpc` is not better: it requires `db`, `login` and `password` in
the request body and does not accept the session cookie either.

These routes use the session cookie, which the browser already has. The write
goes through the same `dms.file.content` inverse that WebDAV uses, and the
access check is the directory's `_filtered_access`, the same predicate the
WebDAV controller applies.
"""

import base64
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# The viewport belongs to the reader, not to the document. Saving it means
# every user inherits the last person's scroll position and zoom level.
VIEWPORT_KEYS = ("scrollX", "scrollY", "zoom")

# `appState.collaborators` is a Map in Excalidraw. JSON.stringify(Map) gives
# `{}`, so the saved scene carries `collaborators: {}` — and on load the
# client does `appState.collaborators.forEach(...)` and dies with
#   TypeError: e19.appState.collaborators.forEach is not a function
# The whole canvas stays blank. It is not document state anyway: it is who
# else is in the room right now, which is meaningless in a saved file.
#
# Same reasoning for the other live-session keys below: they describe the
# editing session, not the drawing.
SESSION_KEYS = (
    "collaborators",
    "followedBy",
    "userToFollow",
    "activeEmbeddable",
    "newElement",
    "multiElement",
    "selectionElement",
    "editingElement",
    "editingGroupId",
    "editingLinearElement",
    "editingTextElement",
    "resizingElement",
    "croppingElementId",
    "pendingImageElementId",
    "startBoundElement",
    "suggestedBindings",
    "originSnapOffset",
    "snapLines",
    "elementsToHighlight",
    "hoveredElementIds",
    "searchMatches",
    "selectedElementIds",
    "selectedGroupIds",
    "selectedLinearElement",
    "previousSelectedElementIds",
    "selectedElementsAreBeingDragged",
    "shouldCacheIgnoreZoom",
    "contextMenu",
    "openDialog",
    "openMenu",
    "openPopup",
    "openSidebar",
    "pasteDialog",
    "toast",
    "errorMessage",
    "fileHandle",
    "stats",
)

# Everything the client must not receive back. Viewport + live session.
DROP_APPSTATE_KEYS = VIEWPORT_KEYS + SESSION_KEYS

def _may(dms_file, operation):
    """Return True when the current user may perform `operation` on `dms_file`.

    `_filtered_access()` returns the SUBSET the user may touch — not a bool.
    `bool(recordset)` is True for any non-empty recordset, so the obvious
    `if not record._filtered_access("write")` never fires: it denies nobody.

    The question is whether THIS record survived the filter:
    `record & filtered`. OCA's own `_compute_permissions` asks it the same
    way (`bool(one & writeable)`).
    """
    allowed = dms_file.with_user(request.env.user)._filtered_access(operation)
    return bool(dms_file & allowed)




class DmsExcalidrawSaveController(http.Controller):
    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    @http.route(
        "/dms_excalidraw/scene/<int:file_id>",
        auth="user",
        type="http",
        website=False,
    )
    def scene(self, file_id):
        """Return the scene of a whiteboard, plus its checksum.

        `404` rather than `403` on denial: a clear "not found" does not
        disclose the existence of a document the user may not read.
        """
        dms_file = request.env["dms.file"].browse(file_id)

        # sudo for the existence check only: `dms.file` is filtered by an
        # ir.rule, so a file the user cannot see would look non-existent here
        # even when it is not. The access decision is made below.
        if not dms_file.sudo().exists():
            return request.make_json_response({"error": "not_found"}, status=404)

        if not _may(dms_file, "read"):
            _logger.info(
                "dms_excalidraw: user %s may not read dms.file %s",
                request.env.user.id,
                file_id,
            )
            return request.make_json_response({"error": "not_found"}, status=404)

        if (dms_file.extension or "").lower() != "excalidraw":
            return request.make_json_response({"error": "not_a_whiteboard"}, status=400)

        content = dms_file.content or ""
        try:
            scene = json.loads(base64.b64decode(content))
        except (ValueError, TypeError):
            # A whiteboard whose content is not valid JSON is a real state:
            # an interrupted write, or a file renamed to .excalidraw. Return
            # an empty scene rather than a 500, and say so.
            _logger.warning(
                "dms_excalidraw: dms.file %s has unparseable content", file_id
            )
            return request.make_json_response(
                {
                    "error": "unparseable",
                    "scene": None,
                    "checksum": dms_file.checksum or "",
                    "name": dms_file.name,
                }
            )

        return request.make_json_response(
            {
                "scene": scene,
                "checksum": dms_file.checksum or "",
                "name": dms_file.name,
                "file_id": dms_file.id,
            }
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    @http.route(
        "/dms_excalidraw/save/<int:file_id>",
        auth="user",
        type="http",
        website=False,
        # csrf=False: the request comes from fetch() with a JSON body, not an
        # Odoo form, so there is no CSRF token to send. The route is still
        # protected — auth="user" plus the directory access check in _may().
        csrf=False,
    )
    def save(self, file_id):
        """Write a scene back to the whiteboard.

        `base_checksum` is the checksum the client loaded. If the stored file
        has moved on since then, the write is refused with a conflict: two
        tabs on the same whiteboard must not silently overwrite each other.

        The route is `type="http"`, not `type="json"`: Odoo's JSON route
        expects a JSON-RPC envelope (`{"params": {...}}`) and answers 400 for
        a plain JSON body. The page posts `{"scene": ..., "base_checksum":
        ...}` directly, so the body is parsed here.
        """
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return request.make_json_response({"error": "invalid_body"}, status=400)

        scene = body.get("scene")
        base_checksum = body.get("base_checksum")

        dms_file = request.env["dms.file"].browse(file_id)

        if not dms_file.sudo().exists():
            return request.make_json_response({"error": "not_found"}, status=404)

        if not _may(dms_file, "write"):
            _logger.info(
                "dms_excalidraw: user %s may not write dms.file %s",
                request.env.user.id,
                file_id,
            )
            return request.make_json_response({"error": "forbidden"}, status=400)

        if (dms_file.extension or "").lower() != "excalidraw":
            return request.make_json_response({"error": "not_a_whiteboard"}, status=400)

        if not isinstance(scene, dict):
            return request.make_json_response({"error": "invalid_scene"}, status=400)

        current = dms_file.checksum or ""
        if base_checksum is not None and base_checksum != current:
            _logger.info(
                "dms_excalidraw: conflict on dms.file %s (client %s, stored %s)",
                file_id,
                base_checksum,
                current,
            )
            return request.make_json_response(
                {"error": "conflict", "checksum": current}, status=409
            )

        cleaned = self._strip_viewport(scene)
        payload = json.dumps(cleaned, separators=(",", ":")).encode("utf-8")

        dms_file.write(
            {"content": base64.b64encode(payload)}
        )

        return request.make_json_response(
            {
                "checksum": dms_file.checksum or "",
                "saved_at": dms_file.write_date.isoformat()
                if dms_file.write_date
                else None,
            }
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _strip_viewport(scene):
        """Return a copy of `scene` without the reader's viewport state.

        `scrollX`, `scrollY` and `zoom` describe how the *last person* was
        looking at the drawing. Saving them makes every other user open the
        whiteboard at someone else's scroll position.

        `viewBackgroundColor` and `gridSize` are kept: they are properties of
        the document, not of the view.
        """
        cleaned = dict(scene)

        # `libraryItems` is a top-level key in the scene file (not appState).
        # Excalidraw writes it when the user adds a shape library. It is
        # document state — keep it — but it must be a list. A Map or an
        # object here makes the client fail on load the same way
        # `collaborators` does.
        if "libraryItems" in cleaned and not isinstance(
            cleaned["libraryItems"], list
        ):
            _logger.warning(
                "dms_excalidraw: dropping non-list libraryItems (%s)",
                type(cleaned["libraryItems"]).__name__,
            )
            cleaned.pop("libraryItems", None)

        app_state = cleaned.get("appState")
        if isinstance(app_state, dict):
            cleaned["appState"] = {
                key: value
                for key, value in app_state.items()
                if key not in DROP_APPSTATE_KEYS
            }
        return cleaned

    # ------------------------------------------------------------------
    # Save as copy (conflict resolution)
    # ------------------------------------------------------------------
    @http.route(
        "/dms_excalidraw/copy/<int:file_id>",
        auth="user",
        type="http",
        website=False,
        csrf=False,
    )
    def save_as_copy(self, file_id):
        """Create a new whiteboard next to the original.

        This is the second half of the conflict dialog: when two tabs both
        edited the same drawing, the second user must be able to keep their
        work without overwriting the first. A copy is the only honest answer —
        a merge of two hand-drawn scenes is not something we can do.

        Body is read manually for the same reason as `save()`: the route is
        `type="http"`, not Odoo's JSON-RPC envelope.
        """
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return request.make_json_response({"error": "invalid_body"}, status=400)
        scene = body.get("scene")

        dms_file = request.env["dms.file"].browse(file_id)

        if not dms_file.sudo().exists():
            return request.make_json_response({"error": "not_found"}, status=404)

        if not _may(dms_file, "create"):
            return request.make_json_response({"error": "forbidden"}, status=400)

        if not isinstance(scene, dict):
            return request.make_json_response({"error": "invalid_scene"}, status=400)

        base_name = dms_file.name
        if base_name.lower().endswith(".excalidraw"):
            base_name = base_name[: -len(".excalidraw")]
        copy_name = "%s (copy).excalidraw" % base_name

        # Never collide: dms refuses two files with the same name in a
        # directory, so a second copy gets a number.
        existing = request.env["dms.file"].sudo().search(
            [
                ("directory_id", "=", dms_file.directory_id.id),
                ("name", "like", copy_name[: -len(".excalidraw")]),
            ]
        )
        if existing:
            copy_name = "%s (copy %d).excalidraw" % (base_name, len(existing) + 1)

        payload = json.dumps(
            self._strip_viewport(scene), separators=(",", ":")
        ).encode("utf-8")

        new_file = (
            request.env["dms.file"]
            .with_user(request.env.user)
            .create(
                {
                    "name": copy_name,
                    "directory_id": dms_file.directory_id.id,
                    "content": base64.b64encode(payload),
                    "mimetype": "application/json",
                }
            )
        )

        _logger.info(
            "dms_excalidraw: saved conflict copy dms.file %s of %s",
            new_file.id,
            file_id,
        )
        return {"file_id": new_file.id, "name": new_file.name}


class DmsExcalidrawPageController(http.Controller):
    """Serve the host page.

    The page is served by Odoo, not by the Excalidraw container. Reason: it
    needs the session, the file id and the access check, none of which the
    container has. The container stays a dumb static asset server that is
    upgraded with `docker pull`.
    """

    @http.route(
        "/dms_excalidraw/whiteboard/<int:file_id>",
        auth="user",
        type="http",
        website=False,
    )
    def whiteboard(self, file_id, **kwargs):
        dms_file = request.env["dms.file"].browse(file_id)

        if not dms_file.sudo().exists():
            return request.not_found()

        if not _may(dms_file, "read"):
            return request.not_found()

        if (dms_file.extension or "").lower() != "excalidraw":
            return request.not_found()

        # Where "back" goes. The file's own directory is the place the user
        # came from; falling back to the Documents root keeps the link valid
        # even for a file whose directory was deleted underneath us.
        # The action xmlids are `dms.action_dms_directory` and
        # `dms.action_dms_file` — NOT `dms.dms_directory_action`. A wrong
        # xmlid renders as "Missing Action" in the web client, which is what
        # the first version of this bar did.
        directory = dms_file.directory_id
        if directory:
            back_url = "/odoo/action-dms.action_dms_directory/%s" % directory.id
        else:
            back_url = "/odoo/documents"

        return request.render(
            "dms_excalidraw.whiteboard_page",
            {
                "file_id": dms_file.id,
                "file_name": dms_file.name,
                "back_url": back_url,
                "record_url": "/odoo/action-dms.action_dms_file/%s" % dms_file.id,
                # Cache-busting for the plain <script> tags. The page does not
                # go through Odoo's asset pipeline (see whiteboard_page.xml),
                # so nothing else versions these files. Without it a browser
                # keeps an old main.js after a module upgrade — and the symptom
                # is a white canvas with no error the user can see.
                "asset_version": self._asset_version(),
            },
        )

    @staticmethod
    def _asset_version():
        """Return a short version token for the static files.

        The module version changes on every deploy, which is exactly when the
        files can change. Cheap, stable between deploys, and good enough to
        defeat browser caching of an unversioned <script src>.
        """
        module = request.env["ir.module.module"].sudo().search(
            [("name", "=", "dms_excalidraw")], limit=1
        )
        return (module.latest_version or "0").replace(".", "")
