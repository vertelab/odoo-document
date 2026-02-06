from odoo import models, fields
##if VERSION >= "17.0"
import os
import logging

_logger = logging.getLogger(__name__)
##endif

class DMSFile(models.Model):
    ##if VERSION <= "16.0"
    _inherit = ['dms.file', 'signature.mixin']
    ##elif VERSION >= "17.0"
    _inherit = 'dms.file'
    ##endif
    web_content = fields.Html(string="Web Content")

    def reset_signature(self):
        self.write({
            'signature': False,
            'signed_date': False,
        })

    ##if VERSION >= "17.0"
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
    ##endif