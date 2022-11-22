from odoo import models, fields


class DMSFile(models.Model):
    _name = 'dms.file'
    _inherit = ['dms.file', 'signature.mixin']

    web_content = fields.Html(string="Web Content")

    def reset_signature(self):
        self.write({
            'signature': False,
            'signed_date': False,
        })
