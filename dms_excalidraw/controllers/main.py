# -*- coding: utf-8 -*-
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
