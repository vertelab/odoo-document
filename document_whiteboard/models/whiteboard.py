from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import uuid


class Whiteboard(models.Model):
    _inherit = 'ir.attachment'
    
    type = fields.Selection(selection_add=[('whiteboard', 'Whiteboard')],
                            ondelete={"whiteboard": "set default"})

    url = fields.Char('Url', index=True, size=1024, compute='_create_whiteboard_url', inverse='_inverse_country',
                      store=True, readonly=False)

    url_dummy = fields.Html(string='URL Dummy', compute="onchange_url_dummy")

    @api.depends('url')
    def onchange_url_dummy(self):
        if self.url:
            self.url_dummy = '<img id="img" src="%s" style="display: none;"/>' % self.url

    @api.depends('type')
    def _create_whiteboard_url(self):
        for rec in self:
            if rec.type == 'whiteboard':
                whiteboard_base_url = self.env['ir.config_parameter'].sudo().get_param('whiteboard_base_url')
                if not whiteboard_base_url:
                    ValidationError(_("No WhiteBoard URL Defined"))
                self.url = f"{whiteboard_base_url}/?whiteboardid={uuid.uuid4()}"

    def _inverse_country(self):
        pass

    def view_url(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'form',
            'view_id': self.env.ref('document_whiteboard.view_url_wizard').id,
            'res_id': self.id,
            'target': 'current',
            'flags': {'mode': 'readonly'},
        }

