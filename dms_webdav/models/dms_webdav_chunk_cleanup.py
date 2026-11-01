# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Remove abandoned chunked uploads.

A chunked PUT buffers its chunks in the temp directory until the last one
arrives. If the client dies halfway -- laptop lid closed, network gone,
rclone killed -- those files stay behind forever: nothing else ever looks at
that path again, because the key is derived from user and target path, and
the next upload to the same path starts by overwriting them.

This cron sweeps the directory and deletes anything older than the cutoff.
The window is generous (24h by default) so a genuinely slow upload over a
bad link is not killed mid-flight.
"""

import logging
import os
import tempfile
import time

from odoo import fields, models

_logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_HOURS = 24


class DmsWebdavChunkCleanup(models.AbstractModel):
    _name = "dms.webdav.chunk.cleanup"
    _description = "Remove abandoned WebDAV chunked uploads"

    def _chunk_dir(self):
        """Same directory the controller buffers into.

        Kept in sync with ``WebdavController._chunk_dir`` by hand; the
        controller cannot be imported from here (it pulls in the HTTP stack).
        """
        path = os.path.join(tempfile.gettempdir(), "dms_webdav_chunks")
        os.makedirs(path, exist_ok=True)
        return path

    def _max_age_hours(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dms_webdav.chunk_max_age_hours", DEFAULT_MAX_AGE_HOURS)
        )
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(DEFAULT_MAX_AGE_HOURS)

    def _cron_cleanup_chunks(self):
        """Delete chunk files whose mtime is older than the cutoff.

        Returns the number of removed files so the cron log says something
        useful when it runs.
        """
        directory = self._chunk_dir()
        cutoff = time.time() - self._max_age_hours() * 3600
        removed = 0
        for name in os.listdir(directory):
            candidate = os.path.join(directory, name)
            try:
                if os.path.getmtime(candidate) >= cutoff:
                    continue
                os.unlink(candidate)
                removed += 1
            except FileNotFoundError:
                # Another worker cleaned it between listdir and unlink.
                continue
            except OSError as error:
                _logger.warning(
                    "dms_webdav: could not remove abandoned chunk %s: %s",
                    candidate,
                    error,
                )
        if removed:
            _logger.info(
                "dms_webdav: removed %s abandoned chunk file(s) older than %sh",
                removed,
                self._max_age_hours(),
            )
        return removed
