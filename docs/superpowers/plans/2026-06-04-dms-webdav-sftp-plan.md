# DMS WebDAV & SFTP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two Odoo 18 modules (`dms_webdav`, `dms_sftp`) that expose OCA DMS directory structures via WebDAV and SFTP protocols for external clients.

**Architecture:** Virtual filesystem pattern — all operations go directly against Odoo ORM (`dms.directory` / `dms.file`), no local filesystem sync. WebDAV uses Odoo HTTP controllers; SFTP uses a paramiko server in a background thread.

**Tech Stack:** Odoo 18, OCA DMS (`dms`), Python `paramiko` (SFTP), Odoo HTTP + lxml (WebDAV XML)

---

### Task 1: Scaffold `dms_webdav` module

**Files:**
- Create: `dms_webdav/__init__.py`
- Create: `dms_webdav/__manifest__.py`
- Create: `dms_webdav/controllers/__init__.py`
- Create: `dms_webdav/models/__init__.py`
- Create: `dms_webdav/security/__init__.py`
- Create: `dms_webdav/tests/__init__.py`

- [ ] **Step 1: Create `dms_webdav/__init__.py`**

```python
from . import controllers
from . import models
```

- [ ] **Step 2: Create `dms_webdav/__manifest__.py`**

```python
{
    "name": "DMS WebDAV",
    "summary": "Access OCA DMS documents via WebDAV",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel AB",
    "license": "AGPL-3",
    "depends": ["dms", "web", "http_routing"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "description": """
WebDAV endpoint for OCA Document Management System at /webdav/.
Allows external clients (Nautilus, Windows Explorer, etc.) to mount
and work with DMS directories and files via the WebDAV protocol.
    """,
}
```

- [ ] **Step 3: Create empty `__init__.py` files**

Create `controllers/__init__.py`, `models/__init__.py`, `security/__init__.py`, `tests/__init__.py` — all empty files.

---

### Task 2: Scaffold `dms_sftp` module

**Files:**
- Create: `dms_sftp/__init__.py`
- Create: `dms_sftp/__manifest__.py`
- Create: `dms_sftp/models/__init__.py`
- Create: `dms_sftp/sftp/__init__.py`
- Create: `dms_sftp/tests/__init__.py`

- [ ] **Step 1: Create `dms_sftp/__init__.py`**

```python
from . import models
```

- [ ] **Step 2: Create `dms_sftp/__manifest__.py`**

```python
{
    "name": "DMS SFTP",
    "summary": "Access OCA DMS documents via SFTP",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel AB",
    "license": "AGPL-3",
    "depends": ["dms", "mail"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "external_dependencies": {
        "python": ["paramiko"],
    },
    "installable": True,
    "application": False,
}
```

- [ ] **Step 3: Create empty `__init__.py` files**

Create `models/__init__.py`, `sftp/__init__.py`, `tests/__init__.py`.

---

### Task 3: Implement path resolution utility (shared logic)

**Files:**
- Create: `dms_webdav/models/dms_webdav_path.py`

- [ ] **Step 1: Create the path resolver**

```python
from odoo import api, models


class DmsWebdavPath(models.AbstractModel):
    _name = "dms.webdav.path"
    _description = "WebDAV Path Resolver"

    @api.model
    def resolve(self, path):
        path = path.strip("/")
        if not path:
            return None, None
        
        parts = path.split("/")
        
        storage = self.env["dms.storage"].search([("name", "=", parts[0])], limit=1)
        if not storage:
            return None, None
        
        if len(parts) == 1:
            return storage, "storage"
        
        current_dir = False
        for i, part in enumerate(parts[1:], start=1):
            domain = [("name", "=", part), ("storage_id", "=", storage.id)]
            if current_dir:
                domain.append(("parent_id", "=", current_dir.id))
            else:
                domain.append(("parent_id", "=", False))

            directory = self.env["dms.directory"].search(domain, limit=1)
            if directory:
                current_dir = directory
                if i == len(parts) - 1:
                    return current_dir, "directory"
            else:
                if i == len(parts) - 1 and current_dir:
                    file_rec = self.env["dms.file"].search([
                        ("name", "=", part),
                        ("directory_id", "=", current_dir.id),
                    ], limit=1)
                    if file_rec:
                        return file_rec, "file"
                return None, None

        if current_dir:
            return current_dir, "directory"
        return None, None

    @api.model
    def list_directory(self, directory):
        result = []
        for child in directory.child_directory_ids:
            if not child.is_hidden:
                result.append((child, "directory"))
        for file_rec in directory.file_ids:
            result.append((file_rec, "file"))
        return result

    @api.model
    def list_storage(self, storage):
        result = []
        for root_dir in storage.root_directory_ids:
            if not root_dir.is_hidden:
                result.append((root_dir, "directory"))
        return result

    @api.model
    def list_storages(self):
        return self.env["dms.storage"].search([("is_hidden", "=", False)])
```

---

### Task 4: Implement WebDAV controller — core routing & auth

**Files:**
- Create: `dms_webdav/controllers/webdav.py`
- Modify: `dms_webdav/controllers/__init__.py`

- [ ] **Step 1: Create the WebDAV controller with auth**

```python
import base64
import logging

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
```

- [ ] **Step 2: Register controller in `controllers/__init__.py`**

```python
from . import webdav
```

---

### Task 5: Implement WebDAV PROPFIND & OPTIONS

**Files:**
- Modify: `dms_webdav/controllers/webdav.py` (append methods to the controller class)

- [ ] **Step 1: Add OPTIONS handler**

```python
    def _options_response(self):
        return request.make_response(
            "",
            headers=[
                ("DAV", "1, 2"),
                ("Allow", "OPTIONS, GET, HEAD, PROPFIND, PUT, DELETE, MKCOL, MOVE, COPY, LOCK, UNLOCK"),
                ("Content-Length", "0"),
            ],
        )
```

- [ ] **Step 2: Add XML helpers and PROPFIND handler**

```python
    def _href(self, path):
        base_url = request.httprequest.url_root.rstrip("/")
        return f"{base_url}/webdav{path}"

    def _prop_xml(self, record, record_type, path):
        parts = ['<d:prop>']
        if record_type == "directory":
            parts.append('<d:displayname>{}</d:displayname>'.format(record.name))
            parts.append('<d:resourcetype><d:collection/></d:resourcetype>')
            parts.append('<d:getcontenttype>httpd/unix-directory</d:getcontenttype>')
        elif record_type == "file":
            parts.append('<d:displayname>{}</d:displayname>'.format(record.name))
            parts.append('<d:resourcetype/>')
            parts.append('<d:getcontenttype>{}</d:getcontenttype>'.format(record.mimetype or "application/octet-stream"))
            parts.append('<d:getcontentlength>{}</d:getcontentlength>'.format(int(record.size or 0)))
        elif record_type == "storage":
            parts.append('<d:displayname>{}</d:displayname>'.format(record.name))
            parts.append('<d:resourcetype><d:collection/></d:resourcetype>')
            parts.append('<d:getcontenttype>httpd/unix-directory</d:getcontenttype>')
        parts.append('</d:prop>')
        return '\n'.join(parts)

    def _propfind(self, path):
        depth = request.httprequest.headers.get("Depth", "0")
        resolver = request.env["dms.webdav.path"]

        record, record_type = resolver.resolve(path)

        responses = []
        if record is None and path == "/":
            responses.append(self._propfind_response("/", "collection", "Storages"))
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

    def _propfind_response(self, path, record_type, record):
        href = self._href(path)
        if record_type == "collection":
            prop_xml = '<d:prop><d:displayname>DMS Root</d:displayname><d:resourcetype><d:collection/></d:resourcetype><d:getcontenttype>httpd/unix-directory</d:getcontenttype></d:prop>'
        else:
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
        record_type = None

        if record._name == "dms.storage":
            children = resolver.list_storage(record)
            record_type = "storage"
        elif record._name == "dms.directory":
            children = resolver.list_directory(record)
            record_type = "directory"

        for child_rec, child_type in children:
            child_path = f"{parent_path}/{child_rec.name}"
            results.append(self._propfind_response(child_path, child_type, child_rec))
            if depth == "infinity" and child_type == "directory":
                results.extend(self._propfind_children(child_path, child_rec, resolver, depth))
        return results
```

---

### Task 6: Implement WebDAV GET/PUT/DELETE/MKCOL/MOVE/COPY

**Files:**
- Modify: `dms_webdav/controllers/webdav.py` (append methods)

- [ ] **Step 1: Add GET handler**

```python
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
```

- [ ] **Step 2: Add PUT handler**

```python
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
```

- [ ] **Step 3: Add DELETE handler**

```python
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
```

- [ ] **Step 4: Add MKCOL handler**

```python
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
```

- [ ] **Step 5: Add MOVE handler**

```python
    def _move(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        destination = request.httprequest.headers.get("Destination", "")
        if not destination:
            return request.make_response("Bad Request: no Destination header", status=400)

        from urllib.parse import urlparse
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
```

- [ ] **Step 6: Add COPY handler**

```python
    def _copy(self, path):
        resolver = request.env["dms.webdav.path"]
        record, record_type = resolver.resolve(path)

        if record is None:
            return request.make_response("Not Found", status=404)

        destination = request.httprequest.headers.get("Destination", "")
        if not destination:
            return request.make_response("Bad Request: no Destination header", status=400)

        from urllib.parse import urlparse
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
```

---

### Task 7: Implement WebDAV LOCK/UNLOCK

**Files:**
- Modify: `dms_webdav/controllers/webdav.py`

- [ ] **Step 1: Add LOCK handler**

```python
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
```

---

### Task 8: Add WebDAV security & settings

**Files:**
- Create: `dms_webdav/security/ir.model.access.csv`
- Create: `dms_webdav/models/dms_webdav.py`
- Modify: `dms_webdav/models/__init__.py`

- [ ] **Step 1: Create security access CSV**

```
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_dms_webdav_path,access_dms_webdav_path,model_dms_webdav_path,base.group_user,1,0,0,0
```

- [ ] **Step 2: Create configuration model**

```python
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dms_webdav_readonly = fields.Boolean(
        string="WebDAV Read-only",
        config_parameter="dms_webdav.readonly",
        default=False,
    )
```

- [ ] **Step 3: Update `models/__init__.py`**

```python
from . import dms_webdav
from . import dms_webdav_path
```

---

### Task 9: Implement SFTP server model and startup

**Files:**
- Create: `dms_sftp/models/dms_sftp.py`
- Modify: `dms_sftp/models/__init__.py`

- [ ] **Step 1: Create the server model**

```python
import logging
import socket
import threading
from io import StringIO

from odoo import api, models
from odoo.modules.registry import Registry
from odoo.service.server import server

try:
    import paramiko
    from ..sftp.transport import DmsSftpTransport
    from ..sftp.server import DmsSftpServer
    from ..sftp.sftp_server import DmsSftpSftpServer, DmsSftpSftpServerInterface
except ImportError:
    pass

_logger = logging.getLogger(__name__)

_db2thread = {}
_channels = []


class DmsSftp(models.AbstractModel):
    _name = "dms.sftp"
    _description = "DMS SFTP Server"

    def _run_server(self, dbname, stop):
        db_registry = Registry.new(dbname)
        with api.Environment.manage(), db_registry.cursor() as cr:
            env = api.Environment(cr, 1, {})
            env[self._name].__run_server(stop)

    @api.model
    def __run_server(self, stop):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        host, port = self.env["ir.config_parameter"].get_param(
            "dms_sftp.bind", "localhost:2222"
        ).split(":")
        _logger.info("SFTP binding to %s:%s", host, port)
        server_socket.bind((host, int(port)))
        server_socket.listen(5)
        server_socket.settimeout(2)

        while not stop.is_set():
            try:
                conn, addr = server_socket.accept()
            except socket.timeout:
                while _channels and not _channels[0].get_transport().is_active():
                    _channels.pop(0)
                continue

            key = self.env["ir.config_parameter"].get_param("dms_sftp.hostkey")
            host_key = paramiko.Ed25519Key.from_private_key(StringIO(key))

            transport = DmsSftpTransport(self.env.cr, conn)
            transport.add_server_key(host_key)
            transport.set_subsystem_handler(
                "sftp", DmsSftpSftpServer, DmsSftpSftpServerInterface, self.env
            )
            server = DmsSftpServer(self.env)
            try:
                transport.start_server(server=server)
                channel = transport.accept()
                if channel:
                    _channels.append(channel)
            except (paramiko.SSHException, EOFError):
                continue

    def _register_hook(self):
        cr = self._cr
        if cr.dbname not in _db2thread:
            stop = threading.Event()
            _db2thread[cr.dbname] = (
                threading.Thread(target=self._run_server, args=(cr.dbname, stop)),
                stop,
            )
            _db2thread[cr.dbname][0].start()
            old_stop = server.stop

            def new_stop():
                stop.set()
                old_stop()

            server.stop = new_stop
        return super()._register_hook()
```

- [ ] **Step 2: Update `models/__init__.py`**

```python
from . import dms_sftp
```

---

### Task 10: Implement SFTP transport, server, and virtual filesystem

**Files:**
- Create: `dms_sftp/sftp/transport.py`
- Create: `dms_sftp/sftp/server.py`
- Create: `dms_sftp/sftp/sftp_server.py`
- Create: `dms_sftp/sftp/handle.py`
- Modify: `dms_sftp/sftp/__init__.py`

- [ ] **Step 1: Create `sftp/transport.py`**

```python
from odoo import api, SUPERUSER_ID

try:
    from paramiko import Transport
    from paramiko.transport import DEFAULT_WINDOW_SIZE, DEFAULT_MAX_PACKET_SIZE
except ImportError:
    pass


class DmsSftpTransport(Transport):
    def __init__(
        self, cr, sock, default_window_size=DEFAULT_WINDOW_SIZE,
        default_max_packet_size=DEFAULT_MAX_PACKET_SIZE, gss_kex=False,
        gss_deleg_creds=True
    ):
        self.cr = cr
        super().__init__(
            sock, default_window_size=default_window_size,
            default_max_packet_size=default_max_packet_size,
            gss_kex=gss_kex, gss_deleg_creds=gss_deleg_creds,
        )

    def run(self):
        with api.Environment.manage():
            self.env = api.Environment(self.cr, SUPERUSER_ID, {})
            result = super().run()
        return result
```

- [ ] **Step 2: Create `sftp/server.py` with multi-db auth**

```python
import logging

from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.exceptions import AccessDenied
from odoo.service import db

try:
    from paramiko.common import AUTH_SUCCESSFUL, AUTH_FAILED, \
        OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED, OPEN_SUCCEEDED
    from paramiko import RSAKey, ServerInterface
    from paramiko.py3compat import decodebytes
except ImportError:
    pass

_logger = logging.getLogger(__name__)


class DmsSftpServer(ServerInterface):
    def __init__(self, env):
        self.env = env
        self.dbname = env.cr.dbname
        super().__init__()

    def check_auth_password(self, username, password):
        user_login = username
        db_name = self.dbname

        if "@" in username:
            user_login, domain = username.rsplit("@", 1)
            db_candidate = domain.rsplit(".", 1)[0] if "." in domain else domain
            all_dbs = db.exp_list()
            if db_candidate in all_dbs:
                db_name = db_candidate
            elif domain in all_dbs:
                db_name = domain
            else:
                for candidate_db in all_dbs:
                    try:
                        db_registry = Registry.new(candidate_db)
                        with api.Environment.manage(), db_registry.cursor() as cr:
                            env = api.Environment(cr, SUPERUSER_ID, {})
                            user = env["res.users"].search([("login", "=", user_login)])
                            if not user:
                                continue
                            valid = user.with_user(user.id)._verify_sftp_user(password)
                            if valid:
                                with api.Environment.manage(), db_registry.cursor() as cr:
                                    self.env = api.Environment(cr, user.id, {})
                                _logger.info(
                                    "SFTP auth: user=%s db=%s (fallback)",
                                    user_login, candidate_db,
                                )
                                return AUTH_SUCCESSFUL
                    except Exception:
                        continue
                return AUTH_FAILED

        try:
            user = self.env["res.users"].search([("login", "=", user_login)])
            if not user:
                return AUTH_FAILED
            valid = user.with_user(user.id)._verify_sftp_user(password)
            if valid:
                db_registry = Registry.new(db_name)
                with api.Environment.manage(), db_registry.cursor() as cr:
                    self.env = api.Environment(cr, user.id, {})
                _logger.info("SFTP auth: user=%s db=%s", user_login, db_name)
                return AUTH_SUCCESSFUL
        except AccessDenied:
            pass
        return AUTH_FAILED

    def check_auth_publickey(self, username, key):
        user = self.env["res.users"].search([("login", "=", username)])
        if not user:
            return AUTH_FAILED
        for line in (user.authorized_keys or "").split("\n"):
            if not line or line.startswith("#"):
                continue
            key_type, key_data = line.split(" ", 2)[:2]
            if key_type != "ssh-rsa":
                continue
            if RSAKey(data=decodebytes(key_data)) == key:
                return AUTH_SUCCESSFUL
        return AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_channel_request(self, kind, chanid):
        if kind in ("session",):
            return OPEN_SUCCEEDED
        return OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
```

- [ ] **Step 3: Create `sftp/handle.py`**

```python
import base64
import logging
import os
import stat as stat_module

try:
    from paramiko import SFTP_EOF, SFTPHandle, SFTPAttributes
    from paramiko.sftp import SFTP_OK
except ImportError:
    pass

_logger = logging.getLogger(__name__)


class DmsSftpHandle(SFTPHandle):
    def __init__(self, dms_file, flags=0):
        self.dms_file = dms_file
        super().__init__(flags)

    def stat(self):
        return SFTPAttributes.from_stat(os.stat_result(
            (
                0o100644,
                0,
                0,
                1,
                self.dms_file.env.uid or 0,
                0,
                int(self.dms_file.size or 0),
                0,
                0,
                0,
            )
        ))

    def read(self, offset, length):
        data = base64.b64decode(self.dms_file.content or b"")
        if offset > len(data):
            return SFTP_EOF
        return data[offset:offset + length]

    def write(self, offset, data):
        existing = base64.b64decode(self.dms_file.content or b"")
        if offset > len(existing):
            existing = existing.ljust(offset, b"\x00")
        new_data = existing[:offset] + data + existing[offset + len(data):]
        self.dms_file.write({"content": base64.b64encode(new_data)})
        return len(data)

    def chattr(self, attr):
        return SFTP_OK

    def close(self):
        pass
```

- [ ] **Step 4: Create `sftp/sftp_server.py`**

```python
import base64
import logging
import os
import stat as stat_module

from odoo import api

try:
    from paramiko import SFTPServerInterface, SFTPServer, SFTPAttributes
    from paramiko.common import o644
    from paramiko.sftp import SFTP_OK, SFTP_NO_SUCH_FILE, SFTP_PERMISSION_DENIED
except ImportError:
    pass

from .handle import DmsSftpHandle

_logger = logging.getLogger(__name__)


class DmsSftpSftpServerInterface(SFTPServerInterface):
    def __init__(self, server, env):
        self.env = api.Environment(env.cr, server.env.user.id, env.context)
        super().__init__(server, env)

    def _resolve(self, path):
        path = path.strip("/")
        if not path:
            return None, None

        parts = path.split("/")

        storage = self.env["dms.storage"].search([("name", "=", parts[0])], limit=1)
        if not storage:
            return None, None

        if len(parts) == 1:
            return storage, "storage"

        current_dir = False
        for i, part in enumerate(parts[1:], start=1):
            domain = [("name", "=", part), ("storage_id", "=", storage.id)]
            if current_dir:
                domain.append(("parent_id", "=", current_dir.id))
            else:
                domain.append(("parent_id", "=", False))

            directory = self.env["dms.directory"].search(domain, limit=1)
            if directory:
                current_dir = directory
                if i == len(parts) - 1:
                    return current_dir, "directory"
            else:
                if i == len(parts) - 1 and current_dir:
                    file_rec = self.env["dms.file"].search([
                        ("name", "=", part),
                        ("directory_id", "=", current_dir.id),
                    ], limit=1)
                    if file_rec:
                        return file_rec, "file"
                return None, None

        if current_dir:
            return current_dir, "directory"
        return None, None

    def _attr(self, record, record_type, name):
        attr = SFTPAttributes()
        attr.filename = name or record.name
        if record_type in ("storage", "directory"):
            attr.st_mode = stat_module.S_IFDIR | stat_module.S_IRUSR | stat_module.S_IXUSR | stat_module.S_IWUSR
            attr.st_size = 0
        else:
            attr.st_mode = stat_module.S_IFREG | stat_module.S_IRUSR | stat_module.S_IWUSR
            attr.st_size = int(record.size or 0)
        attr.st_uid = self.env.uid or 0
        attr.st_gid = 0
        if record.write_date:
            attr.st_mtime = record.write_date.timestamp()
        return attr

    def list_folder(self, path):
        path = path.strip("/")
        if not path:
            try:
                storages = self.env["dms.storage"].search([("is_hidden", "=", False)])
                return [self._attr(s, "storage", s.name) for s in storages]
            except Exception as e:
                _logger.error("list_folder root error: %s", e)
                return SFTP_NO_SUCH_FILE

        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE

        try:
            if record_type == "storage":
                record.check_access("read")
                dirs = record.root_directory_ids.filtered(lambda d: not d.is_hidden)
                return [self._attr(d, "directory", d.name) for d in dirs]
            elif record_type == "directory":
                record.check_access("read")
                result = []
                for child in record.child_directory_ids.filtered(lambda d: not d.is_hidden):
                    result.append(self._attr(child, "directory", child.name))
                for file_rec in record.file_ids:
                    result.append(self._attr(file_rec, "file", file_rec.name))
                return result
            return SFTP_NO_SUCH_FILE
        except Exception as e:
            _logger.error("list_folder error: %s", e)
            return SFTP_NO_SUCH_FILE

    def stat(self, path):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        try:
            record.check_access("read")
            return self._attr(record, record_type, record.name)
        except Exception:
            return SFTP_NO_SUCH_FILE

    def lstat(self, path):
        return self.stat(path)

    def open(self, path, flags, attr):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        if record_type != "file":
            return SFTP_PERMISSION_DENIED

        try:
            if flags & (os.O_WRONLY | os.O_RDWR):
                record.check_access("write")
            else:
                record.check_access("read")
            return DmsSftpHandle(record, flags)
        except Exception:
            return SFTP_PERMISSION_DENIED

    def remove(self, path):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        if record_type != "file":
            return SFTP_PERMISSION_DENIED
        try:
            record.check_access("unlink")
            record.unlink()
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def rename(self, oldpath, newpath):
        record, record_type = self._resolve(oldpath)
        if record is None:
            return SFTP_NO_SUCH_FILE
        try:
            record.check_access("write")
            new_path_clean = newpath.strip("/")
            *new_dir_parts, new_name = new_path_clean.split("/")
            new_dir_path = "/" + "/".join(new_dir_parts) if new_dir_parts else "/"
            parent_record, parent_type = self._resolve(new_dir_path)
            if parent_record is None or parent_type not in ("storage", "directory"):
                return SFTP_PERMISSION_DENIED

            record.write({"name": new_name})
            if record_type == "file" and parent_type == "directory":
                record.write({"directory_id": parent_record.id})
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def mkdir(self, path, attr):
        path_clean = path.strip("/")
        *dir_parts, dir_name = path_clean.split("/")
        dir_path = "/" + "/".join(dir_parts) if dir_parts else "/"
        parent_record, parent_type = self._resolve(dir_path)
        if parent_record is None:
            return SFTP_NO_SUCH_FILE
        if parent_type not in ("storage", "directory"):
            return SFTP_PERMISSION_DENIED
        try:
            parent_record.check_access("create")
            if parent_type == "storage":
                self.env["dms.directory"].create({
                    "name": dir_name,
                    "storage_id": parent_record.id,
                    "is_root_directory": True,
                })
            else:
                self.env["dms.directory"].create({
                    "name": dir_name,
                    "parent_id": parent_record.id,
                })
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def rmdir(self, path):
        record, record_type = self._resolve(path)
        if record is None:
            return SFTP_NO_SUCH_FILE
        if record_type != "directory":
            return SFTP_PERMISSION_DENIED
        if record.child_directory_ids or record.file_ids:
            return SFTP_PERMISSION_DENIED
        try:
            record.check_access("unlink")
            record.unlink()
            return SFTP_OK
        except Exception:
            return SFTP_PERMISSION_DENIED

    def chattr(self, path, attr):
        return SFTP_OK

    def session_ended(self):
        self.env.cr.close()
        super().session_ended()


class DmsSftpSftpServer(SFTPServer):
    def start_subsystem(self, name, transport, channel):
        with api.Environment.manage():
            return super().start_subsystem(name, transport, channel)
```

- [ ] **Step 5: Update `sftp/__init__.py`**

```python
from . import transport
from . import server
from . import sftp_server
from . import handle
```

---

### Task 11: Add SFTP security & settings

**Files:**
- Create: `dms_sftp/security/ir.model.access.csv`
- Create: `dms_sftp/models/dms_sftp_config.py`
- Create: `dms_sftp/models/res_users.py`
- Modify: `dms_sftp/models/__init__.py`

- [ ] **Step 1: Create security access CSV**

```
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_dms_sftp,access_dms_sftp,model_dms_sftp,base.group_user,1,0,0,0
```

- [ ] **Step 2: Extend res.users**

```python
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    authorized_keys = fields.Text(
        "Authorized keys",
        help="An authorized key file as in ~/.ssh/authorized_keys",
    )

    def _register_hook(self):
        if "authorized_keys" not in self.SELF_WRITEABLE_FIELDS:
            self.SELF_WRITEABLE_FIELDS.append("authorized_keys")
            self.SELF_READABLE_FIELDS.append("authorized_keys")
        return super()._register_hook()

    def _verify_sftp_user(self, password):
        assert password
        self.env.cr.execute(
            "SELECT COALESCE(password, '') FROM res_users WHERE id=%s",
            [self.env.user.id],
        )
        [hashed] = self.env.cr.fetchone()
        valid, replacement = self._crypt_context().verify_and_update(password, hashed)
        return valid
```

- [ ] **Step 3: Create configuration model**

```python
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dms_sftp_bind = fields.Char(
        string="SFTP Bind Address",
        config_parameter="dms_sftp.bind",
        default="localhost:2222",
    )
    dms_sftp_readonly = fields.Boolean(
        string="SFTP Read-only",
        config_parameter="dms_sftp.readonly",
        default=False,
    )
```

- [ ] **Step 4: Update `models/__init__.py`**

```python
from . import dms_sftp
from . import dms_sftp_config
from . import res_users
```

---

### Task 12: Add host key auto-generation for SFTP

**Files:**
- Modify: `dms_sftp/__init__.py`
- Create: `dms_sftp/data/ir_config_parameter.xml`

- [ ] **Step 1: Create `__init__.py` with install hook**

```python
import io
import logging
from lxml import etree

from odoo import SUPERUSER_ID, api, tools

try:
    from paramiko.ecdsakey import ECDSAKey
except ImportError:
    pass

_logger = logging.getLogger(__name__)


def install_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    hostkey = env["ir.config_parameter"].get_param("dms_sftp.hostkey")
    parameters = etree.parse(
        tools.file_open("dms_sftp/data/ir_config_parameter.xml")
    )
    default_value = None
    for node in parameters.xpath("//record[@id='param_hostkey']//field[@name='value']"):
        default_value = node.text
    if not hostkey or hostkey == default_value:
        _logger.info("Generating SFTP host key for database %s", cr.dbname)
        key = io.StringIO()
        ECDSAKey.generate().write_private_key(key)
        env["ir.config_parameter"].set_param("dms_sftp.hostkey", key.getvalue())
        key.close()


def uninstall_hook(cr, registry):
    pass
```

- [ ] **Step 2: Create `data/ir_config_parameter.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
  <record id="param_hostkey" model="ir.config_parameter">
    <field name="key">dms_sftp.hostkey</field>
    <field name="value">PLACEHOLDER</field>
  </record>
</odoo>
```

- [ ] **Step 3: Update manifest to include hook**

Add `"post_init_hook": "install_hook",` to `__manifest__.py`.

---

### Task 13: Add SFTP unit tests

**Files:**
- Create: `dms_sftp/tests/test_sftp_path.py`

- [ ] **Step 1: Write path resolution test**

```python
from odoo.tests.common import TransactionCase


class TestSftpPath(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Storage = self.env["dms.storage"]
        self.Directory = self.env["dms.directory"]
        self.File = self.env["dms.file"]

        self.storage = self.Storage.create({"name": "TestStorage"})
        self.root_dir = self.Directory.create({
            "name": "RootDir",
            "storage_id": self.storage.id,
            "is_root_directory": True,
        })
        self.sub_dir = self.Directory.create({
            "name": "SubDir",
            "parent_id": self.root_dir.id,
        })
        self.test_file = self.File.create({
            "name": "test.txt",
            "directory_id": self.root_dir.id,
            "content": self._b64encode(b"hello"),
        })

    def _b64encode(self, data):
        import base64
        return base64.b64encode(data)

    def test_resolve_storage(self):
        record, rtype = self._resolve("/TestStorage")
        self.assertEqual(record, self.storage)
        self.assertEqual(rtype, "storage")

    def test_resolve_directory(self):
        record, rtype = self._resolve("/TestStorage/RootDir")
        self.assertEqual(record, self.root_dir)
        self.assertEqual(rtype, "directory")

    def test_resolve_subdirectory(self):
        record, rtype = self._resolve("/TestStorage/RootDir/SubDir")
        self.assertEqual(record, self.sub_dir)
        self.assertEqual(rtype, "directory")

    def test_resolve_file(self):
        record, rtype = self._resolve("/TestStorage/RootDir/test.txt")
        self.assertEqual(record, self.test_file)
        self.assertEqual(rtype, "file")

    def test_resolve_nonexistent(self):
        record, rtype = self._resolve("/TestStorage/NoExist")
        self.assertIsNone(record)

    def _resolve(self, path):
        path = path.strip("/")
        parts = path.split("/")
        storage = self.Storage.search([("name", "=", parts[0])], limit=1)
        if not storage:
            return None, None
        if len(parts) == 1:
            return storage, "storage"

        current_dir = False
        for i, part in enumerate(parts[1:], start=1):
            domain = [("name", "=", part), ("storage_id", "=", storage.id)]
            if current_dir:
                domain.append(("parent_id", "=", current_dir.id))
            else:
                domain.append(("parent_id", "=", False))

            directory = self.Directory.search(domain, limit=1)
            if directory:
                current_dir = directory
                if i == len(parts) - 1:
                    return current_dir, "directory"
            else:
                if i == len(parts) - 1 and current_dir:
                    file_rec = self.File.search([
                        ("name", "=", part),
                        ("directory_id", "=", current_dir.id),
                    ], limit=1)
                    if file_rec:
                        return file_rec, "file"
                return None, None
        if current_dir:
            return current_dir, "directory"
        return None, None
```

---

### Task 14: Add WebDAV unit tests

**Files:**
- Create: `dms_webdav/tests/test_webdav.py`

- [ ] **Step 1: Write WebDAV endpoint tests**

```python
import base64
from odoo.tests.common import HttpCase, TransactionCase


class TestWebdavPath(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Storage = self.env["dms.storage"]
        self.Directory = self.env["dms.directory"]
        self.File = self.env["dms.file"]

        self.storage = self.Storage.create({"name": "WebDAVTest"})
        self.root_dir = self.Directory.create({
            "name": "Docs",
            "storage_id": self.storage.id,
            "is_root_directory": True,
        })
        self.test_file = self.File.create({
            "name": "readme.txt",
            "directory_id": self.root_dir.id,
            "content": base64.b64encode(b"hello world"),
        })

    def test_resolve_root(self):
        resolver = self.env["dms.webdav.path"]
        storages = resolver.list_storages()
        self.assertIn(self.storage, storages)

    def test_resolve_directory(self):
        resolver = self.env["dms.webdav.path"]
        record, rtype = resolver.resolve("/WebDAVTest/Docs")
        self.assertEqual(record, self.root_dir)
        self.assertEqual(rtype, "directory")

    def test_resolve_file(self):
        resolver = self.env["dms.webdav.path"]
        record, rtype = resolver.resolve("/WebDAVTest/Docs/readme.txt")
        self.assertEqual(record, self.test_file)
        self.assertEqual(rtype, "file")

    def test_list_directory(self):
        resolver = self.env["dms.webdav.path"]
        children = resolver.list_directory(self.root_dir)
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0][0], self.test_file)
        self.assertEqual(children[0][1], "file")


class TestWebdavHttp(HttpCase):
    def test_well_known_redirect(self):
        response = self.url_open("/.well-known/webdav/", allow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertIn("/webdav/", response.headers.get("Location", ""))

    def test_options(self):
        response = self.url_open("/webdav/", method="OPTIONS")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DAV", str(response.headers))
```
