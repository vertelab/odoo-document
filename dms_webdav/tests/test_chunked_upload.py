# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Chunk buffering, assembly and cleanup.

These exercise the controller's chunk helpers directly rather than over
HTTP. The helpers are where the correctness lives -- ordering, the total
size, the completeness test -- and driving them straight keeps the tests
fast and free of auth setup. The HTTP contract (308/201/409) is covered by
``test_webdav_http``.

``_chunk_dir`` is redirected to a per-test temporary directory so the tests
never touch the real buffer, and so they cannot collide with a genuine
upload running on the same machine.
"""

import os
import shutil
import tempfile
import time
from unittest import mock

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.dms_webdav.controllers.webdav import DmsWebdavController


@tagged("post_install", "-at_install")
class TestChunkedUpload(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DmsWebdavController()
        cls.user_id = cls.env.uid
        cls._original_chunk_dir = DmsWebdavController._chunk_dir

    def setUp(self):
        super().setUp()
        self._tmpdir = tempfile.mkdtemp(prefix="dms_chunk_test_")
        DmsWebdavController._chunk_dir = lambda _self: self._tmpdir
        # The cron model resolves the directory itself (it cannot import the
        # controller), so it needs the same redirection or it would sweep the
        # real buffer instead of the test's. Odoo 18 rejects assigning
        # attributes on a model class, so the patch goes through the registry
        # class rather than the recordset.
        cleanup_class = type(self.env["dms.webdav.chunk.cleanup"])
        self._cleanup_patch = mock.patch.object(
            cleanup_class, "_chunk_dir", lambda _self: self._tmpdir
        )
        self._cleanup_patch.start()

    def tearDown(self):
        DmsWebdavController._chunk_dir = self._original_chunk_dir
        self._cleanup_patch.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().tearDown()

    def _feed(self, path, chunks, total):
        """Append every chunk in order; return the final completeness flag."""
        complete = False
        for start, payload in chunks:
            complete = self.controller._append_chunk(
                path, start, payload, total, user_id=self.user_id
            )
        return complete

    def test_three_chunks_assemble_to_the_whole_file(self):
        """Task 5.2: three chunks produce one file with all the bytes."""
        path = "/webdav/big.bin"
        payload = b"a" * 10 + b"b" * 10 + b"c" * 10
        chunks = [(0, b"a" * 10), (10, b"b" * 10), (20, b"c" * 10)]
        self.assertTrue(self._feed(path, chunks, len(payload)))
        self.assertEqual(self.controller._assemble_chunks(path, user_id=self.user_id), payload)

    def test_interrupted_upload_leaves_no_trace_after_cleanup(self):
        """Task 5.3/5.4: an abandoned upload is removable and never assembled.

        The invariant: until the last chunk arrives, nothing is written to
        dms.file. The buffer is the only trace, and cleanup removes it.
        """
        path = "/webdav/interrupted.bin"
        self.assertFalse(self._feed(path, [(0, b"a" * 10)], 30))
        self.assertTrue(os.path.exists(self.controller._chunk_path(path, user_id=self.user_id)))
        self.controller._cleanup_chunks(path, user_id=self.user_id)
        self.assertFalse(os.path.exists(self.controller._chunk_path(path, user_id=self.user_id)))
        self.assertFalse(os.path.exists(self.controller._upload_id_path(path, user_id=self.user_id)))

    def test_out_of_order_chunk_is_refused(self):
        """Task 5.5: a chunk at the wrong offset raises instead of corrupting."""
        path = "/webdav/ordered.bin"
        self._feed(path, [(0, b"a" * 10)], 30)
        with self.assertRaises(ValueError):
            self.controller._append_chunk(
                path, 20, b"c" * 10, 30, user_id=self.user_id
            )

    def test_changed_total_is_refused(self):
        """Task 5.5: a different total mid-upload is a conflict, not a merge."""
        path = "/webdav/total.bin"
        self._feed(path, [(0, b"a" * 10)], 30)
        with self.assertRaises(ValueError):
            self.controller._append_chunk(
                path, 10, b"b" * 10, 99, user_id=self.user_id
            )

    def test_chunks_are_per_user_and_path(self):
        """Task 5.6: two targets never share a buffer.

        This is what makes a second client answer 409 rather than silently
        appending to someone else's upload.
        """
        first = self.controller._chunk_path("/webdav/one.bin", user_id=self.user_id)
        second = self.controller._chunk_path("/webdav/two.bin", user_id=self.user_id)
        self.assertNotEqual(first, second)

    def test_cron_removes_only_abandoned_chunks(self):
        """Task 5.7: the sweep deletes stale files and keeps fresh ones."""
        stale_path = "/webdav/stale.bin"
        fresh_path = "/webdav/fresh.bin"
        self._feed(stale_path, [(0, b"a" * 10)], 30)
        self._feed(fresh_path, [(0, b"b" * 10)], 30)
        stale_chunk = self.controller._chunk_path(stale_path, user_id=self.user_id)
        stale_meta = self.controller._upload_id_path(stale_path, user_id=self.user_id)
        # Backdate both files of the abandoned upload by two days.
        old = time.time() - 48 * 3600
        os.utime(stale_chunk, (old, old))
        os.utime(stale_meta, (old, old))

        removed = self.env["dms.webdav.chunk.cleanup"]._cron_cleanup_chunks()
        self.assertGreaterEqual(removed, 2)
        self.assertFalse(os.path.exists(stale_chunk))
        self.assertFalse(os.path.exists(stale_meta))
        self.assertTrue(os.path.exists(self.controller._chunk_path(fresh_path, user_id=self.user_id)))
