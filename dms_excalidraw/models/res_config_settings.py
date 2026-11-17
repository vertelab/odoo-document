# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Surfaces over ir.config_parameter (design D7). The service URL is
    # per-installation infrastructure, not per-company business configuration,
    # and it is read from Python where a settings record would need a sudo()
    # lookup anyway.
    dms_excalidraw_url = fields.Char(
        string="Excalidraw URL",
        config_parameter="dms_excalidraw.url",
        help="Base URL of the Excalidraw service. Leave empty to disable "
        "opening whiteboards; the action then raises an error naming this "
        "setting instead of producing a broken link.",
    )
    dms_excalidraw_library_sync_enabled = fields.Boolean(
        string="Library sync",
        config_parameter="dms_excalidraw.library_sync_enabled",
        help="Allow the shape-library catalogue to be refreshed from the "
        "upstream Excalidraw catalogue. Off by default: an ERP that calls "
        "GitHub from a customer's server needs a decision behind it. The "
        "shipped catalogue works without this.",
    )
    dms_excalidraw_library_max_bytes = fields.Integer(
        string="Max library size (bytes)",
        config_parameter="dms_excalidraw.library_max_bytes",
        default=2 * 1024 * 1024,
        help="A library larger than this is refused when a user opens it, "
        "with the size named. A 500-shape library is not an asset, it is a "
        "denial of service on the editor.",
    )
    dms_excalidraw_webdav_path = fields.Char(
        string="WebDAV Path",
        config_parameter="dms_excalidraw.webdav_path",
        default="/webdav",
        help="Path prefix under which DMS serves WebDAV. The browser fetches "
        "the whiteboard from this path with the user's own session.",
    )
