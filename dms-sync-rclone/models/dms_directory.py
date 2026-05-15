import logging
import subprocess

from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError, ValidationError

_logger = logging.getLogger(__name__)

class DMSDirectory(models.Model):
    _inherit = 'dms.directory'

    def sync_rclone(self):
        command = [
            "ssh", 
            "-l", "root", 
            "storage.vertel.se", 
            "systemctl", "restart", "*-rclone"
        ]
    
        try:
            # check=True will raise an exception if the command returns a non-zero exit code
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            raise UserError(f"An error occurred while running the command: {e}")
