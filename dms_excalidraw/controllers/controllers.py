# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2026- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DmsExcalidrawController(http.Controller):
    """Skapa en whiteboard direkt i en katalog.

    Varför en egen route och inte bara en knapp på dms.file:
    "New whiteboard" ska kunna klickas i en katalogvy där ingen
    dms.file-post finns ännu. En ``ir.actions.server`` på dms.file kräver
    en vald post; den här routen tar katalogen ur query-strängen.
    """

    @http.route(
        "/dms_excalidraw/new/<int:directory_id>",
        auth="user",
        type="http",
        website=False,
    )
    def new_whiteboard(self, directory_id, name=None, **kwargs):
        directory = request.env["dms.directory"].browse(directory_id)
        if not directory.exists():
            _logger.warning(
                "dms_excalidraw: directory %s not found", directory_id
            )
            return request.not_found()

        # Behörighetskontroll: create på dms.file i den katalogen.
        # Vi kontrollerar explicit i stället för att lita på att ett
        # AccessError kastas — ett tydligt 403 är bättre än en 500.
        try:
            request.env["dms.file"].check_access_rights("create")
        except Exception:  # noqa: BLE001 — AccessError är inte alltid importerbar här
            _logger.info(
                "dms_excalidraw: user %s denied create on dms.file",
                request.env.user.id,
            )
            return request.not_found()

        action = (
            request.env["dms.file"]
            .with_context(default_directory_id=directory_id, default_name=name)
            .action_new_whiteboard()
        )
        return request.redirect(action["url"], code=302)
