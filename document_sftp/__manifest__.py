# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo SA, Open Source Management Solution, third party addon
#    Copyright (C) 2022- Vertel AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'Document: SFTP',
    'version': '1.2',
    # Version ledger: 14.0 = Odoo version. 1 = Major. Non regressionable code. 2 = Minor. New features that are regressionable. 3 = Bug fixes
    'summary': 'Access your documents via SFTP.',
    'category': 'Technical',
    'description': 'Access your documents via SFTP.',
    #'sequence': '1',
    'author': 'Vertel AB, Therp BV, Odoo Community Association (OCA)',
    'website': 'https://vertel.se/apps/odoo-document/document_sftp',
    'images': ['static/description/banner.png'], # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    'depends': ['base','mail',],
    "demo": [
        "demo/res_users.xml",
    ],
    "data": [
        # NOTE: demo/res_users.xml must NOT be listed here. It updates
        # base.user_demo, which only exists when demo data is enabled
        # (without_demo=False). Loading it unconditionally aborts the whole
        # registry with:
        #   ParseError: while parsing document_sftp/demo/res_users.xml:4
        #   Exception: Cannot update missing record 'base.user_demo'
        # It is correctly declared under "demo" above.
        "security/ir.model.access.csv",
        "views/res_users.xml",
        "data/ir_config_parameter.xml",
        "data/ir_cron.xml",
    ],
    "post_init_hook": "install_hook",
    "uninstall_hook": "uninstall_hook",
    "external_dependencies": {
        'python': ['paramiko'],
    },
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
