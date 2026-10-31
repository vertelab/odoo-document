# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "DMS OCA Fixes",
    "summary": "Three OCA/dms fixes as overrides instead of source patches",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "LGPL-3",
    "depends": ["dms", "dms_field"],
    "installable": True,
    "application": False,
    "description": """
DMS OCA Fixes
=============

Three fixes that used to be applied by rewriting OCA source in
``/usr/share/odooext-OCA-dms/`` from ``clicktest.sls``. A source patch is
lost on the next ``repo_apply`` and silently reverts a bug that was fixed
months ago. These are ``_inherit`` overrides instead, so they survive an
update.

1. ``dms.directory._check_name`` ignored the ``check_name=False`` context
   flag for the duplicate check (only the invalid-character check honoured
   it), so programmatic creation of a colliding name raised where it should
   not.
2. ``ir.attachment._dms_directories_create`` used the record's display name
   verbatim, so two records with the same display name produced duplicate
   directory names.
3. ``dms.field.template.create_dms_directory`` had the same problem.

The fixes are upstream candidates. Until OCA takes them, this module is the
supported place for them.
    """,
}
