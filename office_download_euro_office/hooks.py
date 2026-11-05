# -*- coding: utf-8 -*-
"""Refuse to install alongside the Collabora download module.

`conflicts` in the manifest is enforced by repo_apply, not by Odoo's own
installer — installing directly with `-i` bypasses it. Verified 2026-11-05:
both modules installed cleanly in the same database, which is exactly the state
the two office backends must never share. This hook closes that hole.
"""
from odoo.exceptions import ValidationError


def pre_init_check_no_collabora(env):
    other = env["ir.module.module"].search(
        [("name", "=", "office_download_collabora"), ("state", "=", "installed")]
    )
    if other:
        raise ValidationError(
            "office_download_euro_office cannot be installed: "
            "office_download_collabora is already installed. "
            "One database gets one office backend — uninstall the Collabora "
            "modules first (or use office/init.sls, which does it for you)."
        )
