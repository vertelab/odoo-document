# -*- coding: utf-8 -*-
from odoo import models


class CrmTeam(models.Model):
    _name = "crm.team"
    _inherit = ["crm.team", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_crm_team.crm_team_dms_storage"
    _dms_access_mode = "team"

    def _dms_access_group(self):
        """The sales team's own members.

        ``crm.team.member_ids`` is the authoritative list, so the group is
        keyed on it rather than on the team leader alone.
        """
        self.ensure_one()
        return self._dms_get_or_create_access_group(
            name=f"CRM team: {self.display_name}",
            users=self.member_ids,
        )
