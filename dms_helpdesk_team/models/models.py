# -*- coding: utf-8 -*-
from odoo import models


class HelpdeskTeam(models.Model):
    _name = "helpdesk.ticket.team"
    _inherit = ["helpdesk.ticket.team", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_helpdesk_team.helpdesk_team_dms_storage"
    _dms_access_mode = "team"

    def _dms_access_group(self):
        """The helpdesk team's responsible user.

        ``helpdesk.ticket.team`` has no ``member_ids``; ``user_id`` is the
        only membership field it carries.
        """
        self.ensure_one()
        return self._dms_get_or_create_access_group(
            name=f"Helpdesk team: {self.display_name}",
            users=self.user_id,
        )
