# -*- coding: utf-8 -*-
{
    'name': 'Document Wiki',
    'version': '14.1.0.0.0',
    'summary': 'Adds sub page to page',
    'category': '',
    'description': """
        Adds sub page to page
    """,
    'author': 'Vertel AB',
    'license': 'AGPL-3',
    'website': 'https://www.vertel.se',
    'depends': ['website'],
    'data': [
        'views/assets.xml',

    ],
    "qweb": [
        'static/src/xml/website.pageProperties.xml'
    ],
    'installable': True,
}
