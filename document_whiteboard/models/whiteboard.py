from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class Whiteboard(models.Model):
    _inherit = 'ir.attachment'
    
    type = fields.Selection(selection_add=[('whiteboard', 'Whiteboard')])
    
