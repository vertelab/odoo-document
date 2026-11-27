# -*- coding: utf-8 -*-
{
    'name': 'FS Attachment HTTP Stream Fix',
    'version': '18.0.1.0.0',
    'summary': 'Gör att stora bilagor i S3-filestore kan streamas via HTTP',
    'description': """
FS Attachment HTTP Stream Fix
=============================

Problem
-------
`fs_attachment` (OCA/storage) patchar `_file_read`, `_file_write` och
`_file_delete` så att bilagor läses från objektlagring (S3). Men den
patchar **inte** `ir.attachment._to_http_stream()`, som används när en
bilaga levereras via HTTP (`/web/image/...`, `/web/content/...`).

Odoos originalimplementation gör:

    if self.store_fname:
        stream.type = 'path'
        stream.path = werkzeug.security.safe_join(
            os.path.abspath(config.filestore(request.db)),
            self.store_fname,
        )
        stat = os.stat(stream.path)      # <-- FileNotFoundError

Med S3-lagring finns ingen lokal fil. Resultatet blir:

    FileNotFoundError: '/var/lib/odoo/.../filestore/<db>/<db>:/15/159bc8...'

Det slår hårdast mot stora filer som asset-bundles
(`web.assets_frontend_minimal.min.js` m.fl.) — de ger HTTP 500 och
webbplatsen tappar sitt JavaScript. Mindre bilagor klarar sig ibland
eftersom de cachas i `raw`.

Lösning
-------
Modulen overridear `_to_http_stream()` och returnerar en `data`-stream
byggd från `self.raw` när `store_fname` pekar på en konfigurerad
`fs.storage`. Då används `fs_attachment`s `_file_read` (som redan går mot
S3) i stället för `os.stat()` mot en lokal sökväg.

Filen läses in i minnet. För asset-bundles (några MB) är det försumbart;
för mycket stora filer är det en avvägning mot att de inte kan levereras
alls.

Alternativ som övervägdes
-------------------------
* `X-Sendfile` mot S3 — kräver att frontproxy kan signera URL:er, vilket
  Caddy inte gör utan plugin.
* Signerade S3-URL:er — `fs_attachment_s3` har stöd
  (`s3_uses_signed_url_for_x_sendfile`) men det kräver att klienten får
  en redirect, vilket bryter `Content-Disposition` för nedladdningar.
""",
    'author': 'Vertel AB',
    'website': 'https://vertel.se',
    'category': 'Technical',
    'license': 'LGPL-3',
    'depends': ['fs_attachment'],
    'installable': True,
    'auto_install': True,
}
