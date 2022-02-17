# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from . import models


import logging
import io
import socket
from lxml import etree
from odoo import SUPERUSER_ID, tools, api


try:
    from paramiko.ecdsakey import ECDSAKey
except ImportError:  # pragma: no cover
    pass
_logger = logging.getLogger(__name__)


def install_hook(cr, registry):
    _logger.warning('Socket %s' % socket.getfqdn())
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    if socket.getfqdn().endswith('odoo-community.org'):  # pragma: no cover
        # we need a different default listeing address on runbot
        env['ir.config_parameter'].set_param('document_sftp.bind', '%s:0' % socket.getfqdn())
    hostkey = env['ir.config_parameter'].get_param('document_sftp.hostkey')
    parameters = etree.parse(
        tools.file_open('document_sftp/data/ir_config_parameter.xml'))
    default_value = None
    for node in parameters.xpath("//record[@id='param_hostkey']//field[@name='value']"):
        default_value = node.text
    if not hostkey or hostkey == default_value:
        _logger.info('Generating host key for database %s', cr.dbname)
        key = io.StringIO()
        ECDSAKey.generate().write_private_key(key)
        env['ir.config_parameter'].set_param('document_sftp.hostkey', key.getvalue())
        key.close()


def uninstall_hook(cr, registry):
    pass
