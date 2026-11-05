# -*- coding: utf-8 -*-
import base64
import json
import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class DmsExcalidrawController(http.Controller):
    @http.route(
        "/dms_excalidraw/new/<int:directory_id>",
        auth="user",
        type="http",
        website=False,
    )
    def new_whiteboard(self, directory_id, **kwargs):
        """Create a whiteboard in a directory and redirect to Excalidraw.

        This route exists because "New whiteboard" must be clickable from a
        *directory* view, where no `dms.file` record exists to bind a server
        action to (design D6).

        Denial is answered with 404, not 403: a clear "not found" is better
        than an access error that leaks the existence of the directory.
        """
        env = request.env
        directory = env["dms.directory"].browse(directory_id)

        # sudo for the existence check only: `dms.directory` is filtered by an
        # ir.rule on the computed `permission_read`, so a directory the user
        # cannot see would look non-existent here even when it is not. The
        # access decision is made below, on the user's own rights.
        if not directory.sudo().exists():
            _logger.info(
                "dms_excalidraw: directory %s does not exist", directory_id
            )
            return request.not_found()

        # Authorisation is the DIRECTORY's, not the model's.
        #
        # `dms.file` grants `perm_create` only to `group_dms_user`
        # (`dms/security/ir.model.access.csv`: `base.group_user` has 0,0,0,0).
        # A model-level `check_access_rights("create")` therefore denies every
        # ordinary internal user -- the exact audience this button exists for.
        # The DMS access model is per-directory: `permission_create` is the
        # computed field the OCA views themselves use to decide whether a
        # directory accepts writes. That is the authoritative gate.
        if not directory.permission_create:
            _logger.info(
                "dms_excalidraw: user %s may not create in directory %s",
                env.user.id,
                directory_id,
            )
            return request.not_found()

        try:
            # `action_new_whiteboard` is called on an EMPTY recordset: the
            # controller browses only the directory, and the file does not
            # exist yet. That is why the method accepts `directory` explicitly
            # and why its `not self` guard cannot be reached from here -- the
            # guard is for the list-view case, where a user invokes the action
            # with no row selected.
            action = env["dms.file"].action_new_whiteboard(directory=directory)
        except UserError as error:
            # A UserError here is almost always a NAME COLLISION: DMS refuses
            # two files with the same name in one directory, and the default
            # name is the same every time ("Whiteboard.excalidraw"). The first
            # click creates it; the second would 404 for a reason that has
            # nothing to do with the directory existing.
            #
            # So: retry with a free name before giving up. A user clicking
            # "New whiteboard" twice expects two whiteboards, not an error.
            _logger.info(
                "dms_excalidraw: default name taken in directory %s (%s); "
                "retrying with a numbered name",
                directory_id,
                error,
            )
            action = self._create_with_free_name(env, directory)
            if action is None:
                return request.not_found()
        except AccessError as error:
            # Access was refused underneath us despite permission_create. That
            # is a real denial, and 404 is the right answer -- it does not
            # disclose that the directory exists.
            _logger.warning(
                "dms_excalidraw: access denied creating a whiteboard in "
                "directory %s: %s",
                directory_id,
                error,
            )
            return request.not_found()

        return request.redirect(action["url"], code=302)

    @staticmethod
    def _create_with_free_name(env, directory, limit=50):
        """Create a whiteboard under the first free name in the directory.

        DMS enforces a unique (directory_id, name) pair. The default name is
        the same on every click, so the second click collides. Try
        ``Whiteboard.excalidraw`` first (already taken in that case), then
        ``Whiteboard (2).excalidraw``, ``(3)``, ... -- the same convention
        desktop file managers use.

        Returns the action, or ``None`` when every candidate is taken.
        """
        DmsFile = env["dms.file"]
        for n in range(2, limit + 1):
            try:
                return DmsFile.action_new_whiteboard(
                    directory=directory, name="Whiteboard (%d)" % n
                )
            except UserError:
                continue
            except AccessError:
                return None
        _logger.error(
            "dms_excalidraw: no free whiteboard name in directory %s after "
            "%s attempts",
            directory.id,
            limit,
        )
        return None

    # ------------------------------------------------------------------
    # Shape libraries
    # ------------------------------------------------------------------

    @http.route(
        "/dms_excalidraw/libraries",
        auth="user",
        type="http",
        website=False,
    )
    def libraries(self, **kwargs):
        """Return the catalogue the picker lists.

        Only the metadata: name, authors, item count, preview and the id the
        picker uses to load the shapes. The shapes themselves are fetched one
        library at a time, because a catalogue of 30 is 13 MB and the picker
        must render before any of it arrives.
        """
        libraries = (
            request.env["dms_excalidraw.library"]
            .sudo()
            .search([("active", "=", True)], order="name, id")
        )
        payload = [
            {
                "id": library.id,
                "name": library.name,
                "authors": library.authors or "",
                "item_count": library.item_count,
                "preview_url": library.preview_url or "",
                "byte_size": library.byte_size,
            }
            for library in libraries
        ]
        return request.make_json_response({"libraries": payload})

    @http.route(
        "/dms_excalidraw/library/<int:library_id>",
        auth="user",
        type="http",
        website=False,
    )
    def library(self, library_id, **kwargs):
        """Return one library's shapes, or an error naming it.

        `action_load` answers with `{"error": ...}` for the two conditions the
        picker must show rather than swallow: too large, and unreadable. A 404
        would tell the user nothing about which library failed and why.
        """
        library = request.env["dms_excalidraw.library"].sudo().browse(library_id)
        if not library.exists() or not library.active:
            return request.make_json_response(
                {"error": "The library does not exist."}, status=404
            )
        result = library.action_load()
        if "error" in result:
            return request.make_json_response(result, status=422)
        return request.make_json_response(result)

    @http.route(
        "/dms_excalidraw/save_library/<int:file_id>",
        auth="user",
        type="http",
        website=False,
        csrf=False,
    )
    def save_library(self, file_id, **kwargs):
        """Save the caller's shape library as a file next to the whiteboard.

        A user library is a `dms.file` with `extension = excalidrawlib`, so it
        lives in a folder and inherits that folder's access rules. It is NOT a
        catalogue record: the catalogue is a shared reference with no owner,
        and putting a user's own shapes there would leak them to everyone.

        The file is created in the whiteboard's own directory. A user who
        saves their library while working in a customer folder finds it there,
        not in a global pile they cannot locate later.
        """
        env = request.env
        whiteboard = env["dms.file"].browse(file_id)
        if (
            not whiteboard.exists()
            or whiteboard.extension != "excalidraw"
            or not whiteboard.directory_id._filtered_access("write")
        ):
            return request.make_json_response(
                {"error": "The whiteboard does not exist."}, status=404
            )

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True))
        except ValueError:
            return request.make_json_response(
                {"error": "The request body is not valid JSON."}, status=400
            )
        items = payload.get("libraryItems")
        if not isinstance(items, list) or not items:
            return request.make_json_response(
                {"error": "The library is empty."}, status=400
            )

        directory = whiteboard.directory_id
        document = {
            "type": "excalidrawlib",
            "version": 2,
            "source": "https://dms.vertel.se",
            "libraryItems": items,
        }
        blob = json.dumps(document).encode("utf-8")

        # Same naming convention as a new whiteboard: the default name is the
        # same on every click, and DMS enforces a unique (directory, name).
        base = "My library"
        existing = set(directory.file_ids.mapped("name"))
        name = base + ".excalidrawlib"
        counter = 2
        while name in existing:
            name = "%s (%d).excalidrawlib" % (base, counter)
            counter += 1

        try:
            # SUDO, and the access decision is the one taken above.
            #
            # The plain call failed with "Administrator doesn't have 'create'
            # access to dms.file" in the HTTP context while the same call
            # succeeded in a shell (verified 2026-11-05). `dms.file` carries
            # an ir.rule on the computed `permission_read`, which is False for
            # a record that does not exist yet — so the rule hides the create
            # from the very user performing it.
            #
            # The authorisation is NOT delegated here: `_filtered_access
            # ("write")` on the whiteboard's directory already decided, above.
            # `sudo()` only lets the ORM write the row that decision permits.
            record = (
                env["dms.file"]
                .sudo()
                .create(
                    {
                        "name": name,
                        "directory_id": directory.id,
                        "content": base64.b64encode(blob),
                    }
                )
            )
        except (AccessError, UserError) as error:
            _logger.warning(
                "dms_excalidraw: save_library failed for user %s in directory "
                "%s: %s", env.uid, directory.id, error
            )
            return request.make_json_response(
                {"error": str(error)}, status=403
            )

        # Read the values off the CREATE result, not by re-reading the record.
        #
        # `dms.file` carries an ir.rule on the computed `permission_read`, so
        # a plain read right after create can be filtered out — the record
        # exists and the caller may write to it, but the rule has not seen it
        # yet. Re-reading raised "you have stumbled upon some top-secret
        # records" on a file the same user had just created (verified
        # 2026-11-05). The values are already in hand; do not fetch them again.
        return request.make_json_response({"id": record.id, "name": name})

    @http.route(
        "/dms_excalidraw/user_libraries",
        auth="user",
        type="http",
        website=False,
    )
    def user_libraries(self, **kwargs):
        """Return the caller's own saved libraries.

        A user library is a `dms.file` with `extension = excalidrawlib`, so it
        inherits its folder's `dms.access.group`. The search is therefore NOT
        sudo: `dms.file`'s own ir.rules decide what the caller may see, and a
        file in a folder they cannot read must not appear in their picker.
        """
        env = request.env
        files = env["dms.file"].search(
            [("extension", "=", "excalidrawlib"), ("active", "=", True)],
            order="name, id",
        )
        payload = [
            {
                "id": record.id,
                "name": record.name,
                "authors": "",
                "item_count": 0,
                "preview_url": "",
                "byte_size": record.size or 0,
                "user_library": True,
            }
            for record in files
        ]
        return request.make_json_response({"libraries": payload})

    @http.route(
        "/dms_excalidraw/user_library/<int:file_id>",
        auth="user",
        type="http",
        website=False,
    )
    def user_library(self, file_id, **kwargs):
        """Return one user library's shapes.

        Read through the same `_filtered_access` the scene endpoint uses: a
        file the caller cannot read must answer 404, not 403, for the same
        reason — 403 confirms it exists.
        """
        env = request.env
        record = env["dms.file"].browse(file_id)
        if (
            not record.exists()
            or record.extension != "excalidrawlib"
            or not record.directory_id._filtered_access("read")
        ):
            return request.make_json_response(
                {"error": "The library does not exist."}, status=404
            )
        try:
            data = json.loads(base64.b64decode(record.content).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            return request.make_json_response(
                {
                    "error": "The library '%s' is not valid JSON: %s"
                    % (record.name, error)
                },
                status=422,
            )
        return request.make_json_response({"library": data})
