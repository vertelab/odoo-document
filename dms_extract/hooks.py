# -*- coding: utf-8 -*-
"""post_init_hook — verifiera systemberoendena och köa arkivet.

VARFÖR INSTALLATIONEN SKA VÄGRA: OCR är en utlovad förmåga. Saknas
Tesseract blir modulen en tyst textyta-bara-läge, och en skannad PDF ser ut
att vara "tom" i stället för att vara "oläsbar". Det är värre än att inte
installera: användaren får inget fel, bara en sökning som inte hittar.

VARFÖR PyMuPDF OCKSÅ: utan den kan vi inte läsa PDF alls — den vanligaste
dokumenttypen i en DMS.
"""

import logging
import shutil

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _missing_packages():
    """Vilka systemberoenden saknas? Returnerar lista med namn."""
    missing = []

    try:
        import fitz  # noqa: F401  PyMuPDF
    except ImportError:
        missing.append('python3-pymupdf (PyMuPDF, import `fitz`)')

    if not shutil.which('tesseract'):
        missing.append('tesseract-ocr (binären `tesseract`)')
    else:
        # Språkdata: swe+eng krävs av _ocr_pdf. Utan dem kastar Tesseract
        # vid körning — men bara på skannade filer, vilket är precis den
        # typ av fel som upptäcks först när någon faktiskt behöver det.
        try:
            import subprocess
            langs = subprocess.run(
                ['tesseract', '--list-langs'],
                capture_output=True, text=True, timeout=10, check=False)
            available = set((langs.stdout or '').split())
            for needed in ('swe', 'eng'):
                if needed not in available:
                    missing.append(
                        'tesseract-ocr-%s (språkdata saknas)' % needed)
        except Exception as error:  # noqa: BLE001
            _logger.warning(
                'dms_extract: kunde inte läsa Tesseracts språklista: %s', error)

    return missing


def post_init_hook(env):
    """Körs när modulen installeras."""
    missing = _missing_packages()
    if missing:
        raise RuntimeError(
            'dms_extract kan inte installeras — systemberoenden saknas:\n  - '
            + '\n  - '.join(missing)
            + '\n\nInstallera dem och försök igen:\n'
            '  apt-get install python3-pymupdf tesseract-ocr '
            'tesseract-ocr-swe tesseract-ocr-eng')

    _queue_existing_files(env)


def _queue_existing_files(env):
    """Sätt `pending` på varje fil som har innehåll. Idempotent.

    Körs även om modulen installeras om — därför räknar vi och skriver bara
    de filer som inte redan står i kön. Att skriva alla varje gång hade
    nollställt `extract_hash` och tvingat en full omutvinning av ett arkiv
    som redan var färdigt.
    """
    files = env['dms.file'].with_context(active_test=False).search([
        ('extract_state', 'not in', ('pending', 'done')),
    ])
    if files:
        files.write({'extract_state': 'pending', 'extract_error': False})
    # Rapportera HELA kön, inte bara de vi nyss skrev. Vid förstagångs-
    # installation får varje fil `pending` av fältets default, så den här
    # raden skriver noll — och en logg som säger "0 köade" medan 238 filer
    # väntar är en logg som ljuger.
    queued = env['dms.file'].with_context(active_test=False).search_count([
        ('extract_state', '=', 'pending'),
    ])
    _logger.info(
        'dms_extract: %s fil(er) i kön för textutvinning (%s nyskrivna)',
        queued, len(files))
    return queued
