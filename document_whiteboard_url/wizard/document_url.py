# Copyright 2014 Tecnativa - Pedro M. Baeza
# Copyright 2020 Tecnativa - Manuel Calero
# Copyright 2016 ACSONE SA/NV (<http://acsone.eu>)
from urllib import parse

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import uuid


class WhiteboardWizard(models.TransientModel):
    _inherit = "ir.attachment.add_url"

    is_whiteboard_url = fields.Boolean(string="Whiteboard URL")

    @api.onchange('is_whiteboard_url')
    def _create_whiteboard_url(self):
        if self.is_whiteboard_url:
            whiteboard_base_url = self.env['ir.config_parameter'].sudo().get_param('whiteboard_base_url')
            if not whiteboard_base_url:
                ValidationError(_("No WhiteBoard URL Defined"))
            self.url = f"{whiteboard_base_url}/?whiteboardid={uuid.uuid4()}"

    def action_add_url(self):
        """Adds the URL with the given name as an ir.attachment record."""
        if not self.env.context.get("active_model"):
            return
        attachment_obj = self.env["ir.attachment"]
        for form in self:
            url = parse.urlparse(form.url)
            if not url.scheme:
                url = parse.urlparse("{}{}".format("http://", form.url))
            for active_id in self.env.context.get("active_ids", []):
                attachment = {
                    "name": form.name,
                    "type": "whiteboard" if self.is_whiteboard_url else "url",
                    "url": url.geturl(),
                    "res_id": active_id,
                    "res_model": self.env.context["active_model"],
                }
                attachment_obj.create(attachment)
        return {"type": "ir.actions.act_window_close"}
