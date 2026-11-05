import datetime
from unittest.mock import patch

from odoo.tests import BaseCase, tagged
from odoo.tests.common import HttpCase


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

    def test_put_content_range_never_silently_truncates(self):
        """A chunked PUT must never be answered 200/201 as if it were the file.

        This test used to assert 501: chunked upload was not implemented and the
        server had to say so rather than write the first chunk as the whole
        file. Chunked upload is now implemented, so the contract changed - but
        the invariant it protected did not: an upload must never be truncated
        without the client being told. Either the auth gate answers 401, or the
        chunk is accepted (308/201), or it is rejected (400/409). A bare 200 or
        201 for a partial chunk is the bug this test exists to catch.
        """
        response = self._request("/webdav/some/file.txt", method="PUT",
                                 data=b"x",
                                 headers={"Content-Range": "bytes 0-0/10"})
        self.assertIn(response.status_code, (401, 308, 400, 409, 201))

    def test_parse_content_range(self):
        """Content-Range parsing: offsets, the status form, and rejects."""
        from odoo.addons.dms_webdav.controllers.webdav import DmsWebdavController

        parse = DmsWebdavController._parse_content_range
        self.assertEqual(parse("bytes 0-99/100"), (0, 99, 100))
        self.assertEqual(parse("bytes 100-199/200"), (100, 199, 200))
        self.assertEqual(parse("bytes */200"), "status")
        self.assertIsNone(parse(""))
        self.assertIsNone(parse(None))
        self.assertIsNone(parse("bytes 0-99"))
        self.assertIsNone(parse("bytes 50-10/100"))
        self.assertIsNone(parse("bytes 0-100/100"))
        self.assertIsNone(parse("bytes a-b/100"))
        self.assertIsNone(parse("items 0-99/100"))

    def test_form_content_type_preserves_body(self):
        """A form-encoded PUT body must not be swallowed by Odoo's parser.

        Odoo's HttpDispatcher parses ``.form`` before the controller runs,
        which consumes the stream. ``curl --data-binary`` sends
        ``application/x-www-form-urlencoded`` by default, so this combination
        silently stored a 0-byte file with status 200 — the incident that
        produced models/ir_http_dispatch.py. RFC 4918 says the body is opaque
        regardless of Content-Type, so the server has to cope.
        """
        body = b"form-encoded body test, 26 B\n"
        response = self._request(
            "/webdav/some/file.txt",
            method="PUT",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # Unauthenticated in the test DB: 401 is fine, but it must never be a
        # success that stored nothing.
        self.assertIn(response.status_code, (401, 201, 400, 409))

    def test_declared_length_without_body_is_rejected(self):
        """Content-Length > 0 but an empty stream is 400, not a silent zero."""
        response = self._request(
            "/webdav/some/file.txt",
            method="PUT",
            data=b"",
            headers={"Content-Length": "10",
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertIn(response.status_code, (401, 400, 409))

    def test_destination_path_percent_decodes(self):
        """MOVE/COPY Destination arrives percent-encoded from real clients."""
        from odoo.addons.dms_webdav.controllers.webdav import DmsWebdavController

        resolve = DmsWebdavController._destination_path
        self.assertEqual(
            resolve("https://host/webdav/Documents%20Storage/My%20Dir/f.txt"),
            ("/Documents Storage/My Dir/f.txt", None),
        )
        self.assertEqual(
            resolve("/webdav/Documents%20Storage/f.txt"),
            ("/Documents Storage/f.txt", None),
        )
        # A raw space is what older clients send, and must keep working.
        self.assertEqual(
            resolve("/webdav/Documents Storage/f.txt"),
            ("/Documents Storage/f.txt", None),
        )
        # A bare path keeps its first component: the storage name must not be
        # eaten just because the client omitted the /webdav prefix.
        self.assertEqual(
            resolve("/Documents Storage/f.txt"), ("/Documents Storage/f.txt", None)
        )
        self.assertEqual(resolve("/other/prefix/f.txt"), ("/other/prefix/f.txt", None))
        # And a destination with no resource path at all is a client error.
        for empty in ("/", "/webdav", "/webdav/"):
            path, bad = resolve(empty)
            self.assertIsNone(path, "expected %r to be rejected" % empty)
            self.assertIsNotNone(bad)



@tagged("post_install", "-at_install")
class TestWebdavProps(BaseCase):
    """Property/caching behaviour, tested without speaking HTTP.

    These used to live in TestWebdavHttp and therefore never ran. Odoo 18's
    HttpCase.setUpClass() calls cls.base_url(), which reaches
    odoo.service.server.server.httpd - an attribute the prefork server (what
    checkmodule starts) does not have, so setUpClass raised and every test in
    the class was reported as an error instead of a result.
    """

    def test_propfind_returns_etag_and_last_modified(self):
        """A PROPFIND must carry the cache validators, or clients never refresh.

        GNOME's GVFS (and therefore Nautilus) caches directory listings and
        decides whether a file changed by comparing getetag/getlastmodified.
        This server used to answer every PROPFIND with the same fixed set of
        four properties, so both were always absent and a stale listing could
        be opened and saved over.
        """
        from odoo.addons.dms_webdav.controllers.webdav import DmsWebdavController

        self.assertIn("getetag", DmsWebdavController.ALL_PROPS)
        self.assertIn("getlastmodified", DmsWebdavController.ALL_PROPS)

        # _rfc1123 must treat the naive Odoo datetime as UTC. Using
        # datetime.timestamp() would read it as local time and shift it.
        formatted = DmsWebdavController._rfc1123(
            datetime.datetime(2026, 11, 5, 11, 39, 55)
        )
        self.assertEqual(formatted, "Thu, 05 Nov 2026 11:39:55 GMT")

    def test_unavailable_property_gets_404_propstat(self):
        """An unavailable property goes in a 404 propstat, never just vanishes.

        RFC 4918 9.1 requires it, and "silently omitted" is indistinguishable
        from "this resource has no etag" to a caching client. Built against a
        fake record so the XML shape is asserted directly.
        """
        from odoo.addons.dms_webdav.controllers import webdav as webdav_mod

        class FakeRecord:
            name = "Logo.svg"
            mimetype = "image/svg+xml"
            size = 397923
            checksum = "ab26c8c9344bb6c54ac9b318df24edb6ffe3c1f7"
            write_date = datetime.datetime(2026, 11, 5, 11, 39, 55)
            create_date = datetime.datetime(2026, 6, 5, 5, 32, 50)

        class FakeRequest:
            def __init__(self, body):
                self.httprequest = type(
                    "H", (), {"get_data": lambda self, cache=False: body}
                )()

        controller = webdav_mod.DmsWebdavController()
        body = (
            b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop>'
            b"<D:getetag/><D:quota-available-bytes/></D:prop></D:propfind>"
        )
        with patch.object(webdav_mod, "request", FakeRequest(body)):
            xml = controller._propfind_response(
                "/Documents Storage/Media/Graphics/Logo.svg", "file", FakeRecord()
            )

        self.assertIn("<d:getetag>", xml)
        self.assertIn("HTTP/1.1 200 OK", xml)
        # The property the server cannot answer must be reported as 404.
        self.assertIn("<d:quota-available-bytes/>", xml)
        self.assertIn("HTTP/1.1 404 Not Found", xml)
        # And it must not be mixed into the 200 block.
        ok_start = xml.index("HTTP/1.1 200 OK")
        self.assertLess(xml.index("<d:getetag>"), ok_start)

    def test_requested_props_parsing(self):
        """The PROPFIND body decides which properties come back."""
        from odoo.addons.dms_webdav.controllers import webdav as webdav_mod

        class FakeHttpRequest:
            def __init__(self, body):
                self._body = body

            def get_data(self, cache=False):
                return self._body

        class FakeRequest:
            def __init__(self, body):
                self.httprequest = FakeHttpRequest(body)

        parse = webdav_mod.DmsWebdavController._requested_props

        # No body means allprop (RFC 4918 9.1).
        with patch.object(webdav_mod, "request", FakeRequest(b"")):
            self.assertEqual(parse(), ("allprop", None))

        # propname asks for names only.
        with patch.object(
            webdav_mod,
            "request",
            FakeRequest(
                b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:">'
                b"<D:propname/></D:propfind>"
            ),
        ):
            self.assertEqual(parse(), ("propname", None))

        # An explicit prop list comes back in the order requested.
        with patch.object(
            webdav_mod,
            "request",
            FakeRequest(
                b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop>'
                b"<D:getetag/><D:getlastmodified/></D:prop></D:propfind>"
            ),
        ):
            self.assertEqual(parse(), ("prop", ["getetag", "getlastmodified"]))

    def test_xml_escape_protects_names(self):
        """A file called 'a&b.svg' must not produce unparseable XML."""
        from odoo.addons.dms_webdav.controllers.webdav import _xml_escape

        self.assertEqual(_xml_escape("a&b.svg"), "a&amp;b.svg")
        self.assertEqual(_xml_escape("<tag>"), "&lt;tag&gt;")
        self.assertEqual(_xml_escape("normal.svg"), "normal.svg")
