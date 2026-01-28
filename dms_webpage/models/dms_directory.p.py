from odoo import models, fields, api


class DMSDirectory(models.Model):
    _name = 'dms.directory'
    
    _inherit = ['dms.directory', 'website.published.mixin']


    @api.depends_context('lang')
    def _compute_website_url(self):
        for record in self:
            record.website_url = f'/my/dms/directory/{record.id}'
