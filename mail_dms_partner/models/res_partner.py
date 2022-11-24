from odoo import models, fields, api, _


class Partner(models.Model):
    _inherit = 'res.partner'

    file_ids = fields.One2many('dms.file', 'partner_id', string="Files")