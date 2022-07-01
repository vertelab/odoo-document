# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "DMS with SFTP",
    "version": "14.0.1.0.0",
    "author": "Vertel AB",
    "license": "AGPL-3",
    "category": "Document Management via SFTP",
    "summary": "Access your documents via SFTP",
    "depends": ['base', 'mail', 'dms'],
    "data": [
        "data/ir_config_parameter.xml",
        # "views/dms_view.xml",
    ],
    "external_dependencies": {
        'python': ['paramiko'],
    },
}
