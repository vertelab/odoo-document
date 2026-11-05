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
    "name": "Office Download: Collabora",
    "summary": "Download links for the Collabora Office desktop suite",
    "description": """
Download page for the local office suite that matches this database
====================================================================

A customer who gets Collabora Online through `collabora.repo` also wants the
desktop suite. This module adds a menu item under Documents listing the
platforms Collabora Office is available for, with links to the vendor's own
downloads.

WHY THIS MODULE EXISTS
======================
Without it the customer googles, and lands on Euro-Office instead — an editor
that does not match their server. The suite follows the repo: `collabora.repo`
installs this module, `euro-office.repo` installs its sibling. The two declare
`conflicts` against each other, exactly like their repos, because one database
gets one office backend.

WHY THE LINKS ARE RECORDS AND NOT CODE
======================================
Vendors release new builds. Collabora is at 26.04 today. Hardcoding the URLs in
`data/` would turn every vendor release into a module deploy; the records are
`noupdate="1"` so an administrator can correct a URL in the UI and keep the
edit across upgrades.

WHY NO OPERATING-SYSTEM DETECTION
=================================
The page lists the platforms we have rather than guessing the visitor's. User
Agent sniffing is unreliable — an iPad reports `Macintosh`, and ARM versus
Intel Mac is invisible in the UA — and a wrong guess that hides the right row
is worse than a short list.

PLATFORM LIMITS ARE STATED, NOT HIDDEN
======================================
Collabora Office is free for Windows 11 64-bit only, macOS 15 Sequoia or later
on Apple silicon only, and Linux x86_64 only. A customer on Windows 10 or an
Intel Mac gets nothing, and should learn that from the `note` field rather than
after a failed download.
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
    "pre_init_hook": "pre_init_check_no_euro_office",
    "conflicts": ["office_download_euro_office"],
    "installable": True,
    "application": False,
}
