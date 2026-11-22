# -*- coding: utf-8 -*-
"""dms.file — textutvinning till OKF-kroppen (dms-content-extraction).

VARFÖR: `dms_ai` gör varje `dms.file` till ett OKF-koncept, men kroppen är
filnamnet, mappen och taggarna — inte filen. Den som laddar upp
`Avtal-2026.pdf` kan söka `avtal` och inget annat. De 2 400 orden inuti syns
inte för någon av de två signaler sökningen använder (svensk BM25 över
`summary || title`, och `embedding <=> query`), eftersom ingen av dem någonsin
ser byten.

DEN HÄR MODULEN MATAR SÖKNINGEN. Den ändrar den inte.

KONTRAKTET MOT `dms_ai` (D7): modellen svarar, mixinen läser. Vi skriver
därför ALDRIG `okf_body` direkt — det skulle kringgå `_okf_build_summary`, och
då skulle sammanfattningen beskriva filnamnet medan kroppen beskrev
dokumentet. Vi överrider `_okf_body_source()` och hissar `okf_dirty`.
"""

import base64
import hashlib
import io
import logging
import re

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Mimetypes vi kan läsa. Ordningen spelar roll: PDF först (vanligast),
# sedan zip-baserade OOXML/ODF, sedan ren text.
ZIP_MIMETYPES = {
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/vnd.oasis.opendocument.text': 'odt',
    'application/vnd.oasis.opendocument.spreadsheet': 'ods',
    'application/vnd.oasis.opendocument.presentation': 'odp',
}

TEXT_MIMETYPES = {
    'text/plain', 'text/csv', 'text/markdown', 'application/json',
    'application/xml', 'text/xml',
}

HTML_MIMETYPES = {'text/html', 'application/xhtml+xml'}

# E-post: .eml är ren text med headers; vi tar kroppen, inte headern.
EMAIL_MIMETYPES = {'message/rfc822'}

# Binära typer som inte bär text. Zip-baserade dokument hanteras av
# ZIP_MIMETYPES ovan och når aldrig hit.
BINARY_MIMETYPES = {
    'application/octet-stream',
    'application/zip', 'application/gzip', 'application/x-tar',
    'application/x-7z-compressed', 'application/x-rar-compressed',
    'application/x-bzip2', 'application/x-xz',
    'application/x-executable', 'application/x-sharedlib',
    'application/x-object', 'application/x-archive',
    # OLE2-format (Word 97-2003, Excel 97-2003, PowerPoint 97-2003).
    # FYND (2026-11-01): .xls gav 15 521 tecken "text" som började med
    # "ÐÏà¡±á>þÿ" — OLE2-headern avkodad som latin-1. Att läsa dem kräver
    # olefile/antiword; tills dess är tom text det ärliga svaret.
    'application/msword',
    'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
}


class DmsFile(models.Model):
    _inherit = 'dms.file'

    # ── Utvinningsstatus (D3) ──────────────────────────────────────────
    #
    # Varför hash och inte `write_date > extract_date`: `checksum` finns
    # redan på dms.file och är vad dubblettmodulen använder. `write_date`
    # flyttar på sig vid VARJE fältändring — en taggbyta hade kört om
    # utvinningen på en 100 MB PDF helt i onödan.

    extract_hash = fields.Char(
        'Extracted hash', readonly=True, copy=False,
        help='Hash av innehållet vid senaste lyckade utvinning. Samma '
             'algoritm som `checksum` (sha1) sa att de kan jamforas.')

    extract_state = fields.Selection(
        [('pending', 'Pending'),
         ('done', 'Done'),
         ('skipped', 'Skipped'),
         ('failed', 'Failed')],
        'Extraction', default='pending', readonly=True, copy=False,
        index=True,
        help='pending: väntar på kön. done: text utvunnen. '
             'skipped: mappen är undantagen. failed: fel, se extract_error.')

    extract_date = fields.Datetime(
        'Extracted on', readonly=True, copy=False)

    extract_error = fields.Text(
        'Extraction error', readonly=True, copy=False,
        help='Varför utvinningen misslyckades. Terminalt tills filens '
             'innehåll ändras.')

    extracted_chars = fields.Integer(
        'Extracted characters', readonly=True, copy=False, default=0,
        help='Längden på den LAGRADE texten (0 = ingen textyta).')

    _extracted_text = fields.Text(
        'Extracted text', copy=False,
        help='Texten som utvunnits ur filens innehåll. Ingår i OKF-kroppen '
             'via _okf_body_source().')

    # ── EXIF (dms-content-extraction 5b) ───────────────────────────────
    #
    # VARFÖR FÄLT OCH INTE TAGGAR: en tagg är en klassificering någon kan
    # välja. EXIF är mätvärden en kamera skrev. Att göra DateTimeOriginal
    # till en tagg ger en tagg per sekund — 100 000 foton blir 100 000
    # taggar, varav de flesta används en gång. Och GPS som tagg
    # ("57.7089,11.9746") kan inte svara på "inom 500 meter".
    #
    # VARFÖR exif_raw: en kamera skriver upp till hundra fält. Vi indexerar
    # de sex vi frågar på och dumpar resten — att modellera alla vore att
    # göra Odoos schema till en EXIF-ordbok.

    exif_datetime_original = fields.Datetime(
        'Taken at', readonly=True, copy=False,
        help='EXIF DateTimeOriginal — när bilden togs, inte när den '
             'laddades upp.')

    exif_make = fields.Char(
        'Camera make', readonly=True, copy=False, index=True)

    exif_model = fields.Char(
        'Camera model', readonly=True, copy=False, index=True)

    exif_orientation = fields.Integer(
        'Orientation', readonly=True, copy=False,
        help='EXIF Orientation (1-8). En bild med orientation 6 är tagen '
             'roterad och visas fel utan korrigering.')

    exif_gps_lat = fields.Float(
        'GPS latitude', readonly=True, copy=False, digits=(10, 7),
        help='Breddgrad. PERSONUPPGIFT: en bild tagen hemma bär någons '
             'hemadress. Ingår ALDRIG i okf_body — se docs/gdpr.md.')

    exif_gps_lon = fields.Float(
        'GPS longitude', readonly=True, copy=False, digits=(10, 7),
        help='Längdgrad. PERSONUPPGIFT — se exif_gps_lat.')

    exif_raw = fields.Json(
        'EXIF (raw)', readonly=True, copy=False,
        help='Hela EXIF-blocket som det lästes. Indexera det ni frågar på; '
             'resten ligger här för spårbarhet.')

    # ── Kön (D2) ───────────────────────────────────────────────────────

    @api.model
    def _cron_extract_pending(self):
        """Kör utvinning på kön. Anropas av cron.task, aldrig av en request.

        Urvalet är `pending`/`failed` PLUS filer vars `checksum` skiljer sig
        från `extract_hash` — det sistnämnda fångar en skrivning som inte
        satte `pending` (t.ex. en återställd version innan dms_version lär
        sig flagga).
        """
        batch_size = int(self.env['ir.config_parameter'].sudo().get_param(
            'dms_extract.batch_size', '20') or 20)
        files = self._extract_candidates(limit=batch_size)
        if not files:
            return 0
        done = 0
        for record in files:
            try:
                record._extract_one()
                done += 1
            except Exception as error:  # noqa: BLE001 — en fil får inte stoppa kön
                _logger.warning(
                    'dms_extract: %s (#%s) misslyckades: %s',
                    record.name, record.id, error)
                record.write({
                    'extract_state': 'failed',
                    'extract_error': str(error)[:2000],
                    'extract_date': fields.Datetime.now(),
                })
        _logger.info('dms_extract: %s fil(er) behandlade', done)
        return done

    @api.model
    def _extract_candidates(self, limit=20):
        """Vilka filer kön ska ta. Aldrig fler än `limit`.

        SORTERINGEN ÄR INTE KOSMETISK. FYND (2026-11-01): med `search(domain,
        limit=limit*3)` och defaultordning (id) returnerade varje tick samma
        första 60 rader — som efter första körningen var `done`. De `pending`
        filerna med högre id låg utanför fönstret och nåddes ALDRIG: 83 filer
        stod kvar som `pending` i evighet medan kön rapporterade "tom".
        En kö som svälter är värre än en långsam kö, för den ser ut att vara
        klar.

        Ordningen är därför: aldrig försökta först (`extract_date` NULL),
        sedan äldst försök först. Det ger FIFO över hela arkivet i stället
        för FIFO över ett fönster.
        """
        domain = [
            '|', '|',
            ('extract_state', '=', 'pending'),
            ('extract_state', '=', 'failed'),
            '&', ('extract_state', '=', 'done'),
            ('extract_hash', '!=', False),
        ]
        result = self.browse()
        # Hämta i omgångar tills vi har `limit` eller tömmer urvalet.
        offset = 0
        page = max(limit * 5, 100)
        while len(result) < limit:
            candidates = self.search(
                domain, limit=page, offset=offset,
                order='extract_date asc nulls first, id asc')
            if not candidates:
                break
            for record in candidates:
                if len(result) >= limit:
                    break
                if record._extract_needs_work():
                    result |= record
            offset += page
        return result

    def _extract_needs_work(self):
        """Behöver den här filen utvinnas?

        `failed` är terminalt tills innehållet ändras — annars skulle en
        trasig PDF köras om var femte minut för alltid.

        FYND (2026-11-01): 192 av 238 filer saknade blob på disk (filestore
        hade rensats) och blev därför `pending` för alltid — kön tog dem
        aldrig, men de låg kvar och skymde kön. En fil utan innehåll ska
        markeras `skipped` EN gång, inte vänta för evigt.
        """
        self.ensure_one()
        if not self.content:
            return True   # låt _extract_one sätta `skipped`
        if not self.directory_id.extract_enabled:
            # FYND (2026-11-01): här stod `return False`, vilket gjorde att
            # filen ALDRIG blev `skipped` — den låg kvar som `pending` och
            # kön tog den aldrig. Spec:en säger att en fil i en undantagen
            # mapp SKA få `skipped`. Vi låter därför _extract_one sätta det.
            return True
        if self.extract_state == 'failed':
            # Bara om hashen faktiskt ändrats sedan försöket.
            return bool(self.checksum) and self.checksum != self.extract_hash
        if self.extract_state == 'pending':
            return True
        return bool(self.checksum) and self.checksum != self.extract_hash

    # ── Utvinningen ────────────────────────────────────────────────────

    def _extract_one(self):
        """Utvinn text ur EN fil och skriv resultatet."""
        self.ensure_one()

        if not self.directory_id.extract_enabled:
            self.write({
                'extract_state': 'skipped',
                'extract_date': fields.Datetime.now(),
                'extract_error': False,
            })
            return

        raw = base64.b64decode(self.content or b'')
        if not raw:
            self.write({
                'extract_state': 'skipped',
                'extract_date': fields.Datetime.now(),
                'extract_error': False,
            })
            return

        text = self._extract_text(raw, self.mimetype or '')

        # Sista spärren: alla format går genom _sanitize, även de som
        # inte använder _clean (PDF-texten kommer direkt från PyMuPDF).
        text = self._sanitize(text)

        # EXIF (5b). Bara för bilder, och bara om katalogen tillåter det —
        # spärren är densamma som för text: en katalog som inte får
        # indexeras får inte heller berikas.
        exif_vals, exif_text = self._extract_exif(raw, self.mimetype or '')
        if exif_text:
            text = (exif_text + '\n' + text).strip() if text else exif_text

        max_chars = int(self.env['ir.config_parameter'].sudo().get_param(
            'dms_extract.max_chars', '200000') or 200000)
        if len(text) > max_chars:
            text = text[:max_chars]

        # SAMMA ALGORITM SOM `checksum` — annars kan de aldrig matcha.
        # FYND (2026-11-01): jag hasha(de) med sha256 medan OCA:s `checksum`
        # är sha1. Varje fil blev därför "ändrad" vid varje tick och kön
        # körde om 238 filer i oändlighet (14 120 behandlingar innan jag
        # stoppade den). Hashen är en jämförelsenyckel, inte en signatur —
        # algoritmen ska vara den som redan finns på fältet.
        content_hash = hashlib.sha1(raw).hexdigest()
        changed = (text or '') != (self._extracted_text or '')

        vals = {
            'extract_state': 'done',
            'extract_hash': content_hash,
            'extract_date': fields.Datetime.now(),
            'extract_error': False,
            'extracted_chars': len(text),
            '_extracted_text': text,
        }
        vals.update(exif_vals)
        # Hissa flaggan BARA när texten faktiskt ändrats — annars väcker
        # varje omkörning mixinens indexeringscron i onödan.
        if changed:
            vals['okf_dirty'] = True
        self.write(vals)

    def _extract_text(self, raw, mimetype):
        """Dispatcha på mimetype. Returnerar text (kan vara tom)."""
        self.ensure_one()
        mimetype = (mimetype or '').split(';')[0].strip().lower()

        try:
            if mimetype == 'application/pdf' or mimetype.endswith('/pdf'):
                return self._extract_pdf(raw)
            if mimetype in ZIP_MIMETYPES:
                return self._extract_zip(raw, ZIP_MIMETYPES[mimetype])
            if mimetype in HTML_MIMETYPES:
                return self._extract_html(raw)
            if mimetype in EMAIL_MIMETYPES:
                return self._extract_email(raw)
            if mimetype in TEXT_MIMETYPES or mimetype.startswith('text/'):
                return self._decode(raw)
        except Exception as error:  # noqa: BLE001
            _logger.info('dms_extract: %s kunde inte läsas som %s: %s',
                         self.name, mimetype, error)
            raise

        # ICKE-TEXT: bilder, ljud, video, arkiv, körbara filer.
        # FYND (2026-11-01): utan den här grinden blev en JPEG 145 003 tecken
        # "text" — latin-1-avkodad binärdata som ser ut som en sidfot i en
        # sökträff. Det är precis den skräpindexering spec:en förbjuder, och
        # det är värre än ingen text: träffen ser ut som en träff.
        if self._is_binary_type(mimetype):
            return ''

        # Okänd typ som inte är uppenbart binär: försök som text. Bättre en
        # tom body än en kraschad kö.
        return self._decode(raw)

    # ── Format ─────────────────────────────────────────────────────────

    def _extract_pdf(self, raw):
        """PDF via PyMuPDF, med OCR bara när textytan saknas (D4)."""
        try:
            import fitz  # PyMuPDF
        except ImportError as error:
            raise UserError(
                'PyMuPDF saknas — dms_extract kan inte läsa PDF. '
                'Installera python3-pymupdf.') from error

        parts = []
        with fitz.open(stream=raw, filetype='pdf') as doc:
            for page in doc:
                parts.append(page.get_text() or '')
        text = '\n'.join(parts).strip()

        threshold = int(self.env['ir.config_parameter'].sudo().get_param(
            'dms_extract.ocr_threshold', '100') or 100)
        if len(text) < threshold:
            ocr = self._ocr_pdf(raw)
            if len(ocr.strip()) > len(text):
                return ocr
        return text

    def _ocr_pdf(self, raw):
        """OCR-fallback. Dyr — körs bara under tröskeln."""
        try:
            import fitz
        except ImportError as error:
            raise UserError('PyMuPDF saknas — OCR kräver den.') from error

        # FYND (2026-11-01): designen (D4) skrev `lang='swe+eng'`, men
        # PyMuPDF:s parameter heter `language` — `lang` gav
        # `TypeError: get_textpage_ocr() got an unexpected keyword argument
        # 'lang'`. Varje skannad PDF blev `failed` i stället för OCR:ad.
        parts = []
        with fitz.open(stream=raw, filetype='pdf') as doc:
            for page in doc:
                textpage = page.get_textpage_ocr(language='swe+eng', full=False)
                parts.append(page.get_text(textpage=textpage) or '')
        return '\n'.join(parts).strip()

    def _extract_zip(self, raw, kind):
        """DOCX/ODT/XLSX/PPTX — zip med XML inuti.

        FYND (2026-11-01): den första versionen använde regex mot XML:en. För
        ODT gav det 92 119 tecken som började med
        `<text:list-level-style-number text:level="1" ...>` — alltså
        STILUPPsättningen, inte texten. Regex kan inte skilja `<text:p>` som
        bär innehåll från `<text:p>` inuti en stildefinition, och nästlade
        element (`<text:span>` i `<text:p>`) gör det värre.

        Vi tolkar därför XML:en och plockar text-noderna. Det är några
        millisekunder per fil och det är rätt svar i stället för ett snabbt.
        """
        import io
        import re
        import zipfile
        import xml.etree.ElementTree as ET

        # Vilka XML-delar som bär texten, per format.
        targets = {
            'docx': [r'word/document\.xml'],
            'odt': [r'content\.xml'],
            'xlsx': [r'xl/sharedStrings\.xml', r'xl/worksheets/.*\.xml'],
            'ods': [r'content\.xml'],
            'pptx': [r'ppt/slides/slide\d+\.xml'],
            'odp': [r'content\.xml'],
        }[kind]

        parts = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                if not any(re.fullmatch(pattern, name) for pattern in targets):
                    continue
                try:
                    root = ET.fromstring(archive.read(name))
                except ET.ParseError:
                    continue
                # All text i dokumentordning. ElementTree ger oss bara
                # innehållet i löv-noderna, aldrig attributen — vilket är
                # precis skillnaden mot regexen.
                for node in root.iter():
                    # ODF: stycken och rubriker är egna block.
                    if node.tag.endswith(('}p', '}h')):
                        chunk = ''.join(node.itertext()).strip()
                        if chunk:
                            parts.append(chunk)
                        continue
                # DOCX/XLSX/PPTX: <w:t>/<t> är text-noderna. Vi tar dem
                # separat eftersom deras förälder (<w:p>) inte är ODF:s p.
                if kind in ('docx', 'xlsx', 'pptx'):
                    for node in root.iter():
                        if node.tag.endswith(('}t',)) and node.text:
                            parts.append(node.text)
        return self._clean(' '.join(parts))

    def _extract_html(self, raw):
        import re
        html = self._decode(raw)
        html = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html)
        return self._clean(re.sub(r'<[^>]+>', ' ', html))

    def _extract_email(self, raw):
        import email
        from email import policy
        message = email.message_from_bytes(raw, policy=policy.default)
        parts = []
        if message.get('subject'):
            parts.append(str(message.get('subject')))
        for part in message.walk():
            if part.get_content_type() == 'text/plain':
                try:
                    parts.append(part.get_content())
                except Exception:  # noqa: BLE001
                    continue
        return self._clean('\n'.join(parts))

    # ── EXIF (5b) ──────────────────────────────────────────────────────

    #: EXIF-fält vars fritext blir en del av OKF-kroppen.
    #:
    #: GPS ÄR INTE MED, och det är avsiktligt. "57.7089 11.9746" i kroppen
    #: blir två sökbara tal som matchar allt och inget — och gör någons
    #: hemadress sökbar för alla som ser konceptet. Se docs/gdpr.md §4.1.
    EXIF_TEXT_FIELDS = ('ImageDescription', 'UserComment', 'XPTitle',
                        'XPKeywords', 'XPSubject', 'Artist')

    def _extract_exif(self, raw, mimetype):
        """Läs EXIF ur en bild. Returnerar (vals, text).

        VARFÖR TOM TEXT ÄR ETT GODKÄNT SVAR: en skärmbild har ingen EXIF. En
        PNG från en skärmdump är inte ett fel — den är en bild utan metadata.
        Att kasta här hade gjort varje skärmbild till `failed` och fyllt
        fältet `extract_error` med brus.
        """
        if not mimetype.startswith('image/'):
            return {}, ''
        if mimetype == 'image/svg+xml':
            # SVG är XML, inte en rasterbild — ingen EXIF.
            return {}, ''

        try:
            from PIL import Image
            from PIL.ExifTags import GPSTAGS, TAGS
        except ImportError:
            # Pillow saknas. Det är inte skäl att fälla filen: texten (som
            # är det primära) kan fortfarande utvinnas för andra format.
            _logger.info(
                'dms_extract: Pillow saknas — hoppar över EXIF för %s',
                self.name)
            return {}, ''

        try:
            with Image.open(io.BytesIO(raw)) as image:
                exif = image.getexif()
                if not exif:
                    return {}, ''
                flat = {TAGS.get(key, str(key)): value
                        for key, value in exif.items()}
                # GPS ligger i en egen IFD — måste läsas separat.
                gps = {}
                try:
                    gps_ifd = exif.get_ifd(0x8825)
                    if gps_ifd:
                        gps = {GPSTAGS.get(key, str(key)): value
                               for key, value in gps_ifd.items()}
                except Exception:  # noqa: BLE001
                    gps = {}
        except Exception as error:  # noqa: BLE001
            # En trasig EXIF-header får inte fälla kön. Bilden är fortfarande
            # en bild, och `done` med tom text är det ärliga svaret.
            _logger.info('dms_extract: EXIF oläsbar för %s: %s',
                         self.name, error)
            return {}, ''

        vals = {}
        text_parts = []

        taken = flat.get('DateTimeOriginal') or flat.get('DateTime')
        if taken:
            parsed = self._parse_exif_datetime(taken)
            if parsed:
                vals['exif_datetime_original'] = parsed

        if flat.get('Make'):
            vals['exif_make'] = str(flat['Make']).strip()[:128]
        if flat.get('Model'):
            vals['exif_model'] = str(flat['Model']).strip()[:128]
        if flat.get('Orientation'):
            try:
                vals['exif_orientation'] = int(flat['Orientation'])
            except (TypeError, ValueError):
                pass

        lat = self._gps_to_decimal(gps.get('GPSLatitude'),
                                   gps.get('GPSLatitudeRef'))
        lon = self._gps_to_decimal(gps.get('GPSLongitude'),
                                   gps.get('GPSLongitudeRef'))
        if lat is not None and lon is not None:
            vals['exif_gps_lat'] = lat
            vals['exif_gps_lon'] = lon

        for field in self.EXIF_TEXT_FIELDS:
            value = flat.get(field)
            if not value:
                continue
            if isinstance(value, bytes):
                # XPTitle m.fl. är UTF-16LE med nollbytes.
                try:
                    value = value.decode('utf-16-le', errors='ignore')
                except Exception:  # noqa: BLE001
                    continue
            value = str(value).strip('\x00 ').strip()
            if value:
                text_parts.append(value)

        # Rådata: allt vi läste, men JSON-säkert. Datetime-objekt och
        # bytes kan inte serialiseras — vi strängar dem.
        vals['exif_raw'] = self._json_safe({**flat, **gps})

        return vals, self._clean(' '.join(text_parts))

    @staticmethod
    def _parse_exif_datetime(value):
        """'2026:05:12 14:33:01' → datetime. EXIF använder kolon i datumet."""
        from datetime import datetime
        raw = str(value).strip().strip('\x00')
        for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S',
                    '%Y:%m:%d', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _gps_to_decimal(coordinate, ref):
        """EXIF GPS är (grader, minuter, sekunder) som Rational — inte float."""
        if not coordinate:
            return None
        try:
            parts = [float(part) for part in coordinate]
        except (TypeError, ValueError):
            return None
        if len(parts) != 3:
            return None
        degrees, minutes, seconds = parts
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if str(ref or '').strip().upper() in ('S', 'W'):
            decimal = -decimal
        return round(decimal, 7)

    @staticmethod
    def _json_safe(data):
        """Gör EXIF-dicten serialiserbar — bytes och Rational blir strängar."""
        result = {}
        for key, value in (data or {}).items():
            if isinstance(value, bytes):
                try:
                    result[key] = value.decode('utf-8', errors='replace')
                except Exception:  # noqa: BLE001
                    result[key] = repr(value)
            elif isinstance(value, (int, float, str, bool)) or value is None:
                result[key] = value
            elif isinstance(value, (list, tuple)):
                result[key] = [str(item) for item in value]
            else:
                result[key] = str(value)
        return result

    # ── Hjälpare ───────────────────────────────────────────────────────

    @staticmethod
    def _is_binary_type(mimetype):
        """Typ som aldrig bär läsbar text?

        Gränsdragningen är avsiktlig: bilder, ljud, video och teckensnitt
        avkodade som text blir skräp som SER UT som innehåll i en sökträff.
        SVG är undantaget — det är XML och bär faktisk text.
        """
        if not mimetype:
            return False
        if mimetype.startswith(('image/', 'audio/', 'video/', 'font/')):
            return mimetype != 'image/svg+xml'
        return mimetype in BINARY_MIMETYPES

    @staticmethod
    def _decode(raw):
        for encoding in ('utf-8', 'latin-1'):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace')

    @staticmethod
    def _clean(text):
        return re.sub(r'\s+', ' ', DmsFile._sanitize(text)).strip()

    @staticmethod
    def _sanitize(text):
        """Ta bort tecken PostgreSQL inte kan lagra.

        FYND (2026-11-01): en PDF gav `ValueError: A string literal cannot
        contain NUL (0x00) characters` vid commit — hela kön föll på EN fil.
        NUL och de andra C0-kontrolltecknen (utom tab/nyrad/vagnretur) är
        lagliga i Python-strängar men inte i en text-kolumn. De dyker upp i
        PDF:er med trasiga teckensnitt och i binära filer som råkar ha en
        text-mimetype.

        Vi normaliserar i stället för att kasta: en PDF med ett NUL-tecken
        i en sidfot är fortfarande sökbar.
        """
        if not text:
            return ''
        # C0 utom \t \n \r, plus DEL och C1.
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', str(text))

    # ── OKF-handoff (D7) ───────────────────────────────────────────────

    def _okf_body_source(self):
        """Dokumenttexten FÖRE filnamnet.

        Ordningen är avsiktlig: sammanfattningen klipps från början av
        kroppen (`_okf_summary_max_chars`), och en sammanfattning som börjar
        med dokumentets eget innehåll beskriver dokumentet. Börjar den med
        filnamnet beskriver den filnamnet — vilket är precis vad vi redan
        hade.
        """
        body = super()._okf_body_source()

        # FYND (2026-11-01): `_extracted_text` är ett `Text`-fält, och
        # mixinens generiska källa plockar upp ALLA Text-fält. Utan den här
        # raden hamnade dokumenttexten i kroppen två gånger — en gång via
        # super() och en gång via prependen — 186 102 tecken där 93 051
        # räckte. Sammanfattningen klipps från början, så felet syntes inte
        # i sökningen; det syntes bara i kostnaden.
        #
        # Vi kan inte utöka mixinens OKF_BODY_SKIP (den läses i super() och
        # en subklass-konstant hade skuggat den), så vi tar bort den ena
        # förekomsten här i stället: super() gav oss texten EN gång, och det
        # är den vi lägger först.
        if self._extracted_text:
            body = body.replace(self._extracted_text, '', 1).strip()

        if self.extract_state != 'done' or not self._extracted_text:
            return body
        if body:
            return self._extracted_text + '\n\n' + body
        return self._extracted_text

    def _okf_body_source_gps_guard(self):
        """Kontroll att inga koordinater nådde kroppen (5b.4).

        GPS ligger i `exif_gps_lat`/`exif_gps_lon` — Float-fält som mixinens
        generiska källa aldrig plockar upp (den tar bara html/text/name).
        Men ett fält kan hamna i kroppen på andra vägar: `exif_raw` är Json
        och skulle kunna läsas av en framtida override. Den här metoden är
        den uttryckliga kontrollen, och testet använder den.

        Se docs/gdpr.md §4.1: en bild tagen hemma bär någons hemadress.
        """
        self.ensure_one()
        body = self._okf_body_source()
        for value in (self.exif_gps_lat, self.exif_gps_lon):
            if not value:
                continue
            # Både punkt- och kommaform, och med sex decimaler.
            for rendered in ('%.6f' % value, ('%.6f' % value).replace('.', ','),
                             '%.4f' % value):
                if rendered in body:
                    return False
        return True
