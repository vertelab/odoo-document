# -*- coding: utf-8 -*-
"""Leverera bilagor från objektlagring via HTTP.

Se __manifest__.py för bakgrund. Kort: `fs_attachment` patchar läsning
men inte `_to_http_stream()`, så Odoo försöker `os.stat()` på en lokal
sökväg som inte finns när lagringen är S3.
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _to_http_stream(self):
        """Returnera en data-stream för bilagor som ligger i objektlagring.

        Odoos original gör `os.stat()` på en lokal fil. Med S3 finns ingen
        sådan fil. Vi bygger streamen själva i stället för att anropa
        super(), eftersom super() kraschar innan vi hinner ersätta den.
        """
        self.ensure_one()

        if not self.store_fname:
            return super()._to_http_stream()

        if not self._is_file_from_a_storage(self.store_fname):
            return super()._to_http_stream()

        try:
            data = self.raw
        except Exception as exc:
            _logger.warning(
                "fs_stream_fix: FEL vid läsning av %s: %s", self.id, exc, exc_info=True
            )
            return super()._to_http_stream()

        if not data:
            _logger.warning(
                "fs_stream_fix: TOM DATA för %s (store_fname=%s, file_size=%s)",
                self.id, self.store_fname, self.file_size,
            )
            return super()._to_http_stream()

        # Bygg streamen själva — anropa INTE super(), den gör os.stat()
        # på en lokal sökväg som inte finns.
        from odoo.http import Stream
        from werkzeug.wrappers import Response

        stream = Stream(
            mimetype=self.mimetype or 'application/octet-stream',
            download_name=self.name,
            etag=self.checksum,
            public=self.public,
        )
        stream.type = 'data'
        stream.data = data
        stream.size = len(data)
        stream.last_modified = self.write_date
        stream.path = None
        _logger.info(
            "fs_stream_fix: data-stream %s bytes för %s", len(data), self.id
        )
        return stream
