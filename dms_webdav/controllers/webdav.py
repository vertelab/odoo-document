import base64
import logging
from urllib.parse import urlparse

from odoo import http
from odoo.http import request
from odoo.service import db

_logger = logging.getLogger(__name__)

AUTH_HEADER = 'Basic realm="Odoo DMS WebDAV", charset="UTF-8"'

# P1c: in-process thumbnail cache, keyed by (file id, checksum, width).
# Deliberately not an ir.attachment: a preview is derived data that must
# disappear when the file changes, and the checksum in the key gives exactly
# that for free. Cleared wholesale when it grows past the cap — a scroll
# through a large folder is the only workload that fills it.
_PREVIEW_CACHE = {}
_PREVIEW_CACHE_MAX = 512

# P1d: in-flight chunked uploads, keyed by (uid, destination path).
# A value is {"total": int, "chunks": {offset: bytes}, "received": int}.
# Kept in-process on purpose: a partial upload is worthless after a worker
# restart, and writing half a file to the database would be worse than
# asking the client to start over.
_UPLOAD_BUFFER = {}
_UPLOAD_BUFFER_MAX = 64

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


def _parse_content_range(content_range):
    """Parse ``Content-Range: bytes start-end/total`` into a 3-tuple.

    Returns ``None`` for anything malformed, including the ``*/total`` form
    (which is a query, not an upload). ``total`` must be known: a resumable
    upload without a declared size cannot be assembled.
    """
    if not content_range or not content_range.startswith("bytes"):
        return None
    spec = content_range[len("bytes"):].strip()
    if "/" not in spec:
        return None
    span, _, total_raw = spec.partition("/")
    if "-" not in span:
        return None
    first, _, last = span.partition("-")
    try:
        start = int(first.strip())
        end = int(last.strip())
        total = int(total_raw.strip())
    except ValueError:
        return None
    if start < 0 or end < start or total <= 0 or end >= total:
        return None
    return start, end, total


def _parse_range(range_header, total):
    """Parse an HTTP ``Range`` header into an inclusive ``(start, end)``.

    Supports the three forms RFC 7233 allows for a single range::

        bytes=0-1023      -> (0, 1023)
        bytes=1000000-    -> (1000000, total - 1)
        bytes=-500        -> (total - 500, total - 1)

    Returns ``None`` when the header is malformed or the range cannot be
    satisfied, so the caller can answer ``416`` with the real length. A
    multi-range request (``bytes=0-10,20-30``) is also rejected: answering
    ``multipart/byteranges`` is legal but no client we support needs it, and
    silently returning the first range would be a lie about the response.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None
    spec = range_header[len("bytes="):].strip()
    if "," in spec:
        return None
    if "-" not in spec:
        return None
    first, _, last = spec.partition("-")
    first, last = first.strip(), last.strip()
    try:
        if not first:
            # Suffix range: the last N bytes.
            if not last:
                return None
            suffix = int(last)
            if suffix <= 0:
                return None
            start = max(total - suffix, 0)
            end = total - 1
        else:
            start = int(first)
            end = int(last) if last else total - 1
    except ValueError:
        return None
    if start > end or start >= total:
        return None
    return start, min(end, total - 1)


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
        # RFC 4918 §9.1: a PROPFIND answer is 207 Multi-Status, not 200. Some
        # clients (notably the Android document providers) treat 200 as a
        # plain document and skip the XML body entirely.
        return request.make_response(
            xml,
            headers=[("Content-Type", "application/xml; charset=utf-8")],
            status=207,
        )

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

        payload = base64.b64decode(content)
        total = len(payload)
        etag = '"{}"'.format(record.checksum or "")

        # P1c: server-side thumbnail. A folder with 200 images shows no
        # previews in any WebDAV client without this: the client would have
        # to download every original in full to render a grid. ?preview=1
        # returns a scaled JPEG instead, and ?w= sets the target width.
        preview = request.httprequest.args.get("preview")
        if preview and preview not in ("0", "false", "no"):
            preview_response = self._preview_response(record, payload, etag)
            if preview_response is not None:
                return preview_response

        last_modified = record.write_date
        last_modified_str = last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT") if last_modified else ""
        headers = [
            ("Content-Type", record.mimetype or "application/octet-stream"),
            ("Content-Length", str(total)),
            ("ETag", etag),
            ("Last-Modified", last_modified_str),
            # P1a: advertise byte-range support on every GET/HEAD. Without
            # this Android clients (Voyager) treat the resource as a pipe of
            # unknown length and download it in full before showing it.
            ("Accept-Ranges", "bytes"),
        ]

        if head:
            # P1b: returning make_response("") lets werkzeug recompute
            # Content-Length to 0 because the body is empty, which broke
            # size display and progress bars in every client. Build the
            # response from the real payload and then drop the body while
            # keeping the header.
            response = request.make_response(payload, headers=headers)
            response.set_data(b"")
            response.headers["Content-Length"] = str(total)
            return response

        # P1a: honour Range so clients can seek and stream. Android needs a
        # seekable resource with a known length; without 206 it must download
        # the whole file before rendering an image or playing a video.
        range_header = request.httprequest.headers.get("Range")
        if_range = request.httprequest.headers.get("If-Range")
        if range_header and (not if_range or if_range.strip() == etag):
            byte_range = _parse_range(range_header, total)
            if byte_range is None:
                # Malformed or unsatisfiable range: 416 with the real length.
                return request.make_response(
                    "Range Not Satisfiable",
                    headers=[("Content-Range", "bytes */{}".format(total))],
                    status=416,
                )
            start, end = byte_range
            partial = payload[start:end + 1]
            headers = [h for h in headers if h[0] != "Content-Length"]
            headers.extend([
                ("Content-Length", str(len(partial))),
                ("Content-Range", "bytes {}-{}/{}".format(start, end, total)),
            ])
            return request.make_response(partial, headers=headers, status=206)

        return request.make_response(payload, headers=headers)

    def _preview_response(self, record, payload, etag):
        """Return a scaled thumbnail for an image file, or ``None``.

        ``None`` means "not previewable" — the caller falls back to serving
        the original, so a client asking for a preview of a PDF or a zip
        still gets a usable (if large) response instead of an error.

        The generated thumbnail is cached on the record's checksum so a
        folder listing does not re-encode the same image on every scroll.
        """
        try:
            width = int(request.httprequest.args.get("w") or 256)
        except (TypeError, ValueError):
            width = 256
        width = max(1, min(width, 2048))

        mimetype = record.mimetype or ""
        if not mimetype.startswith("image/"):
            return None

        cache_key = (record.id, record.checksum, width)
        cached = _PREVIEW_CACHE.get(cache_key)
        if cached is not None:
            return request.make_response(
                cached,
                headers=[
                    ("Content-Type", "image/jpeg"),
                    ("Content-Length", str(len(cached))),
                    ("ETag", etag),
                    ("Cache-Control", "private, max-age=3600"),
                ],
            )

        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(BytesIO(payload)) as image:
                image = image.convert("RGB")
                if image.width > width:
                    height = max(1, round(image.height * width / image.width))
                    image = image.resize((width, height), Image.LANCZOS)
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=82, optimize=True)
                thumbnail = buffer.getvalue()
        except Exception as exc:  # noqa: BLE001 - never fail a GET on preview
            _logger.info(
                "[WebDAV] preview failed for %s (%s): %s",
                record.name, record.id, exc)
            return None

        if len(_PREVIEW_CACHE) > _PREVIEW_CACHE_MAX:
            _PREVIEW_CACHE.clear()
        _PREVIEW_CACHE[cache_key] = thumbnail
        return request.make_response(
            thumbnail,
            headers=[
                ("Content-Type", "image/jpeg"),
                ("Content-Length", str(len(thumbnail))),
                ("ETag", etag),
                ("Cache-Control", "private, max-age=3600"),
            ],
        )

    def _put(self, path):
        # P1d: resumable / chunked upload. A client that sends Content-Range
        # is uploading one slice of a larger file; slices are buffered per
        # destination and assembled when the last one arrives. This is what
        # makes a 2 GB upload pausable and resumable (goal point 7).
        content_range = request.httprequest.headers.get("Content-Range")
        if content_range:
            return self._put_chunked(path, content_range)
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        data = request.httprequest.get_data()
        if record is not None and record_type == "file":
            if not record.with_user(request.env.user)._filtered_access("write"):
                return request.make_response(
                    "Forbidden: no write access to this resource", status=403)
            record.sudo().write({"content": base64.b64encode(data)})
            return request.make_response(
                "",
                headers=[("ETag", '"{}"'.format(record.checksum or ""))],
            )

        path = path.strip("/")
        *dir_parts, file_name = path.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = self._resolve(resolver, dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            # P1e: name the path that does not exist. "parent not found" alone
            # leaves the client guessing which segment it got wrong.
            return request.make_response(
                "Conflict: the parent collection '{}' does not exist. Create "
                "it first (MKCOL) and upload into it.".format(dir_path),
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=409,
            )

        if parent_type == "storage":
            # P1e: say what to do instead of only what went wrong. A client
            # dragging a file onto /webdav/Filsystem/ has no way to know that
            # files must live in a folder.
            return request.make_response(
                "Conflict: files must be created inside a folder, not directly "
                "under a storage. Create a directory first (MKCOL) and upload "
                "into it.",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=409,
            )

        if not parent_record.with_user(request.env.user)._filtered_access("create"):
            return request.make_response(
                "Forbidden: no create access in this directory", status=403)

        new_file = request.env["dms.file"].sudo().create({
            "name": file_name,
            "directory_id": parent_record.id,
            "content": base64.b64encode(data),
        })
        return request.make_response(
            "",
            headers=[("ETag", '"{}"'.format(new_file.checksum or ""))],
            status=201,
        )

    def _put_chunked(self, path, content_range):
        """Buffer one Content-Range slice and assemble on the final chunk.

        The buffer is keyed by destination path *and* user, so two people
        uploading to the same name cannot corrupt each other's file. A chunk
        is acknowledged with 202 until the last one arrives, which then
        creates or overwrites the dms.file and answers 201/204.
        """
        parsed = _parse_content_range(content_range)
        if parsed is None:
            return request.make_response(
                "Bad Request: malformed Content-Range header",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=400,
            )
        start, end, total = parsed
        data = request.httprequest.get_data()
        if len(data) != end - start + 1:
            return request.make_response(
                "Bad Request: Content-Range says {}-{} ({} bytes) but the "
                "body carried {} bytes".format(
                    start, end, end - start + 1, len(data)),
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=400,
            )

        key = (request.env.uid, path)
        upload = _UPLOAD_BUFFER.get(key)
        if upload is None or upload["total"] != total:
            if len(_UPLOAD_BUFFER) >= _UPLOAD_BUFFER_MAX:
                # Drop the oldest in-flight upload rather than grow without
                # bound. The client re-sends from offset 0 on a 202 mismatch.
                _UPLOAD_BUFFER.pop(next(iter(_UPLOAD_BUFFER)), None)
            upload = {"total": total, "chunks": {}, "received": 0}
            _UPLOAD_BUFFER[key] = upload

        if start not in upload["chunks"]:
            upload["chunks"][start] = data
            upload["received"] += len(data)

        if upload["received"] < total:
            return request.make_response(
                "",
                headers=[
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Range", "bytes 0-{}/{}".format(upload["received"] - 1, total)),
                ],
                status=202,
            )

        # Last chunk received: stitch the slices together in offset order.
        try:
            assembled = b"".join(
                upload["chunks"][offset]
                for offset in sorted(upload["chunks"])
            )
        except KeyError:
            _UPLOAD_BUFFER.pop(key, None)
            return request.make_response(
                "Bad Request: upload has a gap in its byte ranges",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=400,
            )
        _UPLOAD_BUFFER.pop(key, None)

        if len(assembled) != total:
            return request.make_response(
                "Bad Request: assembled {} bytes, expected {}".format(
                    len(assembled), total),
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=400,
            )

        return self._store_uploaded(path, assembled)

    def _store_uploaded(self, path, data):
        """Create or overwrite a dms.file with fully assembled content."""
        resolver = request.env["dms.webdav.path"]
        record, record_type = self._resolve(resolver, path)

        if record is not None and record_type == "file":
            if not record.with_user(request.env.user)._filtered_access("write"):
                return request.make_response(
                    "Forbidden: no write access to this resource", status=403)
            record.sudo().write({"content": base64.b64encode(data)})
            return request.make_response(
                "",
                headers=[("ETag", '"{}"'.format(record.checksum or ""))],
            )

        cleaned = path.strip("/")
        *dir_parts, file_name = cleaned.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = self._resolve(resolver, dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            return request.make_response(
                "Conflict: the parent collection '{}' does not exist. Create "
                "it first (MKCOL) and upload into it.".format(dir_path),
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=409,
            )
        if parent_type == "storage":
            return request.make_response(
                "Conflict: files must be created inside a folder, not directly "
                "under a storage. Create a directory first (MKCOL) and upload "
                "into it.",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=409,
            )
        if not parent_record.with_user(request.env.user)._filtered_access("create"):
            return request.make_response(
                "Forbidden: no create access in this directory", status=403)

        new_file = request.env["dms.file"].sudo().create({
            "name": file_name,
            "directory_id": parent_record.id,
            "content": base64.b64encode(data),
        })
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

        dest_path = urlparse(destination).path
        dest_path = "/" + "/".join(dest_path.strip("/").split("/")[1:])

        dest_record, dest_type = self._resolve(resolver, dest_path)

        if not record.with_user(request.env.user)._filtered_access("write"):
            return request.make_response("Forbidden", status=403)
        if dest_record is not None:
            return request.make_response("Conflict: destination already exists", status=409)

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

        dest_path = urlparse(destination).path
        dest_path = "/" + "/".join(dest_path.strip("/").split("/")[1:])

        dest_record, dest_type = self._resolve(resolver, dest_path)
        if dest_record is not None:
            return request.make_response("Conflict: destination already exists", status=409)

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
