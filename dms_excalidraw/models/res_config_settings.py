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

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dms_excalidraw_url = fields.Char(
        string="Excalidraw URL",
        config_parameter="dms_excalidraw.url",
        help=(
            "Bas-URL till den fristående Excalidraw-tjänsten, t.ex. "
            "https://whiteboard.vertel.se. Utan denna kan whiteboards inte "
            "öppnas — knappen ger ett tydligt fel i stället för en trasig "
            "länk."
        ),
    )

    dms_excalidraw_webdav_path = fields.Char(
        string="DMS WebDAV path",
        config_parameter="dms_excalidraw.webdav_path",
        default="/webdav",
        help=(
            "Sökvägen där dms_webdav monterar DMS-trädet. Ändra bara om "
            "modulen konfigurerats med en annan mount-punkt."
        ),
    )
