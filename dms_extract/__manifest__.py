# -*- coding: utf-8 -*-
{
    'name': 'Document: Text Extraction',
    'version': '18.0.1.2.2',
    'summary': 'Extract text from dms.file content into the OKF body',
    'category': 'Hidden',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'description': """
        Text extraction for the document management system.

        WHY: `dms_ai` makes every `dms.file` an OKF concept, but the indexed
        body is the filename, the directory and the tags -- not the file.
        A customer who uploads `Avtal-2026.pdf` can find it by typing
        `avtal` and nothing else; the 2 400 words inside it are invisible to
        both signals the search uses (the Swedish BM25 column and the
        embedding), because neither ever sees the bytes.

        This module extracts the text and supplies it as the OKF body
        source. The existing indexer, the existing search_vector column and
        the existing embedding path then cover the document contents with no
        change to the search code.

        EXTRACTION IS QUEUED, NEVER SYNCHRONOUS. `_inverse_content` is the
        single write path for five protocols (form, WebDAV, SFTP, API, PWA).
        A slow extractor there would slow every upload on every protocol, so
        extraction runs as a `cron.task` on the `min` cadence.

        OCR IS A FALLBACK. A text layer is used when present; OCR runs only
        when the text layer is below `dms_extract.ocr_threshold`, because OCR
        is roughly two orders of magnitude more expensive per page.

        ENCRYPTED DIRECTORIES ARE EXCLUDED. A directory with
        `extract_enabled=False` (e.g. a Vaultwarden directory holding
        ciphertext) is never extracted. This is a property of the directory,
        not a heuristic on the bytes.

        SYSTEM DEPENDENCIES: PyMuPDF and Tesseract with `swe` and `eng`
        traineddata. The post-init hook refuses to install without them.
    """,
    'depends': [
        'dms_ai',
        'cron_tick',
    ],
    'data': [
        'data/cron_task.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
