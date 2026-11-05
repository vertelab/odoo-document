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

{
    "name": "Office Download: Euro-Office",
    "summary": "Download links for the Euro-Office desktop suite",
    "description": """
Download page for the local office suite that matches this database
====================================================================

A customer who gets Euro-Office through `euro-office.repo` also wants the
desktop suite. This module adds a menu item under Documents listing the
platforms Euro-Office is available for.

WHY THE LINKS POINT AT NEXTCLOUD AND NOT AT EURO-OFFICE
=======================================================
Euro-Office publishes **no signed binaries of its own**. Its README states:

    Signed builds are available as Nextcloud Office, which also offers APT and
    DNF package repositories. Unsigned community builds are published on the
    releases page of this repository.

Linking to `Euro-Office/DesktopEditors/releases` would hand the customer an
unsigned binary — on Windows that means a SmartScreen warning and an IT
department that says no. The signed path is Nextcloud's
`nextcloud-releases/Office-DesktopEditors`.

The consequence is that the customer clicks "Euro-Office" and meets "Nextcloud
Office" branding. That is the same program, but it looks like a mistake unless
it is stated — hence the `note` field on every record.

WHY WE LINK AND DO NOT MIRROR
=============================
Euro-Office is AGPL-3.0. Hosting our own copies would make us a distributor,
and § 6 then requires offering the corresponding source to every recipient.
Linking avoids the obligation and leaves updates and signing where they belong:
with the vendor.

WHY NO OPERATING-SYSTEM DETECTION
=================================
The page lists the platforms we have rather than guessing the visitor's. See
the sibling module `office_download_collabora` for the full reasoning.
""",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "category": "Productivity/Documents",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["dms"],
    "data": [
        "security/ir.model.access.csv",
        "data/office_download_link_data.xml",
        "views/office_download_views.xml",
    ],
    "pre_init_hook": "pre_init_check_no_collabora",
    "conflicts": ["office_download_collabora"],
    "installable": True,
    "application": False,
}
