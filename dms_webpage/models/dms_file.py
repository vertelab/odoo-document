from odoo import models, fields
import os
import logging

_logger = logging.getLogger(__name__)

class DMSFile(models.Model):
    _inherit = 'dms.file'
    web_content = fields.Html(string="Web Content")

    def reset_signature(self):
        self.write({
            'signature': False,
            'signed_date': False,
        })

    def _get_full_path(self):
        self.ensure_one()
        storage = self.directory_id.storage_id.storage_backend_id

        if storage and storage.directory_path:
            return os.path.join(storage.directory_path,self.directory_id.complete_name,self.name)
        return False    

    def unlink(self):
        for rec in self:
            full_path = rec._get_full_path()

            if full_path and os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                        _logger.info(f"Raderar lokal fil: {full_path}")
                    except OSError as e:
                        _logger.warning(f"Kunde inte radera lokal fil {full_path}: {e}")

        return super().unlink()
