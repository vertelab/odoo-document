from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dms_webdav_readonly = fields.Boolean(
        string="WebDAV Read-only",
        config_parameter="dms_webdav.readonly",
        default=False,
    )
