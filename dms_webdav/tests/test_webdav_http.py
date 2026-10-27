import base64
import hashlib
import io
import os

import requests

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWebdavHttp(HttpCase):
    """HTTP-level tests for the WebDAV controller.

    ``HttpCase.url_open()`` cannot send arbitrary verbs (it has no ``method``
    argument in 18.0), so every WebDAV request goes through ``requests``
    against ``self.base_url()``. That is also closer to what a real client
    does, which is the point of these tests.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.user = cls.env["res.users"].create({
            "name": "WebDAV Test",
            "login": "webdav_test@example.com",
            "password": "webdav_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("dms.group_dms_manager").id,
            ])],
        })
        cls.storage = cls.env["dms.storage"].create({"name": "WebdavTestStorage"})
        cls.root = cls.env["dms.directory"].sudo().search([
            ("storage_id", "=", cls.storage.id),
            ("is_root_directory", "=", True),
        ], limit=1)
        if not cls.root:
            # A storage does not always get a root directory for free; the
            # controller expects one, so create it the way the UI does.
            cls.root = cls.env["dms.directory"].sudo().create({
                "name": cls.storage.name,
                "storage_id": cls.storage.id,
                "is_root_directory": True,
            })
        cls.directory = cls.env["dms.directory"].sudo().create({
            "name": "TestDir",
            "storage_id": cls.storage.id,
            "parent_id": cls.root.id,
            "permission_read": True,
            "permission_write": True,
            "permission_create": True,
            "permission_unlink": True,
        })
        cls.payload = os.urandom(4096)
        cls.file = cls.env["dms.file"].sudo().create({
            "name": "data.bin",
            "directory_id": cls.directory.id,
            "content": base64.b64encode(cls.payload),
        })

    def _url(self, path=""):
        return self.base_url() + "/webdav/WebdavTestStorage/WebdavTestStorage/TestDir/" + path

    def _auth(self):
        return (self.user.login, "webdav_test")

    def _request(self, method, path="", **kwargs):
        return requests.request(
            method,
            self._url(path),
            auth=kwargs.pop("auth", self._auth()),
            timeout=30,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Discovery and auth gate
    # ------------------------------------------------------------------
    def test_well_known_redirect(self):
        response = requests.get(
            self.base_url() + "/.well-known/webdav/",
            allow_redirects=False,
            timeout=30,
        )
        self.assertEqual(response.status_code, 307)
        self.assertIn("/webdav/", response.headers.get("Location", ""))

    def test_options_no_auth(self):
        response = requests.options(self.base_url() + "/webdav/", timeout=30)
        self.assertEqual(response.status_code, 200)
        self.assertIn("DAV", response.headers)
        self.assertIn("Allow", response.headers)

    def test_options_on_subpath(self):
        response = requests.options(
            self.base_url() + "/webdav/some/resource", timeout=30)
        self.assertEqual(response.status_code, 200)
        self.assertIn("DAV", response.headers)

    def test_propfind_unauthorized(self):
        response = requests.request(
            "PROPFIND", self.base_url() + "/webdav/", timeout=30)
        self.assertEqual(response.status_code, 401)

    def test_get_unauthorized(self):
        response = requests.get(
            self.base_url() + "/webdav/", allow_redirects=False, timeout=30)
        self.assertEqual(response.status_code, 401)

    def test_put_requires_auth(self):
        response = requests.put(
            self.base_url() + "/webdav/some/file.txt", data=b"x", timeout=30)
        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # P1a / P1b: Range and HEAD
    # ------------------------------------------------------------------
    def test_get_full_body(self):
        response = self._request("GET", "data.bin")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.payload)
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")

    def test_get_range_returns_206(self):
        response = self._request("GET", "data.bin", headers={"Range": "bytes=0-1023"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 1024)
        self.assertEqual(response.content, self.payload[:1024])
        self.assertEqual(
            response.headers["Content-Range"],
            "bytes 0-1023/{}".format(len(self.payload)),
        )
        self.assertEqual(response.headers["Content-Length"], "1024")

    def test_get_open_ended_range(self):
        response = self._request(
            "GET", "data.bin", headers={"Range": "bytes=2048-"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.payload[2048:])

    def test_get_suffix_range(self):
        response = self._request("GET", "data.bin", headers={"Range": "bytes=-500"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 500)
        self.assertEqual(response.content, self.payload[-500:])

    def test_get_unsatisfiable_range_returns_416(self):
        response = self._request(
            "GET", "data.bin", headers={"Range": "bytes=99999999-"})
        self.assertEqual(response.status_code, 416)
        self.assertEqual(
            response.headers["Content-Range"],
            "bytes */{}".format(len(self.payload)),
        )

    def test_get_malformed_range_returns_416(self):
        response = self._request("GET", "data.bin", headers={"Range": "garbage"})
        self.assertEqual(response.status_code, 416)

    def test_head_reports_real_length(self):
        response = self._request("HEAD", "data.bin")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Length"], str(len(self.payload)))
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        self.assertEqual(response.content, b"")

    # ------------------------------------------------------------------
    # P1c: preview endpoint
    # ------------------------------------------------------------------
    def test_preview_resizes_image(self):
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover - Pillow is a hard dependency
            self.skipTest("Pillow not installed")
        buffer = io.BytesIO()
        Image.new("RGB", (1024, 768), (30, 120, 200)).save(buffer, format="PNG")
        self.env["dms.file"].sudo().create({
            "name": "picture.png",
            "directory_id": self.directory.id,
            "content": base64.b64encode(buffer.getvalue()),
        })
        response = self._request("GET", "picture.png?preview=1&w=256")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")
        thumb = Image.open(io.BytesIO(response.content))
        self.assertEqual(thumb.size[0], 256)

    def test_preview_falls_back_for_non_image(self):
        response = self._request("GET", "data.bin?preview=1&w=256")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.payload)

    # ------------------------------------------------------------------
    # P1d: chunked PUT
    # ------------------------------------------------------------------
    def test_chunked_put_assembles_file(self):
        payload = os.urandom(200000)
        first, second = payload[:100000], payload[100000:]
        response = self._request(
            "PUT", "chunked.bin",
            data=first,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Range": "bytes 0-99999/200000",
            },
        )
        self.assertEqual(response.status_code, 202)
        response = self._request(
            "PUT", "chunked.bin",
            data=second,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Range": "bytes 100000-199999/200000",
            },
        )
        self.assertEqual(response.status_code, 201)
        stored = self.env["dms.file"].sudo().search([
            ("name", "=", "chunked.bin"),
            ("directory_id", "=", self.directory.id),
        ], limit=1)
        self.assertTrue(stored)
        self.assertEqual(
            hashlib.sha256(base64.b64decode(stored.content)).hexdigest(),
            hashlib.sha256(payload).hexdigest(),
        )

    def test_chunked_put_rejects_wrong_byte_count(self):
        response = self._request(
            "PUT", "bad.bin",
            data=b"x" * 1000,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Range": "bytes 0-99/2000",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_chunked_put_rejects_malformed_header(self):
        response = self._request(
            "PUT", "bad2.bin",
            data=b"x" * 10,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Range": "nonsense",
            },
        )
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------------
    # P1e: actionable errors
    # ------------------------------------------------------------------
    def test_put_under_storage_explains_mkcol(self):
        response = self._request(
            "PUT", "../../rootfile.bin",
            data=b"x",
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("MKCOL", response.text)

    def test_put_into_missing_parent_names_the_path(self):
        response = self._request(
            "PUT", "NoSuchDir/file.bin",
            data=b"x",
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("NoSuchDir", response.text)

    # ------------------------------------------------------------------
    # Regression: the other verbs still work
    # ------------------------------------------------------------------
    def test_propfind_returns_multistatus(self):
        response = self._request("PROPFIND", "", headers={"Depth": "1"})
        self.assertEqual(response.status_code, 207)
        self.assertIn("multistatus", response.text)

    def test_mkcol_creates_directory(self):
        response = self._request("MKCOL", "newdir")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.env["dms.directory"].sudo().search([
            ("name", "=", "newdir"),
            ("parent_id", "=", self.directory.id),
        ]))

    def test_put_creates_and_updates_file(self):
        response = self._request(
            "PUT", "fresh.bin",
            data=b"hello",
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(response.status_code, 201)
        response = self._request(
            "PUT", "fresh.bin",
            data=b"hello again",
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_removes_file(self):
        self.env["dms.file"].sudo().create({
            "name": "doomed.bin",
            "directory_id": self.directory.id,
            "content": base64.b64encode(b"x"),
        })
        response = self._request("DELETE", "doomed.bin")
        self.assertEqual(response.status_code, 204)

    def test_missing_file_returns_404(self):
        response = self._request("GET", "does-not-exist.bin")
        self.assertEqual(response.status_code, 404)
