# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'Document: Onboarding (LMS)',
    'version': '18.0.2.0.0',
    'summary': 'Onboardingskurs: dokument, DMS och WebDAV',
    'description': """
Dokumenthantering i Vertel
==========================

Onboardingskurs som lär ut hur du strukturerar dokument, monterar
dokumenthanteringen som nätverksdisk och hanterar versioner.

4 sektioner, 12 slides (7 article, 1 infographic, 4 quiz):

- Sektion 1: Varför dokumenthantering — problemet med utspridda filer
- Sektion 2: Ladda upp och strukturera — mappar, namngivning, metadata
- Sektion 3: Montera WebDAV — dokumenthanteringen som nätverksdisk
- Sektion 4: Versioner och Office-redigering — historik och direktredigering

Innehållet ligger i data/ (inte demo/) så att det laddas i alla databaser.
    """,
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-document/document_onboarding',
    'license': 'AGPL-3',
    'category': 'Website/eLearning',
    'depends': ['website_slides'],
    'data': [
        'data/slide_channel.xml',
        'data/slide_slides_s1.xml',
        'data/slide_slides_s2.xml',
        'data/slide_slides_s3.xml',
        'data/slide_slides_s4.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
