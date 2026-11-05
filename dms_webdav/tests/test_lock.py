# -*- coding: utf-8 -*-
"""Tests for WebDAV locking (change webdav-lock-sync).

Two layers, deliberately separated:

  * the pure functions -- `lock_token`, `_if_tokens`, `_lock_refusal` -- which
    need no server and are where the rules live;
  * the HTTP-level refusals, which need a real server and are covered by the
    live verification in the change's tasks rather than here.

The HTTP layer is not duplicated as `HttpCase` because `--single-mode` skips
those classes silently (learned 2026-11-05), so a test that only runs in a
full-server run is a test nobody runs.
"""

from unittest import mock

from odoo.tests import BaseCase, tagged


@tagged("post_install", "-at_install")
class TestLockRules(BaseCase):
    """The lock rules, without a request."""


    def _fake_request(self, headers=None, user_id=1):
        """Patch the module's `request` for one call.

        `request` is a werkzeug LocalProxy, and `unittest.mock.patch` cannot
        patch it directly -- `hasattr()` on the proxy raises "object is not
        bound" outside a request. Patching the MODULE attribute replaces the
        name the controller reads, which is what the test needs.
        """
        from odoo.addons.dms_webdav.controllers import webdav as webdav_module

        fake = mock.MagicMock()
        fake.httprequest.headers = headers if headers is not None else {}
        fake.env.user.id = user_id
        # `make_response` must return something whose `status_code` the test
        # can read. A bare MagicMock gives another MagicMock, and
        # `assertEqual(mock, 423)` fails with a useless message.
        def _response(body=None, status=200, headers=None, **kwargs):
            made = mock.MagicMock()
            made.status_code = status
            made.body = body
            return made

        fake.make_response.side_effect = _response
        return mock.patch.object(webdav_module, "request", fake)

    def _controller(self):
        from odoo.addons.dms_webdav.controllers.webdav import DmsWebdavController

        return DmsWebdavController

    # ------------------------------------------------------------------
    # The token format has one source
    # ------------------------------------------------------------------

    def test_lock_token_is_the_holder_id(self):
        """`LOCK`, `lockdiscovery` and the `If:` check must agree."""
        controller = self._controller()
        self.assertEqual(controller.lock_token(7), "opaquelocktoken:7")

    # ------------------------------------------------------------------
    # If: header parsing
    # ------------------------------------------------------------------

    def test_if_tokens_extracts_angle_brackets(self):
        controller = self._controller()
        with self._fake_request({"If": "(<opaquelocktoken:7>)"}):
            self.assertEqual(controller._if_tokens(), {"opaquelocktoken:7"})

    def test_if_tokens_empty_header(self):
        controller = self._controller()
        with self._fake_request({}):
            self.assertEqual(controller._if_tokens(), set())

    def test_if_tokens_unparseable_fails_closed(self):
        """A header we cannot read must not become a permission."""
        controller = self._controller()
        with self._fake_request({"If": "garbage"}):
            self.assertEqual(controller._if_tokens(), set())

    # ------------------------------------------------------------------
    # The refusal rule
    # ------------------------------------------------------------------

    def _refusal(self, locked_by_id, requester_id, if_header=None):
        """Run `_lock_refusal` against a stand-in record and request."""
        controller = self._controller()

        class Holder:
            def __init__(self, ident):
                self.id = ident
                self.name = "user %s" % ident

        class Record:
            locked_by = Holder(locked_by_id) if locked_by_id else None

        headers = {"If": if_header} if if_header else {}
        with self._fake_request(headers, requester_id):
            return controller._lock_refusal(controller, Record())

    def test_unlocked_file_is_writable(self):
        self.assertIsNone(self._refusal(None, 1))

    def test_holder_may_write_without_a_token(self):
        """D5: a desktop client does not reliably send `If:` on first save."""
        self.assertIsNone(self._refusal(7, 7))

    def test_other_user_is_refused(self):
        response = self._refusal(7, 9)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 423)

    def test_other_user_with_foreign_token_is_refused(self):
        response = self._refusal(7, 9, if_header="(<opaquelocktoken:9>)")
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 423)

    def test_other_user_with_matching_token_is_allowed(self):
        """RFC 4918 10.4.1: presenting the lock's token is the way through."""
        self.assertIsNone(
            self._refusal(7, 9, if_header="(<opaquelocktoken:7>)")
        )
