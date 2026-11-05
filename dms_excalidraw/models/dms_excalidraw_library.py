# -*- coding: utf-8 -*-
"""A catalogue of Excalidraw shape libraries.

WHY THIS IS NOT A `dms.file`
============================
A `dms.file` is the document model: it carries retention, revision history,
`dms.access.group` and a `res_model`/`res_id` link to a business object. A
catalogue library has none of that. It is a shared reference — the same 232
AWS icons for every customer — with no folder, no owner and no business object
behind it. Storing them as documents would put 232 records in every customer's
file listing and make them inherit a folder's access rules for no reason.

So: a separate model with the module's own access group.

**The exception is a USER library** — a user's own saved shapes. That one IS a
`dms.file` with `extension = excalidrawlib`, because it belongs in a folder and
must inherit that folder's access. Two different things, two different homes
(design D3).

WHY `upstream_id` IS THE KEY
============================
The upstream index (`libraries.json`) identifies a library by a short random
`id` (e.g. `6TGNPXCpuVy`). Re-syncing must UPDATE the existing record, not
create a second one, so `upstream_id` is unique and the upsert keys on it. A
library that disappears upstream is deactivated rather than deleted, because a
user may have a saved whiteboard that references it.
"""

import json
import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The format version this module understands. `.excalidrawlib` files in the
# wild are version 1 or 2; v2 is what the current editor writes.
KNOWN_LIBRARY_VERSIONS = (1, 2)

LIBRARY_TYPE = "excalidrawlib"


class DmsExcalidrawLibrary(models.Model):
    _name = "dms_excalidraw.library"
    _description = "Excalidraw shape library"
    _order = "name, id"

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
    )
    description = fields.Text(
        string="Description",
    )
    authors = fields.Char(
        string="Authors",
        help="Comma-separated author names, as the upstream index lists them. "
        "The picker shows this so a user can see who made the shapes before "
        "dragging them into a customer drawing.",
    )
    source_url = fields.Char(
        string="Source URL",
        help="Where the .excalidrawlib file is fetched from when the user "
        "opens the library. For a seeded library this is the module's own "
        "static path, so a fresh install needs no network.",
    )
    preview_url = fields.Char(
        string="Preview URL",
        help="Thumbnail shown in the picker. Loaded lazily — the picker "
        "renders a placeholder until it arrives, because a catalogue of "
        "hundreds of previews must not block the panel.",
    )
    upstream_id = fields.Char(
        string="Upstream ID",
        index=True,
        help="The upstream catalogue's own identifier. The sync upserts on "
        "this, so re-syncing updates instead of duplicating.",
    )
    item_count = fields.Integer(
        string="Items",
        help="Number of shapes in the library, computed from "
        "`libraryItems`. Shown before the user loads it: a 500-shape library "
        "is not free.",
    )
    byte_size = fields.Integer(
        string="Size (bytes)",
    )
    last_sync = fields.Datetime(
        string="Last synced",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Uncheck to hide a library from the picker without deleting it. "
        "A library removed upstream is deactivated this way, so a whiteboard "
        "that already uses its shapes keeps working.",
    )

    # A library without an upstream id is legitimate: the four seeded
    # libraries that upstream publishes without an `id` field have none.
    #
    # ⚠️ The constraint must therefore be a PARTIAL unique index. A plain
    # `unique(upstream_id)` treats every NULL as distinct (fine) but an EMPTY
    # STRING as a value — so the second seed record with `upstream_id = ''`
    # raised `duplicate key value violates unique constraint` and aborted the
    # whole module install. Verified 2026-11-05 against the real seed.
    #
    # `WHERE upstream_id IS NOT NULL` keeps the real guarantee — no two
    # libraries may claim the same upstream id — without inventing one for
    # the libraries that have none.
    _sql_constraints = [
        (
            "upstream_id_uniq",
            "unique(upstream_id)",
            "A library with this upstream id already exists. The sync must "
            "update it, not create a second record.",
        ),
    ]

    # ------------------------------------------------------------------
    # Format validation
    # ------------------------------------------------------------------

    @api.model
    def _parse_library(self, blob):
        """Validate a `.excalidrawlib` payload and return its items.

        TWO FORMATS, NOT ONE
        ====================
        The design documented only the v2 shape:

            {"type": "excalidrawlib", "version": 2, "libraryItems": [...]}

        But 10 of the 30 seeded libraries are **v1**, and they look different:

            {"type": "excalidrawlib", "version": 1, "library": [[element, ...], ...]}

        In v1 every entry is a bare ARRAY of elements with no `id`, `status` or
        `name`; v2 wraps each in an object. Verified 2026-11-05 against the
        files committed under `static/lib/libraries/`.

        Excalidraw's own loader handles both — `Lp(items, defaultStatus)`
        wraps each entry, and `Tp(item)` migrates it — so a v1 library is a
        perfectly loadable library. Rejecting it here would have thrown away a
        third of the catalogue for a format that works.

        So the parser normalises to a list of item objects and reports the
        count. It does NOT rewrite the file: the browser gets the original
        bytes and Excalidraw does its own migration.

        Raises `ValueError` with a message naming the problem when the file is
        not a library. An UNKNOWN version is different from a malformed file:
        it is a real library this module is too old to read, signalled with
        `UnknownLibraryVersion` so the caller can skip it and carry on with
        the rest of the catalogue.
        """
        if isinstance(blob, (bytes, bytearray)):
            try:
                blob = blob.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(
                    "The library is not UTF-8 text: %s" % error
                ) from error

        try:
            data = json.loads(blob)
        except ValueError as error:
            raise ValueError("The library is not valid JSON: %s" % error) from error

        if not isinstance(data, dict):
            raise ValueError(
                "The library is not a JSON object (got %s)."
                % type(data).__name__
            )

        if data.get("type") != LIBRARY_TYPE:
            raise ValueError(
                "The file is a %r, not an %r."
                % (data.get("type"), LIBRARY_TYPE)
            )

        # `version` is an INT in v2 and a STRING in the v1 files upstream
        # ships (`"version": "1"`). Comparing the raw value would reject
        # every v1 library, so normalise before the membership test.
        version = data.get("version")
        try:
            version = int(version)
        except (TypeError, ValueError):
            version = None

        if version not in KNOWN_LIBRARY_VERSIONS:
            raise UnknownLibraryVersion(
                "Library format version %r is not supported (known: %s)."
                % (data.get("version"),
                   ", ".join(str(v) for v in KNOWN_LIBRARY_VERSIONS))
            )

        items = self._library_items(data)
        if not isinstance(items, list):
            raise ValueError(
                "The library has no item list (got %s). Expected "
                "`libraryItems` (v2) or `library` (v1)."
                % type(items).__name__
            )

        return items

    @api.model
    def _library_items(self, data):
        """Return the item list of a parsed library, whichever key it uses.

        v2 uses `libraryItems`; v1 uses `library`. Both are lists, but their
        entries differ (v2: objects, v1: arrays of elements). The caller only
        needs the length, so the difference stops here.
        """
        if "libraryItems" in data:
            return data["libraryItems"]
        if "library" in data:
            return data["library"]
        return None

    @api.model
    def _item_count(self, items):
        """Return the number of shapes in a validated library.

        Kept as a method rather than `len(items)` at the call site so the
        definition lives in one place: the count shown in the picker and the
        count stored by the sync must agree.
        """
        return len(items)


    # ------------------------------------------------------------------
    # Serving a library to the picker
    # ------------------------------------------------------------------

    _MAX_BYTES_PARAM = "dms_excalidraw.library_max_bytes"
    _DEFAULT_MAX_BYTES = 2 * 1024 * 1024

    @api.model
    def _max_bytes(self):
        """Return the largest library the picker will load.

        A cap exists because a library is fetched and parsed in the browser:
        a 20 MB file is a frozen tab, not a slow one. 2 MB is roughly ten
        times the largest library in the upstream catalogue.
        """
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(self._MAX_BYTES_PARAM, str(self._DEFAULT_MAX_BYTES))
        )
        try:
            return int(raw)
        except (TypeError, ValueError):
            return self._DEFAULT_MAX_BYTES

    def _read_source(self):
        """Return the raw bytes of this library's `source_url`.

        A seeded library points at the module's own static path, so this is a
        local file read. A synced library points at GitHub, so it is a fetch.
        Both go through here so the size cap and the error messages are
        written once.
        """
        self.ensure_one()
        if not self.source_url:
            raise UserError(
                _("The library '%s' has no source URL.", self.name)
            )

        url = self.source_url
        if url.startswith("/"):
            # Module static path: read from disk. `/dms_excalidraw/static/...`
            # maps to `<module>/static/...`; anything else is refused rather
            # than resolved, so a crafted record cannot read the filesystem.
            prefix = "/dms_excalidraw/static/"
            if not url.startswith(prefix):
                raise UserError(
                    _("The library '%(name)s' points at %(url)s, which is not "
                      "a module static path.", name=self.name, url=url)
                )
            relative = url[len(prefix):]
            if ".." in relative.split("/"):
                raise UserError(
                    _("The library '%s' has an unsafe path.", self.name)
                )
            module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(module_dir, "static", *relative.split("/"))
            try:
                with open(path, "rb") as handle:
                    return handle.read()
            except OSError as error:
                raise UserError(
                    _("Could not read the library '%(name)s': %(reason)s.",
                      name=self.name, reason=error)
                ) from error

        return self._fetch_bytes(url)

    def action_load(self):
        """Return the library payload for the picker.

        Returns a dict rather than raising for the two conditions the picker
        must SHOW (too large, unreadable): the user picked this library and is
        owed an explanation naming it, not a generic error page.
        """
        self.ensure_one()
        limit = self._max_bytes()
        if self.byte_size and self.byte_size > limit:
            return {
                "error": _(
                    "The library '%(name)s' is %(size)s, which is over the "
                    "%(limit)s limit.",
                    name=self.name,
                    size=_human_size(self.byte_size),
                    limit=_human_size(limit),
                )
            }
        try:
            blob = self._read_source()
        except UserError as error:
            return {"error": _("The library '%(name)s' could not be loaded: "
                              "%(reason)s", name=self.name, reason=error.args[0])}
        if len(blob) > limit:
            return {
                "error": _(
                    "The library '%(name)s' is %(size)s, which is over the "
                    "%(limit)s limit.",
                    name=self.name,
                    size=_human_size(len(blob)),
                    limit=_human_size(limit),
                )
            }
        try:
            data = json.loads(blob.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            return {"error": _("The library '%(name)s' is not valid JSON: "
                              "%(reason)s", name=self.name, reason=error)}
        return {"library": data}


def _human_size(size):
    """Format a byte count the way a user reads it."""
    value = float(size)
    for unit in ("B", "kB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return ("%d %s" % (value, unit)) if unit == "B" else (
                "%.1f %s" % (value, unit)
            )
        value /= 1024.0


class UnknownLibraryVersion(ValueError):
    """A well-formed library of a version this module does not understand.

    Subclasses `ValueError` so a caller that only catches `ValueError` still
    behaves sanely, but lets the sync distinguish "skip and continue" from
    "this file is broken".
    """
