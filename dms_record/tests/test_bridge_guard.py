# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2022- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
##############################################################################
"""Guard: every ``dms_*`` bridge must actually be installable.

The failure this catches is not a wrong value, it is a *missing key*. All 18
bridges were correct and none of them declared ``auto_install``, so 14 sat
uninstalled in production while the code looked finished. A convention in a
README does not catch that; a test does.

The guard discovers bridges by walking the addons path for ``dms_*/``
directories, so a new bridge is covered without editing this file. The one
thing that can rot is :data:`NON_BRIDGE_MODULES` — every name in it is asserted
to still exist on disk, so a stale entry fails loudly instead of silently
exempting a real bridge.
"""

import ast
import logging
import os

from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon

_logger = logging.getLogger(__name__)

#: ``dms_*`` modules that are not bridges: the shared mixin, the access layer,
#: the storage backends and the UI features. Every name here must exist on disk.
NON_BRIDGE_MODULES = {
    "dms_record",  # the shared mixin
    "dms_webdav",  # WebDAV endpoint
    "dms_excalidraw",  # whiteboard rendering on dms.file
    "dms_mobile",  # PWA camera capture, no per-record directory
    "dms_version",  # file versioning
    "dms_sftp",  # SFTP access
    "dms_sync_rclone",  # rclone sync
    "dms_trash",  # trash bin
    "dms_hierarchy",  # directory hierarchy
    "dms_clamav",  # virus scanning
    "dms_ai",  # AI features
    "dms_extract",  # text extraction into the OKF body, no per-record directory
    "dms_oca_fixes",  # OCA patches
    "dms_auto_classification",  # classification
    "dms_duplicate_filenames",  # filename handling
    "dms_field",  # inline DMS field
    "dms_field_auto_classification",  # OCA: classification into the embedded field
    "dms_user_role",  # role-based access
    "dms_account_analytic_account",  # analytic account field
}

#: Dependencies a bridge always declares; the domain module is the one that is
#: neither of these.
BASE_DEPENDS = {"dms", "dms_record"}


def _addons_paths():
    """Every directory Odoo searches for addons."""
    from odoo import tools

    return [
        path.strip()
        for path in (tools.config["addons_path"] or "").split(",")
        if path.strip() and os.path.isdir(path.strip())
    ]


def _discover_dms_modules():
    """Map module name -> manifest path for every ``dms_*`` module on disk."""
    found = {}
    for root in _addons_paths():
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for entry in entries:
            if not entry.startswith("dms_"):
                continue
            manifest = os.path.join(root, entry, "__manifest__.py")
            if os.path.isfile(manifest):
                found.setdefault(entry, manifest)
    return found


def _read_manifest(path):
    """Parse a manifest without importing it."""
    with open(path, encoding="utf-8") as handle:
        return ast.literal_eval(handle.read())


@tagged("post_install", "-at_install")
class TestBridgeGuard(BaseCommon):
    """Every bridge declares a domain module and auto-installs on it."""

    def test_skip_list_entries_still_exist(self):
        """A stale skip-list entry must fail, not silently exempt a bridge."""
        on_disk = _discover_dms_modules()
        stale = sorted(NON_BRIDGE_MODULES - set(on_disk))
        self.assertFalse(
            stale,
            "NON_BRIDGE_MODULES names modules that no longer exist on disk: "
            f"{stale}. Remove them from the skip list — a stale entry would "
            "silently exempt a future bridge with that name.",
        )

    def test_bridges_are_discovered(self):
        """The guard must actually find the bridges, not pass on an empty set."""
        bridges = self._bridges()
        self.assertGreaterEqual(
            len(bridges),
            18,
            f"Expected at least 18 bridges, found {len(bridges)}: "
            f"{sorted(bridges)}. If a bridge was removed on purpose, lower "
            "this floor deliberately.",
        )

    def test_every_bridge_declares_a_domain_module(self):
        """A bridge whose domain module is undeclared can never auto-install."""
        offenders = []
        for name, manifest in sorted(self._bridges().items()):
            depends = set(manifest.get("depends") or [])
            domain = depends - BASE_DEPENDS
            if not domain:
                offenders.append(
                    f"{name}: depends={sorted(depends)} declares no domain "
                    "module beyond dms/dms_record"
                )
        self.assertFalse(
            offenders,
            "Bridges with no domain module:\n  " + "\n  ".join(offenders),
        )

    def test_every_bridge_auto_installs(self):
        """The bug this whole change exists for: a bridge nobody installs."""
        offenders = []
        for name, manifest in sorted(self._bridges().items()):
            if manifest.get("auto_install") is not True:
                offenders.append(
                    f"{name}: auto_install={manifest.get('auto_install')!r}"
                )
        self.assertFalse(
            offenders,
            "Bridges that will never install themselves:\n  "
            + "\n  ".join(offenders),
        )

    def test_the_mixin_does_not_auto_install(self):
        """``dms_record`` must arrive as a dependency, never on its own."""
        manifest_path = _discover_dms_modules().get("dms_record")
        self.assertTrue(manifest_path, "dms_record not found on the addons path")
        manifest = _read_manifest(manifest_path)
        self.assertNotEqual(
            manifest.get("auto_install"),
            True,
            "dms_record must not auto_install — it would appear in every "
            "database that has dms, explaining nothing.",
        )
        self.assertIn(
            "dms_record",
            NON_BRIDGE_MODULES,
            "dms_record must be in the skip list, or the guard checks it as a "
            "bridge and demands a domain module it does not have.",
        )

    def test_unrunnable_bridges_are_reported(self):
        """A bridge whose domain module is absent must be visible, not silent.

        Those bridges have no tests in this run — Odoo never imports them — so
        without this the gap looks exactly like a pass. Report it instead.
        """
        installed = set(
            self.env["ir.module.module"]
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        unrunnable = []
        for name, manifest in sorted(self._bridges().items()):
            domain = set(manifest.get("depends") or []) - BASE_DEPENDS
            if domain and not domain & installed:
                unrunnable.append(f"{name} (needs {sorted(domain)[0]})")
        if unrunnable:
            # Not a failure: an uninstalled domain module is a legitimate
            # state. But it must be printed, so nobody reads this run as
            # "all bridges verified".
            _logger.warning(
                "Bridges with no tests in this run (domain module not "
                "installed): %s",
                ", ".join(unrunnable),
            )
        self.assertTrue(True)

    def _bridges(self):
        """Module name -> manifest dict, for every bridge on disk."""
        return {
            name: _read_manifest(path)
            for name, path in _discover_dms_modules().items()
            if name not in NON_BRIDGE_MODULES
        }
