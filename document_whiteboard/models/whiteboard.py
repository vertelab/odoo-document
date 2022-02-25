from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import uuid


class Whiteboard(models.Model):
    _inherit = 'ir.attachment'
    
    type = fields.Selection(selection_add=[('whiteboard', 'Whiteboard')],
        ondelete={"url": "set default"},)

    @api.model
    def create(self, vals):
        """
        Overrides orm create method.
        @param self: The object pointer
        @param vals: dictionary of fields value.
        """
        if vals['type'] == 'whiteboard':
            vals["url"] = uuid.uuid4()
        return super(Whiteboard, self).create(vals)
