# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo SA, Open Source Management Solution, third party addon
#    Copyright (C) 2022- Vertel Sverige AB (<https://vertel.se>).
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
    'name': 'Document: DMS Property',
    'version': '18.0.1.0.0',
    'summary': 'DMS Property.',
    'description': '''
DMS Property
============

    DMS Property.

    Features:

        - UI Integration: Extends 1 view(s) in the Odoo interface.
        - Extends Odoo: Builds on property.property.
    ''',
    'category': 'Technical',
    'description': 'Creates the Link between Property and DMS',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-document/dms_property_mgmt',
    'images': ['static/description/banner.png'],  # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    # any module necessary for this one to work correctly
    'depends': ['property_mgmt', 'dms'],
    # always loaded
    'data': [
        'views/property_property_view.xml',
    ],
}
