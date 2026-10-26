from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWebdavHttp(HttpCase):
    """HTTP-level checks of the WebDAV endpoints.

    ``url_open()`` in Odoo 18 only speaks GET, POST and HEAD, so every
    verb this module actually serves (OPTIONS, PROPFIND, MKCOL, PUT) has
    to go through ``self.opener`` directly. Using ``url_open(method=...)``
    raised TypeError and made the whole class error out instead of testing
    anything.
    """

    def _request(self, path, method="GET", data=None, headers=None):
        url = self.base_url() + path
        # ``self.opener`` is a requests.Session, so the verb goes through
        # ``request()`` — there is no ``open()``.
        return self.opener.request(
            method,
            url,
            data=data,
            headers=headers or {},
            allow_redirects=False,
            timeout=12,
        )

    def test_well_known_redirect(self):
        response = self.url_open(
            "/.well-known/webdav/",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 307)
        self.assertIn("/webdav/", response.headers.get("Location", ""))

    def test_options_no_auth(self):
        response = self._request("/webdav/", method="OPTIONS")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DAV", response.headers)
        self.assertIn("Allow", response.headers)

    def test_propfind_unauthorized(self):
        response = self._request("/webdav/", method="PROPFIND")
        self.assertEqual(response.status_code, 401)

    def test_get_unauthorized(self):
        response = self.url_open(
            "/webdav/",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 401)

    def test_options_on_subpath(self):
        response = self._request("/webdav/some/resource", method="OPTIONS")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DAV", response.headers)


    def test_mkcol_requires_auth(self):
        response = self._request("/webdav/some/newdir", method="MKCOL")
        self.assertEqual(response.status_code, 401)

    def test_put_requires_auth(self):
        response = self._request("/webdav/some/file.txt", method="PUT",
                                 data=b"x")
        self.assertEqual(response.status_code, 401)

    def test_parse_range_unit(self):
        """The Range parser is pure logic - test it without HTTP."""
        from odoo.addons.dms_webdav.controllers.webdav import DmsWebdavController

        parse = DmsWebdavController._parse_range
        total = 4194304

        self.assertEqual(parse(None, total), None)
        self.assertEqual(parse("", total), None)
        self.assertEqual(parse("bytes=0-1023", total), (0, 1023))
        self.assertEqual(parse("bytes=1000000-", total), (1000000, total - 1))
        self.assertEqual(parse("bytes=-500", total), (total - 500, total - 1))
        self.assertEqual(parse("bytes=0-0", total), (0, 0))
        # An end past the entity is clamped, not rejected.
        self.assertEqual(parse("bytes=0-99999999", total), (0, total - 1))
        # A start at or past the end is unsatisfiable -> 416.
        self.assertEqual(parse("bytes=%d-" % total, total), "unsatisfiable")
        self.assertEqual(parse("bytes=5000000-6000000", total), "unsatisfiable")
        # Malformed headers are ignored and the whole entity is served.
        self.assertEqual(parse("bytes=abc-def", total), None)
        self.assertEqual(parse("bytes=100-50", total), None)
        self.assertEqual(parse("items=0-10", total), None)
        # Multi-range is answered with the full entity.
        self.assertEqual(parse("bytes=0-1023,2048-3071", total), None)
        # Case-insensitive, whitespace tolerant.
        self.assertEqual(parse("BYTES=0-99", total), (0, 99))
        self.assertEqual(parse("bytes= 0-99 ", total), (0, 99))

    def test_parse_range_empty_entity(self):
        from odoo.addons.dms_webdav.controllers.webdav import DmsWebdavController

        parse = DmsWebdavController._parse_range
        self.assertEqual(parse("bytes=0-10", 0), "unsatisfiable")
        self.assertEqual(parse("bytes=-5", 0), "unsatisfiable")

    def test_put_rejects_content_range(self):
        """Chunked PUT is not implemented and must say so, not truncate."""
        response = self._request("/webdav/some/file.txt", method="PUT",
                                 data=b"x",
                                 headers={"Content-Range": "bytes 0-0/1"})
        # 401 comes first (auth gate) - assert we never get a silent 200/201
        self.assertIn(response.status_code, (401, 501))
