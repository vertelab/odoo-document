# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    document_sftp_bind = fields.Char(string='Document_SFTP Bind', config_parameter='document_sftp.bind')
    document_sftp_hostkey = fields.Char(string='Document_SFTP Hostkey', config_parameter='document_sftp.hostkey')