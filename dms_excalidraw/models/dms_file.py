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

import base64
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

EXCALIDRAW_EXTENSION = "excalidraw"

# Minimal, giltig Excalidraw-scene. Excalidraw kräver att rotobjektet är en
# lista — att skicka `{}` eller en tom fil ger "Error: invalid scene" i
# klienten. Se https://github.com/excalidraw/excalidraw/blob/master/packages/excalidraw/data/blob.ts
EMPTY_SCENE = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": [],
    "appState": {
        "gridSize": None,
        "viewBackgroundColor": "#ffffff",
    },
    "files": {},
}


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    def action_new_whiteboard(self):
        """Skapa en tom Excalidraw-ritning i denna katalog.

        Ligger på dms.directory (inte dms.file) eftersom knappen sitter i
        katalogformuläret — där finns ingen dms.file-post att agera på.
        """
        self.ensure_one()
        return (
            self.env["dms.file"]
            .with_context(default_directory_id=self.id)
            .action_new_whiteboard()
        )


class DmsFile(models.Model):
    _inherit = "dms.file"

    can_open_in_excalidraw = fields.Boolean(
        string="Can open in Excalidraw",
        compute="_compute_can_open_in_excalidraw",
    )

    @api.depends("extension")
    def _compute_can_open_in_excalidraw(self):
        for rec in self:
            ext = (rec.extension or "").lower().lstrip(".")
            rec.can_open_in_excalidraw = ext == EXCALIDRAW_EXTENSION

    # ------------------------------------------------------------------
    # Öppna
    # ------------------------------------------------------------------
    def open_in_excalidraw_action(self):
        """Returnera en action som öppnar filen i Excalidraw-tjänsten.

        Flödet är medvetet enkelt: vi skickar användaren till
        Excalidraw-tjänsten med en URL som pekar tillbaka på Odoo:s
        DMS-WebDAV-endpoint. Excalidraw hämtar filen därifrån (användarens
        session/cookies gäller, eftersom det är samma värd) och sparar
        tillbaka samma väg.

        Varför inte en server-side proxy: DMS-WebDAV kräver användarens
        behörighet. En proxy skulle behöva ``sudo()`` och därmed kringgå
        ``dms.access.group`` — det är ett behörighetshål, inte en förenkling.
        """
        self.ensure_one()
        if not self.can_open_in_excalidraw:
            raise UserError(
                _(
                    "Filen '%(name)s' är inte en Excalidraw-ritning "
                    "(extension: %(ext)s).",
                    name=self.name,
                    ext=self.extension or "-",
                )
            )

        base_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "")
        )
        webdav_path = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dms_excalidraw.webdav_path", "/webdav")
        )
        excalidraw_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dms_excalidraw.url", "")
        )

        if not excalidraw_url:
            raise UserError(
                _(
                    "Excalidraw-tjänstens URL är inte konfigurerad. "
                    "Sätt 'Excalidraw URL' under Inställningar ▸ DMS."
                )
            )

        # Filens WebDAV-sökväg. dms_webdav exponerar DMS-trädet under
        # /webdav/<katalog>/<filnamn>. Vi bygger den ur katalogens namnkedja
        # i stället för att gissa — kataloger kan vara nästlade.
        dav_path = self._excalidraw_webdav_path(webdav_path)
        file_url = f"{base_url.rstrip('/')}{dav_path}"

        return {
            "type": "ir.actions.act_url",
            "url": (
                f"{excalidraw_url.rstrip('/')}/"
                f"#json={file_url}"
            ),
            "target": "new",
        }

    def _excalidraw_webdav_path(self, webdav_root="/webdav"):
        """Bygg WebDAV-sökvägen för denna fil.

        ``dms_webdav`` monterar DMS-trädet med katalognamn som segment.
        Rot-katalogen (``is_root_directory``) är monteringspunkten och
        ingår därför inte i sökvägen.
        """
        self.ensure_one()
        segments = [self.name]
        directory = self.directory_id
        seen = set()
        while directory and not directory.is_root_directory:
            if directory.id in seen:
                _logger.warning(
                    "Cyclic parent chain in dms.directory %s — stopping",
                    directory.id,
                )
                break
            seen.add(directory.id)
            segments.insert(0, directory.name)
            directory = directory.parent_id
        if directory and directory.is_root_directory:
            # Rotkatalogens namn är monteringspunkten i dms_webdav.
            segments.insert(0, directory.name)
        return "/" + "/".join(
            [webdav_root.strip("/")] + [s for s in segments if s]
        )

    # ------------------------------------------------------------------
    # Skapa
    # ------------------------------------------------------------------
    def action_new_whiteboard(self):
        """Skapa en tom Excalidraw-ritning i aktuell katalog.

        Anropas från DMS-filvyns "New whiteboard"-knapp. Returnerar en
        action som öppnar den nyskapade filen direkt i Excalidraw, så
        användaren slipper leta upp den.
        """
        # Ingen ensure_one(): metoden anropas medvetet på en TOM recordset
        # från katalogvyn (dms.directory.action_new_whiteboard delegerar hit),
        # där katalogen kommer ur context['default_directory_id']. Ett
        # ensure_one() här gör att fallbacken på nästa rad aldrig nås.
        if self._name != "dms.file":
            raise UserError(_("Denna åtgärd kräver en dms.file-post."))

        # Anropas på en tom recordset från en katalogvy: context bär
        # default_directory_id. Annars används postens egen katalog.
        directory_id = self.directory_id.id or self.env.context.get(
            "default_directory_id"
        )
        if not directory_id:
            raise UserError(
                _(
                    "Ingen katalog angiven. Öppna en DMS-katalog och "
                    "skapa whiteboarden därifrån."
                )
            )

        name = self.env.context.get("default_name") or _("Whiteboard")
        if not name.lower().endswith(f".{EXCALIDRAW_EXTENSION}"):
            name = f"{name}.{EXCALIDRAW_EXTENSION}"

        scene = json.dumps(EMPTY_SCENE, separators=(",", ":")).encode("utf-8")
        new_file = self.create(
            {
                "name": name,
                "directory_id": directory_id,
                "content": base64.b64encode(scene),
                "mimetype": "application/json",
            }
        )
        _logger.info(
            "Created whiteboard dms.file %s (%s) in directory %s",
            new_file.id,
            name,
            directory_id,
        )
        return new_file.open_in_excalidraw_action()
