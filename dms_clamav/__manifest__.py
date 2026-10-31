# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "DMS Antivirus (ClamAV)",
    "summary": "Scan every DMS file write with ClamAV before it is stored",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "LGPL-3",
    "depends": ["dms"],
    "external_dependencies": {"python": ["clamd"]},
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
    "description": """
DMS Antivirus (ClamAV)
======================

Every write to ``dms.file.content`` is scanned before the content is stored.
An infected file is rejected and never reaches the storage backend.

* Scans in ``write()`` before ``super().write()``, so the bytes are still in
  memory and nothing has been persisted yet.
* Runs **before** the version snapshot in ``dms_version``: an infected file
  must not become a version either.
* Fail-open: if clamd is not reachable the file is stored and a warning is
  logged. A ClamAV restart must not take the whole DMS down.
* Every rejection is logged with user, file name and signature.
    """,
}
