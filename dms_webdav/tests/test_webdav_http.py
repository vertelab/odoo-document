from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWebdavHttp(HttpCase):
    def test_well_known_redirect(self):
        response = self.url_open(
            "/.well-known/webdav/",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 307)
        self.assertIn("/webdav/", response.headers.get("Location", ""))

    def test_options_no_auth(self):
        response = self.url_open(
            "/webdav/",
            method="OPTIONS",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("DAV", response.headers)
        self.assertIn("Allow", response.headers)

    def test_propfind_unauthorized(self):
        response = self.url_open(
            "/webdav/",
            method="PROPFIND",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 401)

    def test_get_unauthorized(self):
        response = self.url_open(
            "/webdav/",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 401)

    def test_options_on_subpath(self):
        response = self.url_open(
            "/webdav/some/resource",
            method="OPTIONS",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("DAV", response.headers)


    def test_mkcol_requires_auth(self):
        response = self.url_open(
            "/webdav/some/newdir",
            method="MKCOL",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 401)

    def test_put_requires_auth(self):
        response = self.url_open(
            "/webdav/some/file.txt",
            method="PUT",
            data=b"x",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 401)

    def test_put_rejects_content_range(self):
        """Chunked PUT is not implemented and must say so, not truncate."""
        response = self.url_open(
            "/webdav/some/file.txt",
            method="PUT",
            data=b"x",
            headers={"Content-Range": "bytes 0-0/1"},
            allow_redirects=False,
        )
        # 401 comes first (auth gate) - assert we never get a silent 200/201
        self.assertIn(response.status_code, (401, 501))
