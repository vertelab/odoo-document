# -*- coding: utf-8 -*-
"""Upstream sync for the shape-library catalogue.

WHY SYNC IS OPT-IN
==================
An ERP that silently calls GitHub from a customer's server is a conversation
nobody wants during a security review (design D1). So the default is the
shipped seed and nothing else; a company that wants the full upstream
catalogue sets `dms_excalidraw.library_sync_enabled` and presses "Sync now".

WHY THE INDEX IS ONE REQUEST AND THE LIBRARIES ARE NOT
======================================================
`libraries.json` is ~40 KB and lists all 232 libraries. The libraries
themselves are ~100 MB together. Downloading all of them at sync time would
take minutes and fail halfway, so the sync stores METADATA ONLY and the
browser fetches a library when the user opens it (design D2).

WHAT A FAILED SYNC MUST NOT DO
==============================
Leave the catalogue in a worse state than it found it. Every write happens
after the index has been parsed; a 404, a timeout or a malformed index logs
and returns without touching a single record.
"""

import json
import logging
import urllib.error
import urllib.request

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The upstream catalogue. `libraries.json` is the index; `source` and
# `preview` in it are paths relative to `libraries/`, so a library's raw URL
# is `<raw base>/libraries/<source>`.
UPSTREAM_RAW_BASE = (
    "https://raw.githubusercontent.com/excalidraw/excalidraw-libraries/main/"
)
UPSTREAM_INDEX_URL = UPSTREAM_RAW_BASE + "libraries.json"

SYNC_ENABLED_PARAM = "dms_excalidraw.library_sync_enabled"
SYNC_TIMEOUT_PARAM = "dms_excalidraw.library_sync_timeout"

DEFAULT_TIMEOUT = 20


class DmsExcalidrawLibrarySync(models.Model):
    """Sync lives on the library model rather than in a wizard.

    It is one operation with one outcome, and it must be callable from a test
    and from a button. A transient wizard would only add a step.

    ⚠️ `_inherit` MUST match the model's `_name`, which is
    `dms_excalidraw.library` (the module's own prefix). An earlier version
    said `dms.excalidraw.library` — a plausible-looking name that does not
    exist — and Odoo silently registered an EXTENSION class under that name
    while the base class kept `dms_excalidraw.library`. The result was
    `TypeError: Model 'dms.excalidraw.library' does not exist in registry`
    at install, because the extension was built before its base.
    """

    _inherit = "dms_excalidraw.library"

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @api.model
    def _sync_enabled(self):
        """Return True when outbound sync is allowed.

        Read through `sudo()`: the parameter is installation configuration, not
        user data, and a library user has no business needing settings access
        to trigger a read of it.
        """
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(SYNC_ENABLED_PARAM, "False")
        )
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @api.model
    def _sync_timeout(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(SYNC_TIMEOUT_PARAM, str(DEFAULT_TIMEOUT))
        )
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return DEFAULT_TIMEOUT

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    @api.model
    def _fetch_bytes(self, url):
        """Fetch a URL and return its raw bytes.

        Separate from `_fetch_json` because a `.excalidrawlib` is fetched for
        the BROWSER to parse, not for the server: parsing it here would mean
        re-serialising it, and the picker must receive exactly the bytes the
        upstream published.
        """
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "odoo-dms-excalidraw-library/18.0",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._sync_timeout()
            ) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise UserError(
                _("Could not fetch %(url)s: HTTP %(code)s.",
                  url=url, code=error.code)
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise UserError(
                _("Could not reach %(url)s: %(reason)s.", url=url, reason=error)
            ) from error

    @api.model
    def _fetch_json(self, url):
        """Fetch and parse a JSON document.

        Raises `UserError` with a message naming the URL. The caller decides
        whether that is fatal (the index) or skippable (one library).
        """
        request = urllib.request.Request(
            url,
            headers={
                # GitHub serves raw content to any UA, but an explicit one is
                # polite and makes the request identifiable in their logs.
                "User-Agent": "odoo-dms-excalidraw-library/18.0",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._sync_timeout()
            ) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            raise UserError(
                _(
                    "Could not fetch %(url)s: HTTP %(code)s.",
                    url=url,
                    code=error.code,
                )
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise UserError(
                _("Could not reach %(url)s: %(reason)s.", url=url, reason=error)
            ) from error

        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise UserError(
                _("%(url)s did not return valid JSON: %(reason)s.",
                  url=url, reason=error)
            ) from error

    # ------------------------------------------------------------------
    # The sync
    # ------------------------------------------------------------------

    @api.model
    def _sync_from_upstream(self):
        """Pull the upstream index and upsert the catalogue.

        Returns a dict of counters so the button can report what happened
        without a second query:

            {"created": n, "updated": n, "deactivated": n, "skipped": n}
        """
        index = self._fetch_json(UPSTREAM_INDEX_URL)
        if not isinstance(index, list):
            raise UserError(
                _(
                    "The upstream index is not a list (got %s). The catalogue "
                    "was left unchanged.",
                    type(index).__name__,
                )
            )

        Library = self.with_context(active_test=False)
        counters = {"created": 0, "updated": 0, "deactivated": 0, "skipped": 0}
        seen = set()
        now = fields.Datetime.now()

        for entry in index:
            if not isinstance(entry, dict):
                counters["skipped"] += 1
                continue

            upstream_id = entry.get("id")
            name = entry.get("name")
            if not upstream_id or not name:
                _logger.info(
                    "dms_excalidraw: skipping upstream entry without id/name: %r",
                    entry,
                )
                counters["skipped"] += 1
                continue

            seen.add(upstream_id)

            # `source` and `preview` are paths relative to `libraries/`.
            source = entry.get("source")
            preview = entry.get("preview")
            values = {
                "name": name,
                "description": entry.get("description") or False,
                "authors": self._authors_text(entry.get("authors")),
                "source_url": (UPSTREAM_RAW_BASE + "libraries/" + source)
                if source
                else False,
                "preview_url": (UPSTREAM_RAW_BASE + "libraries/" + preview)
                if preview
                else False,
                "upstream_id": upstream_id,
                "last_sync": now,
                # A library that reappears upstream is reactivated: it was
                # deactivated because it vanished, not because anyone decided
                # against it.
                "active": True,
            }

            existing = Library.search(
                [("upstream_id", "=", upstream_id)], limit=1
            )
            if existing:
                existing.write(values)
                counters["updated"] += 1
            else:
                Library.create(values)
                counters["created"] += 1

        # Libraries that vanished upstream are DEACTIVATED, never deleted: a
        # whiteboard may already use their shapes, and a deleted record would
        # make the picker throw on a drawing that still works.
        #
        # Only libraries that have been synced at least once are candidates.
        # A seeded library has `last_sync = False` and must survive a sync
        # that does not know about it.
        stale = Library.search(
            [
                ("upstream_id", "!=", False),
                ("upstream_id", "not in", list(seen)),
                ("last_sync", "!=", False),
                ("active", "=", True),
            ]
        )
        if stale:
            stale.write({"active": False})
            counters["deactivated"] = len(stale)

        _logger.info(
            "dms_excalidraw: library sync finished: %s created, %s updated, "
            "%s deactivated, %s skipped",
            counters["created"],
            counters["updated"],
            counters["deactivated"],
            counters["skipped"],
        )
        return counters

    @staticmethod
    def _authors_text(authors):
        """Flatten the upstream `authors` list into one searchable string.

        The index gives `[{"name": ..., "url": ...}]`. The model stores a
        Char so the list view can search it; the URLs are kept alongside the
        names because the spec requires the licence position to be
        discoverable ("Authors are visible").
        """
        if not authors:
            return False
        if isinstance(authors, str):
            return authors
        parts = []
        for author in authors:
            if isinstance(author, dict):
                name = (author.get("name") or "").strip()
                url = (author.get("url") or "").strip()
                if name and url:
                    parts.append("%s (%s)" % (name, url))
                elif name:
                    parts.append(name)
            elif author:
                parts.append(str(author))
        return ", ".join(parts) or False

    # ------------------------------------------------------------------
    # Button
    # ------------------------------------------------------------------

    @api.model
    def action_sync_now(self):
        """Run the sync from the catalogue list's "Sync now" button.

        Refuses when sync is disabled rather than silently doing nothing: a
        button that appears to work and does not is worse than one that
        explains why it will not.
        """
        if not self._sync_enabled():
            raise UserError(
                _(
                    "Upstream sync is disabled.\n\n"
                    "Enable 'Library sync' under Settings > Documents > "
                    "Excalidraw before syncing. The shipped catalogue works "
                    "without it."
                )
            )

        counters = self._sync_from_upstream()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Library sync finished"),
                "message": _(
                    "%(created)s new, %(updated)s updated, "
                    "%(deactivated)s deactivated, %(skipped)s skipped.",
                    **counters,
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
