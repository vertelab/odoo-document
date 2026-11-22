# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2022- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
##############################################################################

from odoo import fields, models


class DmsRecordTestInherit(models.Model):
    """Access mode ``inherit`` — attachment storage."""

    _name = "dms.record.test.inherit"
    _description = "DMS Record Test (inherit)"
    _inherit = ["dms.record.mixin"]

    _dms_storage_xmlid = "dms_record.test_storage_inherit"
    _dms_access_mode = "inherit"

    name = fields.Char(required=True)


class DmsRecordTestTeam(models.Model):
    """Access mode ``team`` — attachment storage plus an access group."""

    _name = "dms.record.test.team"
    _description = "DMS Record Test (team)"
    _inherit = ["dms.record.mixin"]

    _dms_storage_xmlid = "dms_record.test_storage_team"
    _dms_access_mode = "team"

    name = fields.Char(required=True)

    def _dms_access_group(self):
        self.ensure_one()
        group = self.env.ref(
            "dms_record.test_access_group", raise_if_not_found=False
        )
        if not group:
            group = self.env["dms.access.group"].search(
                [("name", "=", "DMS Record Test Team")], limit=1
            )
        return group


class DmsRecordTestOwner(models.Model):
    """Access mode ``owner`` — filestore storage."""

    _name = "dms.record.test.owner"
    _description = "DMS Record Test (owner)"
    _inherit = ["dms.record.mixin"]

    _dms_storage_xmlid = "dms_record.test_storage_owner"
    _dms_access_mode = "owner"

    name = fields.Char(required=True)

    def _dms_owner_field(self):
        self.ensure_one()
        return "create_uid"


class DmsRecordTestNoStorage(models.Model):
    """A bridge that forgot to declare its storage."""

    _name = "dms.record.test.no.storage"
    _description = "DMS Record Test (no storage)"
    _inherit = ["dms.record.mixin"]

    _dms_access_mode = "inherit"

    name = fields.Char(required=True)


class DmsRecordTestBadMode(models.Model):
    """A bridge that declared an access mode that does not exist."""

    _name = "dms.record.test.bad.mode"
    _description = "DMS Record Test (bad mode)"
    _inherit = ["dms.record.mixin"]

    _dms_storage_xmlid = "dms_record.test_storage_inherit"
    _dms_access_mode = "nonsense"

    name = fields.Char(required=True)
