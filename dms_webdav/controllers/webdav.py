import base64
import logging
from urllib.parse import urlparse

from odoo import http
from odoo.http import request
from odoo.service import db

_logger = logging.getLogger(__name__)

AUTH_HEADER = 'Basic realm="Odoo DMS WebDAV", charset="UTF-8"'


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

    @http.route(
        "/webdav/",
        type="http",
        auth="public",
        csrf=False,
        strict_slashes=False,
    )
    @http.route(
        "/webdav/<path:resource_path>",
        type="http",
        auth="public",
        csrf=False,
        strict_slashes=False,
    )
    def webdav_dispatch(self, resource_path=""):
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

    def _href(self, path):
        base_url = request.httprequest.url_root.rstrip("/")
        return f"{base_url}/webdav{path}"

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
        href = self._href(path)
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

    def _propfind_children(self, parent_path, record, resolver, depth):
        results = []
        children = []

        if record._name == "dms.storage":
            children = resolver.list_storage(record)
        elif record._name == "dms.directory":
            children = resolver.list_directory(record)
        else:
            return results

        for child_rec, child_type in children:
            child_path = f"{parent_path}/{child_rec.name}"
            results.append(self._propfind_response(child_path, child_type, child_rec))
            if depth == "infinity" and child_type == "directory":
                results.extend(self._propfind_children(child_path, child_rec, resolver, depth))
        return results

    def _propfind(self, path):
        depth = request.httprequest.headers.get("Depth", "0")
        resolver = request.env["dms.webdav.path"]

        record, record_type = resolver.resolve(path)

        responses = []
        if record is None and path == "/":
            responses.append(self._propfind_response("/", "collection", None))
            if depth in ("1", "infinity"):
                for storage in resolver.list_storages():
                    storage_path = f"/{storage.name}"
                    responses.append(self._propfind_response(storage_path, "storage", storage))
                    if depth == "infinity":
                        responses.extend(self._propfind_children(storage_path, storage, resolver, depth))
        elif record is not None:
            responses.append(self._propfind_response(path, record_type, record))
            if depth in ("1", "infinity"):
                responses.extend(self._propfind_children(path, record, resolver, depth))
        else:
            return request.make_response("Not Found", status=404)

        xml = '<?xml version="1.0" encoding="utf-8"?>\n'
        xml += '<d:multistatus xmlns:d="DAV:">\n'
        xml += '\n'.join(responses)
        xml += '\n</d:multistatus>'
        return request.make_response(xml, headers=[("Content-Type", "application/xml; charset=utf-8")])

    def _get(self, path, head=False):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        if record_type in ("storage", "directory"):
            return request.make_response("Method not allowed on collection", status=405)

        record.check_access("read")
        content = record.content
        if not content:
            return request.make_response("", status=204)

        last_modified = record.write_date
        last_modified_str = last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT") if last_modified else ""
        headers = [
            ("Content-Type", record.mimetype or "application/octet-stream"),
            ("Content-Length", str(int(record.size or 0))),
            ("ETag", '"{}"'.format(record.checksum or "")),
            ("Last-Modified", last_modified_str),
        ]
        if head:
            return request.make_response("", headers=headers)
        return request.make_response(
            base64.b64decode(content),
            headers=headers,
        )

    def _put(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        data = request.httprequest.data
        if record is not None and record_type == "file":
            record.check_access("write")
            record.write({"content": base64.b64encode(data)})
            return request.make_response(
                "",
                headers=[("ETag", '"{}"'.format(record.checksum or ""))],
            )

        path = path.strip("/")
        *dir_parts, file_name = path.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = resolver.resolve(dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            return request.make_response("Bad Request: parent not found", status=409)

        if parent_type == "storage":
            return request.make_response("Bad Request: cannot create file directly under storage", status=409)

        parent_record.check_access("create")

        new_file = request.env["dms.file"].create({
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
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        record.check_access("unlink")

        if record_type == "directory":
            if record.child_directory_ids or record.file_ids:
                return request.make_response("Conflict: directory not empty", status=409)

        record.unlink()
        return request.make_response("", status=204)

    def _mkcol(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is not None:
            return request.make_response("Conflict: resource already exists", status=409)

        path = path.strip("/")
        *dir_parts, dir_name = path.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = resolver.resolve(dir_path)

        if parent_record is None:
            return request.make_response("Conflict: parent not found", status=409)
        if parent_type not in ("storage", "directory"):
            return request.make_response("Bad Request", status=405)

        if parent_type == "storage":
            parent_record.check_access("create")
            request.env["dms.directory"].create({
                "name": dir_name,
                "storage_id": parent_record.id,
                "is_root_directory": True,
            })
        else:
            parent_record.check_access("create")
            request.env["dms.directory"].create({
                "name": dir_name,
                "parent_id": parent_record.id,
            })

        return request.make_response("", status=201)

    def _move(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        destination = request.httprequest.headers.get("Destination", "")
        if not destination:
            return request.make_response("Bad Request: no Destination header", status=400)

        dest_path = urlparse(destination).path
        dest_path = "/" + "/".join(dest_path.strip("/").split("/")[1:])

        dest_record, dest_type = resolver.resolve(dest_path)

        record.check_access("write")
        if dest_record is not None:
            return request.make_response("Conflict: destination already exists", status=409)

        dest_path_clean = dest_path.strip("/")
        *dest_dir_parts, dest_name = dest_path_clean.split("/")
        dest_dir_path = "/" + "/".join(dest_dir_parts) if dest_dir_parts else "/"
        parent_record, parent_type = resolver.resolve(dest_dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            return request.make_response("Conflict: destination parent not found", status=409)

        if record_type in ("file", "directory"):
            record.write({"name": dest_name})
            if record_type == "file" and parent_type == "directory":
                record.write({"directory_id": parent_record.id})

        return request.make_response("", status=204)

    def _copy(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        destination = request.httprequest.headers.get("Destination", "")
        if not destination:
            return request.make_response("Bad Request: no Destination header", status=400)

        dest_path = urlparse(destination).path
        dest_path = "/" + "/".join(dest_path.strip("/").split("/")[1:])

        dest_record, dest_type = resolver.resolve(dest_path)
        if dest_record is not None:
            return request.make_response("Conflict: destination already exists", status=409)

        dest_path_clean = dest_path.strip("/")
        *dest_dir_parts, dest_name = dest_path_clean.split("/")
        dest_dir_path = "/" + "/".join(dest_dir_parts) if dest_dir_parts else "/"
        parent_record, parent_type = resolver.resolve(dest_dir_path)

        if parent_record is None or parent_type not in ("storage", "directory"):
            return request.make_response("Conflict: destination parent not found", status=409)

        record.check_access("read")

        if record_type == "file":
            parent_record.check_access("create")
            request.env["dms.file"].create({
                "name": dest_name,
                "directory_id": parent_record.id,
                "content": record.content,
            })
        elif record_type == "directory":
            parent_record.check_access("create")
            new_dir = request.env["dms.directory"].create({
                "name": dest_name,
                "parent_id": parent_record.id if parent_type == "directory" else False,
                "storage_id": parent_record.id if parent_type == "storage" else parent_record.storage_id.id,
                "is_root_directory": parent_type == "storage",
            })
            self._copy_directory_contents(record, new_dir)

        return request.make_response("", status=204)

    def _copy_directory_contents(self, source_dir, target_dir):
        for child in source_dir.child_directory_ids:
            new_child = request.env["dms.directory"].create({
                "name": child.name,
                "parent_id": target_dir.id,
            })
            self._copy_directory_contents(child, new_child)
        for file_rec in source_dir.file_ids:
            request.env["dms.file"].create({
                "name": file_rec.name,
                "directory_id": target_dir.id,
                "content": file_rec.content,
            })

    def _lock(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        if record_type in ("storage", "directory"):
            return request.make_response(
                self._lock_xml("shared", path),
                headers=[("Content-Type", "application/xml; charset=utf-8")],
            )

        record.check_access("write")
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
            '<d:locktoken><d:href>opaquelocktoken:{}</d:href></d:locktoken>'.format(request.env.user.id)
            '</d:activelock>'
            '</d:lockdiscovery>'
            '</d:prop>'
        )

    def _unlock(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        if record_type == "file":
            record.check_access("write")
            record.unlock()

        return request.make_response("", status=204)
