import io
import logging
from lxml import etree

from odoo import SUPERUSER_ID, api, tools

try:
    from paramiko.ecdsakey import ECDSAKey
except ImportError:
    pass

_logger = logging.getLogger(__name__)


def install_hook(env):
    hostkey = env["ir.config_parameter"].get_param("dms_sftp.hostkey")
    parameters = etree.parse(
        tools.file_open("dms_sftp/data/ir_config_parameter.xml")
    )
    default_value = None
    for node in parameters.xpath("//record[@id='param_hostkey']//field[@name='value']"):
        default_value = node.text
    if not hostkey or hostkey == default_value:
        _logger.info("Generating SFTP host key for database %s", env.cr.dbname)
        key = io.StringIO()
        ECDSAKey.generate().write_private_key(key)
        env["ir.config_parameter"].set_param("dms_sftp.hostkey", key.getvalue())
        key.close()


def uninstall_hook(env):
    pass


from . import models
