# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "DMS Mobile Capture",
    "summary": "Photograph a document straight into a DMS directory",
    "version": "18.0.1.0.9",
    "category": "Document Management",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "LGPL-3",
    "depends": ["dms", "dms_field", "web_pwa_push"],
    "data": [
        "security/ir.model.access.csv",
        "data/web_pwa_app_data.xml",
        "views/dms_directory_views.xml",
    ],
    "installable": True,
    "application": False,
    "description": """
DMS Mobile Capture
==================

The DMS is desktop-only in practice: a field technician who photographs
damage, a salesperson who photographs a quote attachment, or a manager
approving receipts on a phone has no way in.

This module registers a PWA app with ``web_pwa_push`` and implements the
callback that receives the files. ``web_pwa_push`` provides the camera page
and the upload endpoint; it never learns what a document is. This module
knows, and decides where the file lands.

* A directory can be marked as a mobile target
* ``/dms/mobile`` lists those directories with a camera button each
* Uploads are created as ``dms.file`` with ``capture_source='pwa'``
    """,
}
