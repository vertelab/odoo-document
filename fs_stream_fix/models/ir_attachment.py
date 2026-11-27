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
        sådan fil. Vi bygger i stället en `data`-stream från `raw`, som
        `fs_attachment` redan läser via `_file_read()` mot S3.
        """
        self.ensure_one()

        if not self.store_fname:
            return super()._to_http_stream()

        # Bara om store_fname pekar på en konfigurerad fs.storage.
        # Annars är det en vanlig lokal filestore och originalmetoden
        # fungerar som den ska.
        if not self._is_file_from_a_storage(self.store_fname):
            return super()._to_http_stream()

        try:
            data = self.raw
        except Exception:  # noqa: BLE001 — fall tillbaka på original
            _logger.warning(
                "Kunde inte läsa bilaga %s från objektlagring, "
                "faller tillbaka på lokal filestore",
                self.id,
                exc_info=True,
            )
            return super()._to_http_stream()

        if data is None:
            return super()._to_http_stream()

        stream = super()._to_http_stream()
        stream.type = 'data'
        stream.data = data
        stream.size = len(data)
        stream.last_modified = self.write_date
        # path ska inte användas när type='data'
        stream.path = None
        return stream
