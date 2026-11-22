# -*- coding: utf-8 -*-
from odoo import models


class HelpdeskTicket(models.Model):
    _name = "helpdesk.ticket"
    _inherit = ["helpdesk.ticket", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_helpdesk_ticket.helpdesk_ticket_dms_storage"
    _dms_access_mode = "inherit"
