# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "DMS Trash",
    "summary": "Soft delete with a per-directory retention delay",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "LGPL-3",
    "depends": ["dms"],
    "data": [
        "views/dms_directory_views.xml",
        "data/ir_cron_data.xml",
    ],
    "installable": True,
    "application": False,
    "description": """
DMS Trash
=========

A deleted file goes to the trash instead of vanishing. ``dms.directory``
gets a ``deletion_delay`` in days (0 = off, the default): while the delay
runs the file is archived with a ``deletion_date``, and a daily cron removes
it for good once the date has passed.

Restoring before the deadline is a matter of clearing the archive flag.
    """,
}
