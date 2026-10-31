# -*- coding: utf-8 -*-
from odoo import models


class CrmLead(models.Model):
    _name = "crm.lead"
    _inherit = ["crm.lead", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_crm_lead.crm_lead_dms_storage"
    _dms_access_mode = "inherit"
