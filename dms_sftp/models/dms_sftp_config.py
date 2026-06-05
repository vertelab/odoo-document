from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dms_sftp_bind = fields.Char(
        string="SFTP Bind Address",
        config_parameter="dms_sftp.bind",
        default="localhost:2222",
    )
    dms_sftp_readonly = fields.Boolean(
        string="SFTP Read-only",
        config_parameter="dms_sftp.readonly",
        default=False,
    )
