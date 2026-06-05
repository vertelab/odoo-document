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
