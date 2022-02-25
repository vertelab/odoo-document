from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class Whiteboard(models.Model):
    _inherit = 'ir.attachment'
    
    type = fields.Selection([('url', 'URL'), ('binary', 'File')],
        string='Type', required=True, default='binary', change_default=True,
        help="You can either upload a file from your computer or copy/paste an internet link to your file.")
    
