# -*- coding: utf-8 -*-
{
    'name': 'FileStore Upload',
    'version': '14.1.0.0.0',
    'summary': 'Upload large files with SFTP',
    'category': '',
    'description': """
        """,
    'author': 'Vertel AB',
    'license': 'AGPL-3',
    'website': 'https://www.vertel.se',
    'depends': ['mail'],
    'data': [
        'views/filestore_view.xml',
        'views/assets.xml',
        'security/ir.model.access.csv',
    ],
    "qweb": [
        'static/src/xml/attachment_box.xml'
    ],
    'external_dependencies': {
        'python': ['paramiko'],
    },
    'installable': True,
}
