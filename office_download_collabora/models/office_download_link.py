# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2026- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, fields, models


class OfficeDownloadLink(models.Model):
    """One downloadable build of an office suite.

    Deliberately a plain model and not code: vendors ship new releases and an
    administrator must be able to correct a URL without a module upgrade. See
    the manifest for why the page does not sniff the visitor's operating
    system.
    """

    _name = "office.download.link"
    _description = "Office suite download link"
    _order = "sequence, id"

    name = fields.Char(
        string="Name",
        required=True,
        help="What the customer sees, e.g. 'Collabora Office for Windows'.",
    )
    platform = fields.Selection(
        selection=[
            ("windows", "Windows"),
            ("macos", "macOS"),
            ("linux", "Linux"),
            ("android", "Android"),
            ("ios", "iOS / iPadOS"),
        ],
        string="Platform",
        required=True,
    )
    os_family = fields.Char(
        string="OS version",
        help="Which versions of the platform this build supports, e.g. "
             "'Windows 11 (64-bit)'. Stated explicitly because the supported "
             "range is narrower than customers expect.",
    )
    url = fields.Char(
        string="Download URL",
        required=True,
        help="Vendor or app-store URL. We link, we do not mirror — hosting "
             "copies would make us a distributor.",
    )
    package_format = fields.Char(
        string="Format",
        help="Package format, e.g. '.appx', 'Flatpak', 'App Store'.",
    )
    note = fields.Text(
        string="Note",
        help="Limitations the customer must know before downloading, e.g. "
             "'Apple silicon only' or 'shows Nextcloud branding'.",
    )
    sequence = fields.Integer(string="Priority", default=10)
    active = fields.Boolean(string="Active", default=True)

    @api.depends("name", "platform")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.name
