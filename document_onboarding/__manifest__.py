# -*- coding: utf-8 -*-
{
    'name': 'Dokumenthantering i Vertel',
    'version': '18.0.1.0.0',
    'summary': 'Onboardingskurs: dokument, DMS och WebDAV',
    'description': """
Lär dig strukturera dokument, montera WebDAV som nätverksdisk och hantera versioner.
""",
    'author': 'Vertel AB',
    'website': 'https://vertel.se',
    'license': 'LGPL-3',
    'category': 'Website/eLearning',
    'depends': ['website_slides'],
    'data': [
        'views/slide_channel_data.xml',
    ],
    'demo': [
        'demo/slide_slide_demo.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
