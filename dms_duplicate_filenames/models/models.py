# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools
import logging
from odoo.exceptions import ValidationError

from odoo.addons.dms.tools import file
_logger = logging.getLogger(__name__)

class File(models.Model):

    _inherit = "dms.file"

    @api.constrains("name")
    def _check_name(self):
        for record in self:
            if not file.check_name(record.name):
                raise ValidationError(_("The file name is invalid."))
            files = record.sudo().directory_id.file_ids.name_get()