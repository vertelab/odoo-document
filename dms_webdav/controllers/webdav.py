import base64
import logging
from urllib.parse import unquote, urlparse

from odoo import http
from odoo.http import request
from odoo.service import db

_logger = logging.getLogger(__name__)

AUTH_HEADER = 'Basic realm="Odoo DMS WebDAV", charset="UTF-8"'

WEBDAV_METHODS = [
    "GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS",
    "PROPFIND", "MKCOL", "MOVE", "COPY", "LOCK", "UNLOCK",
]


def _basic_auth():
    auth = request.httprequest.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return _unauthorized()
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        login, password = decoded.split(":", 1)
    except Exception:
        return _unauthorized()
    credential = {"type": "password", "login": login, "password": password}
    for db_name in db.exp_list():
        try:
            auth_info = request.session.authenticate(db_name, credential)
            if auth_info.get("uid"):
                return
        except Exception:
            continue
    return _unauthorized()


def _unauthorized():
    return request.make_response(
        "WebDAV: Authorization required",
        headers=[("WWW-Authenticate", AUTH_HEADER), ("Content-Type", "text/plain; charset=utf-8")],
        status=401,
    )


class DmsWebdavController(http.Controller):

    @http.route(
        "/.well-known/webdav/",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET", "PROPFIND", "OPTIONS"],
        strict_slashes=False,
    )
    def well_known_discovery(self):
        base_url = request.httprequest.url_root.rstrip("/")
        return request.redirect(f"{base_url}/webdav/", code=307)

    # Odoo 18 keeps only ONE route per endpoint method: ``route()`` does
    # ``routing['routes'] = [route]`` on a dict shared by every decorator
    # applied to the method, so stacking two @http.route silently discards
    # the first one. Verified on 18.0-20260701: the stacked version produced
    # a routing map containing only "/webdav/", and every sub-path 404:ed
    # before reaching the controller. Hence two methods, one route each.
    @http.route(
        "/webdav/",
        type="http",
        auth="public",
        csrf=False,
        save_session=False,
        strict_slashes=False,
        methods=WEBDAV_METHODS,
    )
    def webdav_root(self):
        return self._dispatch("")

    # NOTE: a single ``<path:...>`` segment does not match here on Odoo 18
    # (verified: /webdav/NagotX 404:ed while /webdav/ worked). Spell out the
    # depth explicitly instead of relying on path-converter fallthrough.
    @http.route(
        "/webdav/<string:seg1>",
        type="http",
        auth="public",
        csrf=False,
        save_session=False,
        strict_slashes=False,
        methods=WEBDAV_METHODS,
    )
    def webdav_depth1(self, seg1):
        return self._dispatch(seg1)

    @http.route(
        "/webdav/<string:seg1>/<path:resource_path>",
        type="http",
        auth="public",
        csrf=False,
        save_session=False,
        strict_slashes=False,
        methods=WEBDAV_METHODS,
    )
    def webdav_dispatch(self, seg1, resource_path):
        return self._dispatch(f"{seg1}/{resource_path}")

    def _dispatch(self, resource_path):
        method = request.httprequest.method
        _logger.info("[WebDAV] %s /webdav/%s", method, resource_path)

        if method == "OPTIONS":
            return self._options_response()

        auth_result = _basic_auth()
        if auth_result:
            return auth_result

        path = f"/{resource_path}" if resource_path else "/"

        if method == "PROPFIND":
            return self._propfind(path)
        elif method == "GET" or method == "HEAD":
            return self._get(path, head=(method == "HEAD"))
        elif method == "PUT":
            return self._put(path)
        elif method == "DELETE":
            return self._delete(path)
        elif method == "MKCOL":
            return self._mkcol(path)
        elif method == "MOVE":
            return self._move(path)
        elif method == "COPY":
            return self._copy(path)
        elif method == "LOCK":
            return self._lock(path)
        elif method == "UNLOCK":
            return self._unlock(path)
        else:
            return request.make_response("Method not allowed", status=405)

    def _options_response(self):
        return request.make_response(
            "",
            headers=[
                ("DAV", "1, 2"),
                ("Allow", "OPTIONS, GET, HEAD, PROPFIND, PUT, DELETE, MKCOL, MOVE, COPY, LOCK, UNLOCK"),
                ("Content-Length", "0"),
            ],
        )

    def _href(self, path, is_collection=False):
        """Build the <d:href> for a resource.

        RFC 4918 allows either an absolute URI or an absolute path. We emit
        the *path* form ("/webdav/DavTest/"), which is what davfs2, rclone
        and Windows Explorer all expect: with an absolute URI davfs2 parses
        the entry but then discards it when matching it against the
        requested collection, and FUSE_READDIR ends in EINVAL.
        """
        href = f"/webdav{path}"
        # Collections must end with a slash, otherwise clients build the
        # wrong child URLs.
        if is_collection and not href.endswith("/"):
            href += "/"
        return href

    def _prop_xml(self, record, record_type, path):
        if record_type == "collection":
            return (
                '<d:prop>'
                '<d:displayname>DMS Root</d:displayname>'
                '<d:resourcetype><d:collection/></d:resourcetype>'
                '<d:getcontenttype>httpd/unix-directory</d:getcontenttype>'
                '</d:prop>'
            )
        parts = ['<d:prop>']
        if record_type == "directory":
            parts.append('<d:displayname>{}</d:displayname>'.format(record.name))
            parts.append('<d:resourcetype><d:collection/></d:resourcetype>')
            parts.append('<d:getcontenttype>httpd/unix-directory</d:getcontenttype>')
        elif record_type == "file":
            parts.append('<d:displayname>{}</d:displayname>'.format(record.name))
            parts.append('<d:resourcetype/>')
            parts.append('<d:getcontenttype>{}</d:getcontenttype>'.format(
                record.mimetype or "application/octet-stream"))
            parts.append('<d:getcontentlength>{}</d:getcontentlength>'.format(int(record.size or 0)))
        elif record_type == "storage":
            parts.append('<d:displayname>{}</d:displayname>'.format(record.name))
            parts.append('<d:resourcetype><d:collection/></d:resourcetype>')
            parts.append('<d:getcontenttype>httpd/unix-directory</d:getcontenttype>')
        parts.append('</d:prop>')
        return '\n'.join(parts)

    def _propfind_response(self, path, record_type, record):
        href = self._href(path, is_collection=record_type in ("collection", "storage", "directory"))
        prop_xml = self._prop_xml(record, record_type, path)
        return (
            '<d:response>'
            f'<d:href>{href}</d:href>'
            '<d:propstat>'
            f'{prop_xml}'
            '<d:status>HTTP/1.1 200 OK</d:status>'
            '</d:propstat>'
            '</d:response>'
        )

    @staticmethod
    def _overwrite_allowed():
        """RFC 4918 10.6: ``Overwrite`` defaults to ``T``, ``F`` means fail.

        If a destination exists and Overwrite is F the server must answer 412
        and leave both resources alone. With T (the default) it must replace
        the destination -- clients such as rclone rename by MOVE onto an
        existing name.
        """
        return (
            request.httprequest.headers.get("Overwrite", "T").strip().upper()
            != "F"
        )

    def _replace_destination(self, dest_record, dest_type):
        """Remove an existing destination before MOVE/COPY writes over it."""
        if dest_type == "directory" and (
            dest_record.child_directory_ids or dest_record.file_ids
        ):
            # RFC 4918 9.8.4/9.9.4: a non-empty collection can only be
            # replaced by deleting it first, which we do not do implicitly.
            return request.make_response(
                "Conflict: destination collection is not empty", status=409
            )
        dest_record.sudo().unlink()
        return None

    def _resolve(self, resolver, path):
        """Resolve a WebDAV path, tolerating a missing leading slash.

        Werkzeug strips the leading slash from ``<path:...>`` matches, so
        ``/webdav/WebdavTest`` arrives as ``WebdavTest``. ``resolve()``
        expects ``/WebdavTest``.
        """
        if not path.startswith("/"):
            path = "/" + path
        # sudo: resolve() searches dms.directory, which is filtered by the
        # ir.rule on the computed `permission_read`. Without sudo a path the
        # user cannot *see* resolves to None and the request 404s even
        # though the resource exists. Measured for uid 2:
        #     resolve("/DavTest/Docs")         -> (None, None)
        #     sudo().resolve("/DavTest/Docs")  -> ("Docs", "directory")
        # Access is enforced afterwards via _filtered_access() in _propfind().
        return resolver.sudo().resolve(path)

    @staticmethod
    def _destination_path(destination):
        """Turn a Destination header into a WebDAV path, decoded.

        ``urlparse().path`` does **not** decode percent-encoding, so RFC 4918
        clients that send ``Destination: https://host/webdav/Documents%20Storage/x``
        used to reach ``resolve("/Documents%20Storage/x")``, which never
        matches a real name. The parent was then "not found" and MOVE/COPY
        returned 409 for every destination below a name containing a space.
        Unquoting once makes both the encoded and the raw form work.

        The ``/webdav`` prefix is stripped after decoding, because a leading
        component cannot itself contain an encoded slash. Some clients send
        the bare path (``/Documents Storage/x``) instead of the full URL;
        stripping the first component unconditionally would then eat the
        storage name, so the prefix is only removed when it is really there.
        """
        dest_path = unquote(urlparse(destination).path)
        parts = dest_path.strip("/").split("/")
        if parts and parts[0] == "webdav":
            parts = parts[1:]
        if not parts or not parts[-1]:
            return None, request.make_response(
                "Bad Request: Destination has no resource path", status=400
            )
        return "/" + "/".join(parts), None

    def _propfind_children(self, parent_path, record, resolver, depth):
        results = []
        children = []

        # Two separate traps here, both verified on 18.0-20260701:
        #
        # 1. The One2many fields (root_directory_ids, child_directory_ids,
        #    file_ids) resolve and cache their ids before sudo() applies, so
        #    they come back silently empty for users the rules filter out.
        #    Hence search() in the resolver.
        # 2. Even search() is filtered by the ir.rule on the computed
        #    `permission_read`. Measured for uid 2 (admin):
        #        search()         -> []
        #        sudo().search()  -> [3]
        #    So the resolver must run with sudo(); access is then enforced
        #    per record below via _filtered_access().
        resolver = resolver.sudo()
        if record._name == "dms.storage":
            children = resolver.list_storage(record)
        elif record._name == "dms.directory":
            children = resolver.list_directory(record)
        else:
            return results

        for child_rec, child_type in children:
            if not child_rec.with_user(request.env.user)._filtered_access("read"):
                continue
            child_path = f"{parent_path.rstrip('/')}/{child_rec.name}"
            results.append(self._propfind_response(child_path, child_type, child_rec))
            if depth == "infinity" and child_type == "directory":
                results.extend(self._propfind_children(child_path, child_rec, resolver, depth))
        return results

    def _propfind(self, path):
        depth = request.httprequest.headers.get("Depth", "0")
        resolver = request.env["dms.webdav.path"]

        record, record_type = self._resolve(resolver, path)

        responses = []
        if record is None and path == "/":
            responses.append(self._propfind_response("/", "collection", None))
            if depth in ("1", "infinity"):
                for storage in resolver.sudo().list_storages():
                    storage_path = f"/{storage.name}"
                    responses.append(self._propfind_response(storage_path, "storage", storage))
                    if depth == "infinity":
                        responses.extend(self._propfind_children(storage_path, storage, resolver, depth))
        elif record is not None:
            if not record.with_user(request.env.user)._filtered_access("read"):
                return request.make_response("Not Found", status=404)
            responses.append(self._propfind_response(path, record_type, record))
            if depth in ("1", "infinity"):
                responses.extend(self._propfind_children(path, record, resolver, depth))
        else:
            return request.make_response("Not Found", status=404)

        xml = '<?xml version="1.0" encoding="utf-8"?>\n'
        xml += '<d:multistatus xmlns:d="DAV:">\n'
        xml += '\n'.join(responses)
        xml += '\n</d:multistatus>'
        # RFC 4918 §9.1: a PROPFIND response carrying a DAV:multistatus body
        # MUST use 207 Multi-Status. Returning 200 made strict clients such as
        # gvfs (GNOME Files / Nautilus) reject the collection, so davs:// mounts
        # failed even though the body was valid. Lenient clients (curl, rclone,
        # davfs2) parse the body regardless and were unaffected.
        return request.make_response(
            xml,
            status=207,
            headers=[("Content-Type", "application/xml; charset=utf-8")],
        )

    @staticmethod
    def _parse_range(range_header, total):
        """Parse a single ``Range: bytes=...`` header.

        Returns ``(start, end)`` as inclusive byte offsets, ``None`` when the
        header is absent or malformed in a way that must be ignored (RFC 9110
        lets a server serve the whole entity in that case), or the string
        ``"unsatisfiable"`` when the range lies outside the entity and the
        caller must answer 416.

        Only a single range is supported. A multi-range request is answered
        with the full entity, which the RFC permits.
        """
        if not range_header:
            return None
        value = range_header.strip()
        if not value.lower().startswith("bytes="):
            return None
        spec = value[6:].strip()
        if "," in spec or "-" not in spec:
            return None
        first, _, last = spec.partition("-")
        first, last = first.strip(), last.strip()
        if not first:
            # Suffix range: ``bytes=-500`` means the final 500 bytes.
            if not last.isdigit():
                return None
            length = int(last)
            if length == 0 or total == 0:
                return "unsatisfiable"
            return (max(total - length, 0), total - 1)
        if not first.isdigit():
            return None
        start = int(first)
        if last:
            if not last.isdigit():
                return None
            end = int(last)
            if end < start:
                return None
        else:
            end = total - 1
        if total == 0 or start >= total:
            return "unsatisfiable"
        return (start, min(end, total - 1))

    def _get(self, path, head=False):
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is None:
            return request.make_response("Not Found", status=404)

        if record_type in ("storage", "directory"):
            return request.make_response("Method not allowed on collection", status=405)

        if not record.with_user(request.env.user)._filtered_access("read"):
            return request.make_response(
                "Forbidden: no read access to this resource", status=403)
        content = record.sudo().content
        if not content:
            return request.make_response("", status=204)

        last_modified = record.write_date
        last_modified_str = last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT") if last_modified else ""
        etag = '"{}"'.format(record.checksum or "")
        mimetype = record.mimetype or "application/octet-stream"

        if head:
            # ``request.make_response("")`` lets werkzeug recompute
            # Content-Length to 0, which broke every client that asks how
            # large a file is. Serve HEAD through the same path as GET but
            # with an empty body and the entity length preserved.
            response = request.make_response(
                "",
                headers=[
                    ("Content-Type", mimetype),
                    ("Accept-Ranges", "bytes"),
                    ("ETag", etag),
                    ("Last-Modified", last_modified_str),
                ],
            )
            response.headers["Content-Length"] = str(int(record.size or 0))
            return response

        body = base64.b64decode(content)
        total = len(body)

        headers = [
            ("Content-Type", mimetype),
            ("Content-Length", str(total)),
            ("Accept-Ranges", "bytes"),
            ("ETag", etag),
            ("Last-Modified", last_modified_str),
        ]

        range_header = request.httprequest.headers.get("Range")
        # ``If-Range`` lets a client keep a partial download across a change:
        # honour the range only while the validator still matches.
        if_range = request.httprequest.headers.get("If-Range")
        if range_header and if_range and if_range.strip() != etag:
            range_header = None

        parsed = self._parse_range(range_header, total)
        if parsed == "unsatisfiable":
            return request.make_response(
                "",
                status=416,
                headers=[
                    ("Content-Range", "bytes */{}".format(total)),
                    ("Content-Length", "0"),
                    ("Accept-Ranges", "bytes"),
                    ("ETag", etag),
                ],
            )
        if parsed:
            start, end = parsed
            chunk = body[start:end + 1]
            return request.make_response(
                chunk,
                status=206,
                headers=[
                    ("Content-Type", mimetype),
                    ("Content-Length", str(len(chunk))),
                    ("Content-Range", "bytes {}-{}/{}".format(start, end, total)),
                    ("Accept-Ranges", "bytes"),
                    ("ETag", etag),
                    ("Last-Modified", last_modified_str),
                ],
            )

        return request.make_response(body, headers=headers)

    @staticmethod
    def _request_body():
        """Return the raw request body as bytes, whatever the Content-Type.

        Odoo's ``Dispatcher.dispatch()`` builds ``request.params`` from
        ``request.get_http_params()``, which merges ``args``, ``form`` and
        ``files``. Touching ``.form`` runs Werkzeug's form parser for any
        request that carries a ``Content-Type``
        (``want_form_data_parsed`` is true whenever ``CONTENT_TYPE`` is set),
        and that parser *consumes the stream*: the body ends up in
        ``request.params`` instead of on ``httprequest`` and the endpoint's
        signature only accepts route arguments, so the payload is logged as
        ``called ignoring args`` and dropped.

        ``curl --data-binary`` sends ``application/x-www-form-urlencoded`` by
        default, so a plain PUT looked successful (201/200) while writing
        zero bytes -- this silently emptied a live file.

        Reading the body here always yields the bytes, but the positional-arg
        capture that drops them has to be handled too, hence
        ``models.ir_http_dispatch.webserver_dispatch_keeps_body``.
        """
        return request.httprequest.get_data(cache=True)

    @staticmethod
    def _reject_form_urlencoded(body):
        """Return a 400 when a non-empty body arrived unparsed as a form.

        Belt and braces: if ``webserver_dispatch_keeps_body`` is missing (an
        Odoo patch that renames the dispatcher again) and the body was eaten,
        ``body`` is empty while ``Content-Length`` says otherwise. Writing
        nothing over a file is the one thing this route must never do
        silently, so the caller gets a 400 instead of a 0-byte overwrite.
        """
        declared = request.httprequest.content_length
        if declared and not body:
            _logger.warning(
                "[WebDAV] body missing: %s bytes declared, 0 read "
                "(Content-Type %r) -- refusing to write empty content",
                declared,
                request.httprequest.headers.get("Content-Type"),
            )
            return request.make_response(
                "Bad Request: request body was consumed by form parsing; "
                "send Content-Type: application/octet-stream",
                status=400,
            )
        return None

    @staticmethod
    def _parse_content_range(header):
        """Parse a ``Content-Range: bytes start-end/total`` header.

        Returns ``(start, end, total)`` with inclusive byte offsets, ``None``
        when the header is absent or malformed, or the string ``"status"`` for
        the ``bytes */total`` form a client uses to ask how much was received.

        Unlike ``_parse_range`` (a GET concern) a malformed header here is an
        error, not something to ignore: silently treating a chunk as a whole
        file would truncate the upload.
        """
        if not header:
            return None
        value = header.strip()
        if not value.lower().startswith("bytes "):
            return None
        spec = value[6:].strip()
        span, _, total = spec.partition("/")
        span, total = span.strip(), total.strip()
        if not total.isdigit():
            return None
        total = int(total)
        if span == "*":
            return "status"
        if "-" not in span:
            return None
        first, _, last = span.partition("-")
        first, last = first.strip(), last.strip()
        if not first.isdigit() or not last.isdigit():
            return None
        start, end = int(first), int(last)
        if end < start or end >= total:
            return None
        return (start, end, total)

    def _chunk_dir(self):
        """Directory holding in-progress chunked uploads."""
        import os
        import tempfile

        path = os.path.join(tempfile.gettempdir(), "dms_webdav_chunks")
        os.makedirs(path, exist_ok=True)
        return path

    def _chunk_path(self, path):
        """Per-user, per-target path for an in-progress chunked upload."""
        import hashlib
        import os

        key = "{}:{}".format(request.env.user.id, path)
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return os.path.join(self._chunk_dir(), digest)

    def _upload_id_path(self, path):
        """Sidecar recording the target path and the total size received."""
        return self._chunk_path(path) + ".meta"

    def _append_chunk(self, path, start, data, total):
        """Append one chunk, refusing anything that would corrupt the result.

        Returns True when the upload is complete, False when more chunks are
        needed. Raises ``ValueError`` on an out-of-order or oversized chunk so
        the caller can answer 409 instead of writing a broken file.
        """
        import json
        import os

        chunk_path = self._chunk_path(path)
        meta_path = self._upload_id_path(path)
        received = 0
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
            if meta.get("total") != total:
                raise ValueError("total size changed mid-upload")
            received = meta.get("received", 0)
        if start != received:
            raise ValueError(
                "expected chunk at offset {}, got {}".format(received, start)
            )
        with open(chunk_path, "ab") as handle:
            handle.write(data)
        received += len(data)
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump({"total": total, "received": received}, handle)
        return received >= total

    def _assemble_chunks(self, path):
        """Return the assembled bytes and remove the temporary files."""
        import os

        chunk_path = self._chunk_path(path)
        with open(chunk_path, "rb") as handle:
            data = handle.read()
        self._cleanup_chunks(path)
        return data

    def _cleanup_chunks(self, path):
        """Remove the temporary files of an upload, complete or abandoned."""
        import os

        for candidate in (self._chunk_path(path), self._upload_id_path(path)):
            try:
                os.unlink(candidate)
            except FileNotFoundError:
                pass

    def _put(self, path):
        content_range = request.httprequest.headers.get("Content-Range")

        # RFC 7231: a chunked upload is buffered and written once, when the last
        # chunk arrives. Writing per chunk would leave a half file behind on a
        # crash and would create one version per chunk.
        if content_range:
            parsed = self._parse_content_range(content_range)
            if parsed is None:
                return request.make_response(
                    "Bad Request: malformed Content-Range", status=400
                )
            if parsed == "status":
                return request.make_response(
                    "Bad Request: status query is not a chunk", status=400
                )
            start, end, total = parsed
            data = self._request_body()
            rejected = self._reject_form_urlencoded(data)
            if rejected:
                return rejected
            if len(data) != end - start + 1:
                return request.make_response(
                    "Bad Request: chunk length does not match Content-Range",
                    status=400,
                )
            try:
                complete = self._append_chunk(path, start, data, total)
            except ValueError as error:
                self._cleanup_chunks(path)
                return request.make_response(
                    "Conflict: {}".format(error), status=409
                )
            if not complete:
                return request.make_response(
                    "",
                    headers=[
                        ("Range", "bytes=0-{}".format(end)),
                        ("Content-Length", "0"),
                    ],
                    status=308,
                )
            data = self._assemble_chunks(path)

        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if not content_range:
            data = self._request_body()
            rejected = self._reject_form_urlencoded(data)
            if rejected:
                return rejected
        if record is not None and record_type == "file":
            if not record.with_user(request.env.user)._filtered_access("write"):
                return request.make_response(
                    "Forbidden: no write access to this resource", status=403)
            # An empty body over an existing, non-empty file is almost always a
            # client bug -- a consumed stream, a failed read, a truncated
            # upload -- and the result is indistinguishable from data loss.
            # This is how a 397923-byte SVG became 0 bytes next to a 200 OK.
            # Truncating to zero is possible on purpose by deleting the file.
            if not data and record.size:
                _logger.error(
                    "[WebDAV] refusing to empty %s (%s bytes) -- PUT carried "
                    "no content (Content-Length %s, Content-Type %r)",
                    path,
                    record.size,
                    request.httprequest.content_length,
                    request.httprequest.headers.get("Content-Type"),
                )
                return request.make_response(
                    "Conflict: refusing to overwrite a non-empty file with an "
                    "empty body",
                    status=409,
                )
            record.sudo().with_context(dms_source="webdav").write(
                {"content": base64.b64encode(data)}
            )
            return request.make_response(
                "",
                headers=[("ETag", '"{}"'.format(record.checksum or ""))],
            )

        path = path.strip("/")
        *dir_parts, file_name = path.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = self._resolve(resolver, dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            return request.make_response("Bad Request: parent not found", status=409)

        if parent_type == "storage":
            return request.make_response("Bad Request: cannot create file directly under storage", status=409)

        if not parent_record.with_user(request.env.user)._filtered_access("create"):
            return request.make_response(
                "Forbidden: no create access in this directory", status=403)

        new_file = (
            request.env["dms.file"]
            .sudo()
            .with_context(dms_source="webdav")
            .create(
                {
                    "name": file_name,
                    "directory_id": parent_record.id,
                    "content": base64.b64encode(data),
                }
            )
        )
        return request.make_response(
            "",
            headers=[("ETag", '"{}"'.format(new_file.checksum or ""))],
            status=201,
        )

    def _delete(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is None:
            return request.make_response("Not Found", status=404)

        if not record.with_user(request.env.user)._filtered_access("unlink"):
            return request.make_response(
                "Forbidden: no delete access to this resource", status=403)

        if record_type == "directory":
            if record.child_directory_ids or record.file_ids:
                return request.make_response("Conflict: directory not empty", status=409)

        record.sudo().unlink()
        return request.make_response("", status=204)

    def _mkcol(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is not None:
            return request.make_response("Conflict: resource already exists", status=409)

        path = path.strip("/")
        *dir_parts, dir_name = path.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = self._resolve(resolver, dir_path)

        if parent_record is None:
            return request.make_response("Conflict: parent not found", status=409)
        if parent_type not in ("storage", "directory"):
            return request.make_response("Bad Request", status=405)

        if parent_type == "storage":
            if not parent_record.with_user(request.env.user)._filtered_access("create"):
                return request.make_response("Forbidden", status=403)
            # sudo: the ir.rule on dms.directory checks the *computed*
            # permission_create, which is False for a record that does not
            # exist yet — so a plain create() is always denied. The access
            # check is done above via _filtered_access("create").
            request.env["dms.directory"].sudo().create({
                "name": dir_name,
                "storage_id": parent_record.id,
                "is_root_directory": True,
            })
        else:
            if not parent_record.with_user(request.env.user)._filtered_access("create"):
                return request.make_response("Forbidden", status=403)
            request.env["dms.directory"].sudo().create({
                "name": dir_name,
                "parent_id": parent_record.id,
            })

        return request.make_response("", status=201)

    def _move(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is None:
            return request.make_response("Not Found", status=404)

        destination = request.httprequest.headers.get("Destination", "")
        if not destination:
            return request.make_response("Bad Request: no Destination header", status=400)

        dest_path, bad = self._destination_path(destination)
        if bad:
            return bad

        dest_record, dest_type = self._resolve(resolver, dest_path)

        if not record.with_user(request.env.user)._filtered_access("write"):
            return request.make_response("Forbidden", status=403)
        if dest_record is not None:
            if dest_record.id == record.id:
                # RFC 4918 9.9.2: moving a resource onto itself is a no-op.
                return request.make_response("", status=204)
            if not self._overwrite_allowed():
                return request.make_response(
                    "Precondition Failed: destination exists and Overwrite is F",
                    status=412,
                )
            rejected = self._replace_destination(dest_record, dest_type)
            if rejected:
                return rejected

        dest_path_clean = dest_path.strip("/")
        *dest_dir_parts, dest_name = dest_path_clean.split("/")
        dest_dir_path = "/" + "/".join(dest_dir_parts) if dest_dir_parts else "/"
        parent_record, parent_type = self._resolve(resolver, dest_dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            return request.make_response("Conflict: destination parent not found", status=409)

        if record_type in ("file", "directory"):
            # sudo: the ir.rule on dms.file checks the computed
            # permission_write, which is not evaluated for the target user
            # inside this transaction. Access was checked above.
            record.sudo().write({"name": dest_name})
            if record_type == "file" and parent_type == "directory":
                record.sudo().write({"directory_id": parent_record.id})

        return request.make_response("", status=204)

    def _copy(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is None:
            return request.make_response("Not Found", status=404)

        destination = request.httprequest.headers.get("Destination", "")
        if not destination:
            return request.make_response("Bad Request: no Destination header", status=400)

        dest_path, bad = self._destination_path(destination)
        if bad:
            return bad

        dest_record, dest_type = self._resolve(resolver, dest_path)
        if dest_record is not None:
            if not self._overwrite_allowed():
                return request.make_response(
                    "Precondition Failed: destination exists and Overwrite is F",
                    status=412,
                )
            rejected = self._replace_destination(dest_record, dest_type)
            if rejected:
                return rejected

        dest_path_clean = dest_path.strip("/")
        *dest_dir_parts, dest_name = dest_path_clean.split("/")
        dest_dir_path = "/" + "/".join(dest_dir_parts) if dest_dir_parts else "/"
        parent_record, parent_type = self._resolve(resolver, dest_dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            return request.make_response("Conflict: destination parent not found", status=409)

        if not record.with_user(request.env.user)._filtered_access("read"):
            return request.make_response("Forbidden", status=403)

        if record_type == "file":
            if not parent_record.with_user(request.env.user)._filtered_access("create"):
                return request.make_response("Forbidden", status=403)
            request.env["dms.file"].sudo().create({
                "name": dest_name,
                "directory_id": parent_record.id,
                "content": record.sudo().content,
            })
        elif record_type == "directory":
            if not parent_record.with_user(request.env.user)._filtered_access("create"):
                return request.make_response("Forbidden", status=403)
            new_dir = request.env["dms.directory"].sudo().create({
                "name": dest_name,
                "parent_id": parent_record.id if parent_type == "directory" else False,
                "storage_id": parent_record.id if parent_type == "storage" else parent_record.storage_id.id,
                "is_root_directory": parent_type == "storage",
            })
            self._copy_directory_contents(record, new_dir)

        return request.make_response("", status=204)

    def _copy_directory_contents(self, source_dir, target_dir):
        # search() + sudo: One2many fields are filtered by the ir.rule on
        # permission_read and come back empty, and create() is denied before
        # permission_create can be computed for a new record.
        Directory = request.env["dms.directory"].sudo()
        DmsFile = request.env["dms.file"].sudo()
        for child in Directory.search([("parent_id", "=", source_dir.id)]):
            new_child = Directory.create({
                "name": child.name,
                "parent_id": target_dir.id,
            })
            self._copy_directory_contents(child, new_child)
        for file_rec in DmsFile.search([("directory_id", "=", source_dir.id)]):
            DmsFile.create({
                "name": file_rec.name,
                "directory_id": target_dir.id,
                "content": file_rec.content,
            })

    def _lock(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is None:
            return request.make_response("Not Found", status=404)

        if record_type in ("storage", "directory"):
            return request.make_response(
                self._lock_xml("shared", path),
                headers=[("Content-Type", "application/xml; charset=utf-8")],
            )

        if not record.with_user(request.env.user)._filtered_access("write"):
            return request.make_response("Forbidden", status=403)
        record.lock()

        return request.make_response(
            self._lock_xml("exclusive", path),
            headers=[("Content-Type", "application/xml; charset=utf-8")],
        )

    def _lock_xml(self, lock_type, path):
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:prop xmlns:d="DAV:">'
            '<d:lockdiscovery>'
            '<d:activelock>'
            '<d:locktype><d:write/></d:locktype>'
            f'<d:lockscope><d:{lock_type}/></d:lockscope>'
            '<d:depth>infinity</d:depth>'
            '<d:locktoken><d:href>opaquelocktoken:{}</d:href></d:locktoken>'
            '</d:activelock>'
            '</d:lockdiscovery>'
            '</d:prop>'
        ).format(request.env.user.id)

    def _unlock(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is None:
            return request.make_response("Not Found", status=404)

        if record_type == "file":
            if not record.with_user(request.env.user)._filtered_access("write"):
                return request.make_response("Forbidden", status=403)
            record.unlock()

        return request.make_response("", status=204)
