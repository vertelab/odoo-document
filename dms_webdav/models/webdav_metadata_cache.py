"""Request-scoped metadata cache for WebDAV PROPFIND.

WHY NOT A CROSS-REQUEST CACHE
=============================
The tempting design is a module-level dict keyed on record id. It is also the
design that breaks sync. `size`, `checksum` and `write_date` change when a
file is written, and `dms.file` has several write paths: the ORM, the WebDAV
PUT, and the `dms_excalidraw` save-back controller. A cache that outlives the
request serves an old etag — the client concludes it already has the current
content and stops downloading. Silently, and for as long as the cache lives.

Reusing Odoo's own field cache (`request.env.cache`) is not the answer either:
that is `odoo.api.Cache`, a slot-based structure with dirty tracking and ORM
invalidation. Writing arbitrary keys into it would either corrupt its
invariants or be wiped by the next `invalidate_all()`.

So the cache is scoped to ONE request. That is enough for the case that costs
time: `_propfind_children()` reads each record at least twice (once for the
batched permission check, once for the property block), and a Depth: infinity
walk revisits parents.

WHAT IS CACHED
==============
Only the fields PROPFIND reads: name, mimetype, size, checksum, write_date,
create_date. Nothing else.

WHAT IS NOT
===========
No `content`. A file's bytes must never be held in a shared structure, and
holding them for one request buys nothing — GET reads them once.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# The only fields a PROPFIND response reads, per model.
#
# ⚠️ PER MODEL, not one list. `dms.directory` has no `mimetype`, `size` or
# `checksum` — those are file-only fields. A single shared list raised
#
#     ValueError: Invalid field 'mimetype' on model 'dms.directory'
#
# on every PROPFIND against a collection. Verified 2026-11-05.
CACHED_FIELDS = {
    "dms.file": (
        "name",
        "mimetype",
        "size",
        "checksum",
        "write_date",
        "create_date",
        # `lockdiscovery` needs it. The PROPFIND property list is built from
        # this cache, so a field that is not cached here is simply absent --
        # `_prop_values` would see None and report every file as unlocked,
        # which is the bug this change exists to fix.
        "locked_by",
    ),
    "dms.directory": (
        "name",
        "write_date",
        "create_date",
    ),
    "dms.storage": (
        "name",
        "write_date",
        "create_date",
    ),
}

# What a caller may ask for. Missing keys fall back to this, so a model added
# later does not silently return None for every property.
DEFAULT_FIELDS = ("name", "write_date", "create_date")


# Every key a caller may read, so a dict from a directory still has the file
# keys (as None) and `_prop_values` does not need per-model branching.
_ALL_PROP_KEYS = tuple(
    sorted({key for fields in CACHED_FIELDS.values() for key in fields})
)


class DmsWebdavMetadataCache(models.AbstractModel):
    _name = "dms.webdav.metadata.cache"
    _description = "WebDAV PROPFIND metadata cache (request-scoped)"

    @api.model
    def get(self, records):
        """Return {(model, id): {field: value}} for the given records.

        Reads only what is missing, grouped per model so each gets one
        `read()` call. Records may mix models: a directory listing contains
        both `dms.directory` and `dms.file`.
        """
        cache = self._store()

        key = lambda record: (record._name, record.id)  # noqa: E731

        missing = {}
        for record in records:
            if key(record) not in cache:
                missing.setdefault(record._name, []).append(record.id)

        for model_name, ids in missing.items():
            fields = CACHED_FIELDS.get(model_name, DEFAULT_FIELDS)
            rows = self.env[model_name].browse(ids).read(list(fields))
            for row in rows:
                # Missing file-only keys default to None so callers can read
                # `props["checksum"]` without guarding every model.
                cache[(model_name, row["id"])] = {
                    key: row.get(key) for key in _ALL_PROP_KEYS
                }

        return {key(record): cache[key(record)] for record in records}

    @api.model
    def _store(self):
        """Return this request's dict, creating it on first use.

        An attribute on the `request` object is the right home: `request` is
        created per HTTP request and discarded when the response is sent, so
        the lifetime is exactly what a metadata cache needs — long enough to
        serve the repeated reads inside one PROPFIND, short enough that a
        stale validator can never outlive the request that produced it.
        """
        from odoo.http import request

        if not request:
            # Outside a request (tests, cron, a shell): no cache. The caller
            # still gets correct data, it is just read again.
            return {}
        store = getattr(request, "_dms_webdav_propfind_cache", None)
        if store is None:
            store = {}
            request._dms_webdav_propfind_cache = store
        return store
