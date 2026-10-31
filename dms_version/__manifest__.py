# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "DMS File Versioning",
    "summary": "Keep a version history of every DMS file write",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "LGPL-3",
    "depends": ["dms"],
    "data": [
        "security/ir.model.access.csv",
        "views/dms_file_views.xml",
        "data/ir_cron_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "description": """
DMS File Versioning
===================

``dms.file.content`` is a non-stored binary field: every write goes through
``_inverse_content`` and overwrites the previous blob in place. This module
keeps the previous content as a ``dms.file.version`` record before each
overwrite, so a file can be restored.

* One version per overwrite, whatever the source (form, WebDAV, SFTP, API, PWA)
* Retention policy per directory (count and/or age)
* Restore a previous version (which itself creates a new version)
* Existing files get an initial version on install (idempotent post-init hook)
    """,
}
