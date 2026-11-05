# -*- coding: utf-8 -*-
"""Tests for the LibreOffice lock-file convention (change webdav-dotfile-locks).

The name rule and the holder parse are pure functions; they carry the whole
risk of over-matching, so they are tested exhaustively here rather than
through HTTP.
"""

from odoo.tests import BaseCase, tagged


@tagged("post_install", "-at_install")
class TestDotfileLocks(BaseCase):
    def _helpers(self):
        from odoo.addons.dms_webdav.controllers import webdav

        return webdav

    # ------------------------------------------------------------------
    # The name rule
    # ------------------------------------------------------------------

    def test_lock_file_is_recognised(self):
        webdav = self._helpers()
        self.assertTrue(webdav._is_lock_file(".~lock.Budget.docx#"))
        self.assertTrue(webdav._is_lock_file(".~lock.a#"))

    def test_ordinary_dotfile_is_not_a_lock(self):
        webdav = self._helpers()
        self.assertFalse(webdav._is_lock_file(".hidden"))
        self.assertFalse(webdav._is_lock_file(".notes.txt"))

    def test_document_named_lock_is_not_a_lock(self):
        """A document may be called `lock-report.docx`."""
        webdav = self._helpers()
        self.assertFalse(webdav._is_lock_file("lock-report.docx"))

    def test_lock_prefix_without_hash_is_not_a_lock(self):
        webdav = self._helpers()
        self.assertFalse(webdav._is_lock_file(".~lock.Budget.docx"))

    def test_backup_conventions_are_not_locks(self):
        """GIMP writes `.foo.xcf~`, Inkscape `.foo.svg.` -- backups, not locks."""
        webdav = self._helpers()
        self.assertFalse(webdav._is_lock_file(".foo.xcf~"))
        self.assertFalse(webdav._is_lock_file(".foo.svg."))

    def test_empty_and_none(self):
        webdav = self._helpers()
        self.assertFalse(webdav._is_lock_file(""))
        self.assertFalse(webdav._is_lock_file(None))

    # ------------------------------------------------------------------
    # The document a lock file names
    # ------------------------------------------------------------------

    def test_locked_document_name(self):
        webdav = self._helpers()
        self.assertEqual(
            webdav._locked_document_name(".~lock.Budget.docx#"), "Budget.docx"
        )

    def test_locked_document_name_on_non_lock(self):
        webdav = self._helpers()
        self.assertIsNone(webdav._locked_document_name("Budget.docx"))

    # ------------------------------------------------------------------
    # The holder
    # ------------------------------------------------------------------

    def test_holder_parsed(self):
        webdav = self._helpers()
        line = b"Anna Andersson,aandersson,laptop,2026-11-05T15:00:00\n"
        self.assertEqual(
            webdav._lock_holder(line), ("Anna Andersson", "aandersson")
        )

    def test_holder_unknown_on_empty(self):
        webdav = self._helpers()
        self.assertEqual(webdav._lock_holder(b""), (None, None))
        self.assertEqual(webdav._lock_holder(None), (None, None))

    def test_holder_unknown_on_truncated(self):
        """A partial line must not become a guess."""
        webdav = self._helpers()
        self.assertEqual(webdav._lock_holder(b"onlyaname"), (None, None))

    def test_holder_tolerates_missing_name(self):
        webdav = self._helpers()
        self.assertEqual(
            webdav._lock_holder(b",aandersson,host,ts"), (None, "aandersson")
        )
