from odoo import models, fields


class DMSFile(models.Model):
    _name = 'dms.file'
    ##if VERSION <= "16.0"
    _inherit = ['dms.file', 'signature.mixin']
    ##elif VERSION >= "17.0"
    _inherit = ['dms.file']
    ##endif
    web_content = fields.Html(string="Web Content")

    def reset_signature(self):
        self.write({
            'signature': False,
            'signed_date': False,
        })
