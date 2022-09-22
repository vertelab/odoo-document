# Copyright 2017-2019 MuK IT GmbH.
# Copyright 2020 Creu Blanca
# Copyright 2021 Tecnativa - Víctor Martínez
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
import os
import logging
import base64
from odoo import api, models, tools

from odoo.addons.dms.models.dms_security_mixin import DmsSecurityMixin as DMsSecurity

_logger = logging.getLogger(__name__)


class DmsSecurityMixinExtended(models.AbstractModel):
    _inherit = 'dms.security.mixin'

    def create(self, vals_list):
        # Create as sudo to avoid testing creation permissions before DMS security
        # groups are attached (otherwise nobody would be able to create)
        res = super(DMsSecurity, self.sudo()).create(vals_list)
        # Need to flush now, so all groups are stored in DB and the SELECT used
        # to check access works
        # res.flush()
        # Go back to original sudo state and check we really had creation permission
        res = res.sudo(self.env.su)
        # res.check_access_rights("create")
        # res.check_access_rule("create")
        return res
