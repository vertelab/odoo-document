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
