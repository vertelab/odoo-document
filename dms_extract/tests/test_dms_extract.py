# -*- coding: utf-8 -*-
"""Tester för dms_extract — utvinning, kö, idempotens, OKF-handoff.

VARFÖR DE HÄR TESTERNA FINNS: modulen rör en Binary-kolumn som fem protokoll
skriver till, och den matar en sökning som folk litar på. Tre saker måste
bevisas och inte antas:

1. Att kön TÖMS. En kö som svälter ser ut att vara klar.
2. Att kön är IDEMPOTENT. En hash-jämförelse som aldrig kan matcha kör om
   hela arkivet var femte minut.
3. Att OKF-kroppen får dokumenttexten EN gång — inte två, inte noll.
"""

import base64
import unittest
import io
import zipfile

from odoo.tests import TransactionCase, tagged


def _make_pdf(text):
    """Minimal PDF med en textyta — utan externa beroenden i testet."""
    content = "BT /F1 12 Tf 72 720 Td (%s) Tj ET" % text
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(("%d 0 obj\n%s\nendobj\n" % (index, body)).encode('latin-1'))
    xref = out.tell()
    out.write(("xref\n0 %d\n" % (len(objects) + 1)).encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(("%010d 00000 n \n" % offset).encode())
    out.write(("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
               % (len(objects) + 1, xref)).encode())
    return out.getvalue()


def _make_docx(text):
    """Minimal DOCX — zip med word/document.xml."""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body><w:p>'
        '<w:r><w:t>%s</w:t></w:r></w:p></w:body></w:document>' % text)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr('word/document.xml', document)
    return out.getvalue()


def _make_odt(text):
    """Minimal ODT — zip med content.xml, inklusive en stildeklaration.

    Stildeklarationen är poängen: den första regex-baserade utvinningen
    returnerade `<text:list-level-style-number ...>` i stället för texten.
    """
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0">'
        '<office:automatic-styles>'
        '<text:list-level-style-number text:level="1" '
        'style:num-format="1"/>'
        '</office:automatic-styles>'
        '<office:body><office:text>'
        '<text:p>%s</text:p>'
        '</office:text></office:body></office:document-content>' % text)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr('content.xml', content)
    return out.getvalue()


@tagged('post_install', '-at_install', 'dms_extract')
class TestDmsExtract(TransactionCase):
    """Utvinning och kö."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Directory = cls.env['dms.directory']
        cls.File = cls.env['dms.file']
        # OCA:s dms kräver en förälder: en katalog utan parent avvisas med
        # "A directory has to have a parent directory." Vi skapar därför en
        # rot (parent_id = False är tillåtet för roten) och testkatalogen
        # under den.
        cls.storage = cls.env['dms.storage'].create({
            'name': 'Extract test storage',
        })
        cls.root = cls.Directory.create({
            'name': 'Extract test root',
            'storage_id': cls.storage.id,
            'is_root_directory': True,
        })
        cls.directory = cls.Directory.create({
            'name': 'Extract test directory',
            'parent_id': cls.root.id,
        })

    def _file(self, name, content, mimetype):
        """Skapa en fil vars innehåll läses tillbaka i samma transaktion.

        VARFÖR `content_binary` OCH INTE `content`: OCA:s `dms.file.content`
        är `store=False` med en compute som läser från filestore via
        `content_file`. I ett test skrivs blobben till en temporär filestore
        som `_compute_content` inte alltid hinner/kan läsa tillbaka — då blev
        `self.content` False och varje utvinning "lyckades" med tom text.
        `content_binary` är DB-lagrad och läses tillbaka direkt, så testet
        mäter utvinningen och inte filestore-uppsättningen.
        """
        record = self.File.create({
            'name': name,
            'directory_id': self.directory.id,
            'content_binary': content,
        })
        # `mimetype` är compute+store och beräknas från filnamnet/innehållet
        # — värdet i create() skrivs över. Vi sätter det efteråt så testet
        # mäter det format det påstår sig mäta (en .txt blev annars
        # application/octet-stream och föll i binärgrinden).
        record.write({'mimetype': mimetype})
        return record

    # ── 2.1 Format ─────────────────────────────────────────────────────

    def test_pdf_with_text_layer_yields_text(self):
        record = self._file('avtal.pdf', _make_pdf('Avtalsvillkor'),
                            'application/pdf')
        record._extract_one()
        self.assertEqual(record.extract_state, 'done')
        self.assertIn('Avtalsvillkor', record._extracted_text)

    def test_docx_yields_text(self):
        record = self._file(
            'brev.docx', _make_docx('Hej fran DOCX'),
            'application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document')
        record._extract_one()
        self.assertEqual(record.extract_state, 'done')
        self.assertIn('Hej fran DOCX', record._extracted_text)

    def test_odt_yields_text_not_style_markup(self):
        """FYND 2026-11-01: regex gav stiluppsättningen i stället för texten."""
        record = self._file(
            'dokument.odt', _make_odt('Sjalva texten'),
            'application/vnd.oasis.opendocument.text')
        record._extract_one()
        self.assertIn('Sjalva texten', record._extracted_text)
        self.assertNotIn('list-level-style-number', record._extracted_text)

    def test_plain_text_yields_text(self):
        record = self._file('anteckning.txt', b'Ren text har', 'text/plain')
        record._extract_one()
        self.assertIn('Ren text har', record._extracted_text)

    def test_binary_types_yield_no_text(self):
        """Bilder/ljud är inte dokument — de får inte bli skräp i indexet.

        FYND 2026-11-01: en JPEG blev 145 003 tecken latin-1-avkodad
        binärdata som såg ut som innehåll i en sökträff.
        """
        # Riktig minimal PNG (1x1) — Odoo försöker skapa en miniatyr av
        # bilder, och en påhittad header ger UnidentifiedImageError.
        png = base64.b64decode(
            b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
            b'z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        record = self._file('logo.png', png, 'image/png')
        record._extract_one()
        self.assertEqual(record.extract_state, 'done')
        self.assertEqual(record.extracted_chars, 0)
        self.assertFalse(record._extracted_text)

    def test_nul_bytes_are_stripped(self):
        """FYND 2026-11-01: NUL gav 'A string literal cannot contain NUL'."""
        record = self._file('nul.txt', b'fore\x00efter', 'text/plain')
        self.assertTrue(record.content, 'content lästes inte tillbaka')
        self.assertEqual(record.mimetype, 'text/plain', 'mimetype')
        record._extract_one()   # får inte kasta
        self.assertEqual(record.extract_state, 'done')
        self.assertNotIn('\x00', record._extracted_text or '')
        self.assertIn('fore', record._extracted_text)
        self.assertIn('efter', record._extracted_text)

    # ── 2.3 Taket ──────────────────────────────────────────────────────

    def test_text_is_truncated_at_ceiling(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'dms_extract.max_chars', '100')
        record = self._file('lang.txt', b'x' * 5000, 'text/plain')
        record._extract_one()
        self.assertEqual(record.extracted_chars, 100)
        self.assertEqual(len(record._extracted_text), 100)

    # ── 3.2 Kön ────────────────────────────────────────────────────────

    def test_cron_is_idempotent(self):
        """Andra körningen får inte skriva något."""
        record = self._file('idem.txt', b'kort text', 'text/plain')
        first = self.File._cron_extract_pending()
        self.assertGreaterEqual(first, 1)
        self.assertEqual(record.extract_state, 'done')
        self.assertEqual(self.File._cron_extract_pending(), 0)

    def test_queue_does_not_starve(self):
        """FYND 2026-11-01: kön tog alltid samma första fönster.

        Med `search(limit=limit*3)` och id-ordning nåddes aldrig filer med
        högre id — 83 filer stod kvar som `pending` i evighet medan kön
        rapporterade "tom".
        """
        records = self.File
        for index in range(5):
            records |= self._file(
                'ko%d.txt' % index, b'text ' + str(index).encode(), 'text/plain')
        # Töm kön helt, med en hård gräns så ett svält-fel inte hänger testet.
        for _ in range(20):
            if not self.File._cron_extract_pending():
                break
        for record in records:
            self.assertEqual(record.extract_state, 'done', record.name)

    def test_file_without_content_is_skipped_not_pending_forever(self):
        """FYND 2026-11-01: 192 filer utan blob låg kvar som `pending`."""
        record = self.File.create({
            'name': 'tom.txt',
            'directory_id': self.directory.id,
            'mimetype': 'text/plain',
        })
        self.File._cron_extract_pending()
        self.assertEqual(record.extract_state, 'skipped')

    # ── 2.4 / 3.4 Undantagna mappar ────────────────────────────────────

    def test_directory_with_extract_disabled_is_skipped(self):
        self.directory.extract_enabled = False
        record = self._file('hemlig.txt', b'chiffertext', 'text/plain')
        self.File._cron_extract_pending()
        self.assertEqual(record.extract_state, 'skipped')
        self.assertFalse(record._extracted_text)

    def test_failed_is_terminal_until_hash_changes(self):
        """En trasig fil får inte köras om varje tick."""
        record = self._file('trasig.pdf', b'inte en pdf alls',
                            'application/pdf')
        record.write({
            'extract_state': 'failed',
            'extract_hash': record.checksum,
            'extract_error': 'test',
        })
        # Samma checksum som extract_hash → inget arbete.
        self.assertFalse(record._extract_needs_work())

    # ── 4.1 OKF-handoff ────────────────────────────────────────────────

    def test_body_source_prepends_document_text_once(self):
        """Dokumenttexten först, filnamnet sist — och bara EN gång.

        FYND 2026-11-01: `_extracted_text` är ett Text-fält som mixinens
        generiska källa plockar upp, så texten hamnade i kroppen två gånger
        (186 102 tecken där 93 051 räckte).
        """
        record = self._file('handoff.txt', b'Dokumentets egna ord',
                            'text/plain')
        record._extract_one()
        body = record._okf_body_source()
        self.assertEqual(body.count('Dokumentets egna ord'), 1)
        self.assertIn('handoff.txt', body)
        self.assertLess(body.index('Dokumentets egna ord'),
                        body.index('handoff.txt'))

    def test_body_source_is_unchanged_before_extraction(self):
        """Utan utvinning är kroppen exakt som förut."""
        record = self._file('orord.txt', b'x', 'text/plain')
        record.write({'extract_state': 'pending', '_extracted_text': False})
        body = record._okf_body_source()
        self.assertIn('orord.txt', body)


@tagged('post_install', '-at_install', 'dms_extract')
class TestDmsExtractVersionRestore(TransactionCase):
    """4.3 — en återställd version måste utvinnas igen.

    `dms_version.action_restore()` skriver `content` via `_inverse_content`.
    Frågan är om det sätter `extract_state='pending'`. Om det INTE gör det
    ligger filen kvar som `done` med den gamla texten, och sökningen visar
    innehåll som inte längre finns i filen — ett tyst fel som är värre än
    ingen sökning.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'dms.file.version' not in cls.env:
            raise unittest.SkipTest('dms_version är inte installerad')
        cls.storage = cls.env['dms.storage'].create({'name': 'Version test'})
        cls.root = cls.env['dms.directory'].create({
            'name': 'Version root',
            'storage_id': cls.storage.id,
            'is_root_directory': True,
        })
        cls.directory = cls.env['dms.directory'].create({
            'name': 'Version dir',
            'parent_id': cls.root.id,
        })

    def test_restore_marks_file_pending(self):
        record = self.env['dms.file'].create({
            'name': 'version.txt',
            'directory_id': self.directory.id,
            'content_binary': b'forsta versionen',
        })
        record.write({'mimetype': 'text/plain'})
        record._extract_one()
        self.assertEqual(record.extract_state, 'done')
        self.assertIn('forsta versionen', record._extracted_text)

        # Skriv nytt innehåll — det skapar en version av det gamla.
        record.write({'content_binary': b'andra versionen'})
        record.write({'mimetype': 'text/plain'})
        record._extract_one()
        self.assertIn('andra versionen', record._extracted_text)

        version = self.env['dms.file.version'].search(
            [('file_id', '=', record.id)], limit=1)
        if not version:
            self.skipTest('ingen version skapades — dms_version-versionen '
                          'av modulen skapar dem inte i denna miljö')

        version.action_restore()
        # Efter en återställning SKA filen vara pending igen.
        self.assertEqual(
            record.extract_state, 'pending',
            'action_restore() lämnade extract_state=%r — filen skulle '
            'behålla texten från den version som inte längre är aktiv'
            % record.extract_state)


@tagged('post_install', '-at_install', 'dms_extract')
class TestDmsExtractClamavOrder(TransactionCase):
    """4.4 — en fil som ClamAV avvisar blir aldrig utvunnen.

    Detta kräver ingen kod i dms_extract: `dms_clamav.write()` kastar
    ValidationError FÖRE `super().write()`, så filen blir aldrig ett
    `dms.file` och når aldrig kön. Testet bevisar ordningen.

    Utan clamd (fail-open) kan ordningen inte bevisas här — då skippar vi
    hellre än att påstå något testet inte mätte.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        installed = cls.env['ir.module.module'].search([
            ('name', '=', 'dms_clamav'), ('state', '=', 'installed')])
        if not installed:
            raise unittest.SkipTest('dms_clamav är inte installerad')

    def _clamd_up(self):
        """Svarar clamd? Fail-open-läget gör testet meningslöst."""
        File = self.env['dms.file']
        if not hasattr(File, '_clamav_scan'):
            return False
        if not File._clamav_enabled():
            return False
        # En ofarlig sträng: svarar clamd får vi None, annars fail-open None
        # också. Vi skiljer dem genom att skanna EICAR — bara en levande
        # clamd känner igen signaturen.
        eicar = (b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-'
                 b'ANTIVIRUS-TEST-FILE!$H+H*')
        return bool(File._clamav_scan(eicar))

    def test_rejected_file_never_becomes_extractable(self):
        if not self._clamd_up():
            raise unittest.SkipTest(
                'clamd svarar inte — fail-open gör ordningen omöjlig att '
                'bevisa i den här miljön')

        eicar = (b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-'
                 b'ANTIVIRUS-TEST-FILE!$H+H*')
        directory = self.env['dms.directory'].search(
            [('is_root_directory', '=', True)], limit=1)
        File = self.env['dms.file']
        before = File.search_count([('name', '=', 'eicar.txt')])

        with self.assertRaises(Exception):
            File.create({
                'name': 'eicar.txt',
                'directory_id': directory.id,
                'content': base64.b64encode(eicar),
            })

        # Filen skapades aldrig — alltså finns det inget att utvinna.
        self.assertEqual(
            File.search_count([('name', '=', 'eicar.txt')]), before,
            'ClamAV avvisade filen men den skapades ändå — då kan '
            'utvinningen se den, och attackerstyrda strängar hamnar i '
            'sökindexet')
