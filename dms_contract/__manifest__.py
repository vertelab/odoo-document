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
    'name': 'Document: DMS Contract',
    'version': '18.0.1.0.0',
    'summary': 'A document directory for every contract.',
    'description': '''
Document: DMS Contract
======================

Gives every ``contract.contract`` a document directory of its own, so the
signed agreement, its annexes and its correspondence live with the contract
instead of somewhere else.

Access mode is ``inherit``: a contract's documents are readable by whoever may
read the contract, decided by the contract's own ``ir.rule``. That requires the
storage to be ``save_type='attachment'`` with
``inherit_access_from_parent_record`` set, because ``dms.security.mixin``
hardcodes both when it resolves inherited access.

This module auto-installs when both ``contract`` and ``dms`` are installed.
    ''',
    'category': 'Document Management',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-document/dms_contract',
    'license': 'AGPL-3',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    'depends': ['contract', 'dms', 'dms_record'],
    'auto_install': True,
    'data': [
        'data/contract_data.xml',
        'views/contract_views.xml',
    ],
}
