# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "DMS Vault",
    "summary": "Encrypt the bytes of a DMS directory before they reach storage",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "license": "LGPL-3",
    "depends": [
        "dms",
        "fs_attachment",
        # The extractor guard in models/dms_extract_guard.py overrides
        # ``dms.file._extract_needs_work``. Without this dependency the load
        # order is undefined and dms_extract's own definition can win, which
        # would silently let a vault file be decrypted and indexed.
        "dms_extract",
    ],
    "external_dependencies": {"python": ["cryptography"]},
    "data": [
        "security/ir.model.access.csv",
        "views/dms_vault_views.xml",
        "views/dms_directory_views.xml",
        "wizards/dms_vault_member_wizard_views.xml",
        "wizards/dms_vault_migrate_wizard_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "description": """
DMS Vault
=========

A DMS directory can be protected by ``dms.access.group``. That answers "who
may read this" but not "what happens if the database walks out the door".
Every byte sits in plaintext in the filestore or in the object storage, so a
database dump plus the filestore is a complete copy of every document.

A **vault** directory encrypts its files before the bytes reach storage, with
a key that does not live in the database.

Key hierarchy::

    odoo.conf: dms_vault_master_key
        -> member_key  = HKDF-SHA256(master, "vault-member:<uid>")
        -> content_key = random 32 bytes per vault, wrapped per member
        -> file bytes  = Fernet(content_key)

Adding or removing a member writes one row. No file is ever re-encrypted for a
membership change.

Encryption happens in ``ir.attachment._storage_file_write()`` — the single
point where bytes leave Odoo — not in ``dms.file``. ``dms_version`` creates its
own ``ir.attachment`` rows with ``res_model='dms.file'``, so the same lookup
catches the version snapshots too. Encrypting at ``dms.file`` would have left
plaintext copies in the version history.

READ THE README BEFORE ENABLING THIS ON A DIRECTORY. It lists what is lost.
    """,
}
