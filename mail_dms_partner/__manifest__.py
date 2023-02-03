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
    'name': 'Document: DMS Partner',
    'version': '14.0.0.1.0',
    'summary': 'Manage Partner Documents',
    'category': 'Technical',
    'description': 'Manage Partner Document',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-document/mail_dms_partner',
    'images': ['static/description/banner.png'],  # 560x280 px.
    'license': 'AGPL-3',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    # Any module necessary for this one to work correctly

    'depends': ['dms','contacts','base_signature',],
    'data': [
        'security/ir.model.access.csv',
        'views/dms_view.xml',
        'views/partner_dms_file_view.xml',
        'views/res_partner_view.xml',
        'data/action.xml',
        'data/mail_template.xml',
    ],
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
