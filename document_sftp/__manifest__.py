# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "SFTP",
    "version": "14.0.1.0.0",
    "author": "Vertel AB,Therp BV,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "category": "Knowledge Management",
    "summary": "Access your documents via SFTP",
    "depends": [
        'base',
        'mail'
    ],
    "demo": [
        "demo/res_users.xml",
    ],
    "data": [
        "demo/res_users.xml",
        "views/res_users.xml",
        "data/ir_config_parameter.xml",
        "data/ir_cron.xml",
    ],
#    "post_init_hook": 'install_hook',
#    'uninstall_hook': 'uninstall_hook',
    "external_dependencies": {
        'python': ['paramiko'],
    },
}
