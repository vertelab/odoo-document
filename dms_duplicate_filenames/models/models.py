# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _
import logging
from odoo.exceptions import ValidationError

from odoo.addons.dms.tools import file

_logger = logging.getLogger(__name__)


class File(models.Model):
    _inherit = "dms.file"

    @api.constrains("name")
    def _check_name_valid(self):
        """Reject a name with characters dms does not allow.

        Named explicitly rather than _check_name: document_version declares a
        method of that name on dms.file too, and two same-named methods on one
        model means whichever module loads last wins. This check was the one
        that could be silently dropped.
        """
        for record in self:
            if not file.check_name(record.name):
                raise ValidationError(_("The file name is invalid."))