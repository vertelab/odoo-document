from odoo import models, fields, api, _


class DMSFile(models.Model):
    _name = 'dms.file'
    _inherit = [
        "dms.file",
        "portal.mixin",
    ]

    is_template = fields.Boolean(string="Is Template")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company.id)
    file_template_id = fields.Many2one('dms.file', string="File Template")
    partner_id = fields.Many2one('res.partner', string="Partner")


class EmailDMSFile(models.TransientModel):
    _name = 'partner.dms.file'
    _description = 'Email Partner Documents'

    res_id = fields.Integer('Document ID')
    res_ids = fields.Char('Document IDs')
    require_customer_signature = fields.Boolean(string='Signature Required', default=True)
    dms_file = fields.Many2one('dms.file', string="DMS File", required=True, domain="[('is_template', '=', True)]")
    email_template = fields.Many2one('mail.template', string="Template", required=True,
                                     domain="[('model_id', '=', 'dms.file')]")
    file_name = fields.Char(string="File Name", required=True)

    @api.onchange('dms_file')
    def set_file_name(self):
        if self.dms_file:
            self.file_name = self.dms_file.name

    def action_email_partner(self):
        active_ids = self.env.context.get('active_ids')
        template = self.env.ref('mail_dms_partner.mail_template_partner_signature', raise_if_not_found=False)
        for partner in self.env['res.partner'].browse(active_ids):
            attachment_id = self.env['ir.attachment'].create({
                'name': self.file_name,
                'datas': self.dms_file.content,
                'mimetype': self.dms_file.mimetype,
                'res_model': 'res.partner',
                'res_id': partner.id,
                'res_name': partner.name,
            })
            if file_id := self.env['dms.file'].search([('attachment_id', '=', attachment_id.id)], limit=1):
                file_id.write({
                    'require_signature': self.require_customer_signature,
                    'web_content': self.dms_file.web_content,
                    'file_template_id': self.dms_file.id,
                    'partner_id': partner.id
                })
            file_id._portal_ensure_token()
            if template and partner.email:
                template.sudo().send_mail(file_id.id, force_send=True)
