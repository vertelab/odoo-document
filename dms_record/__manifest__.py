# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
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
    'name': 'Document: DMS Record',
    'version': '18.0.1.0.0',
    'summary': 'Shared primitive: one DMS directory per record.',
    'description': '''
DMS Record
==========

Shared primitive for the ``dms_*`` bridge modules.

Gives every record of a bridge model exactly one ``dms.directory`` linked to it
through ``res_model`` and ``res_id``, so that

  * documents in that directory inherit the record's access rights,
  * a file written through WebDAV, SFTP or the API picks up the link without
    the writing code setting it, and
  * ``doc_count`` has one meaning instead of eighteen.

    Features:

        - Extends Odoo: adds the abstract model ``dms.record.mixin``.
        - No new tables.
    ''',
    'category': 'Technical',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-document/dms_record',
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    'depends': ['dms'],
    'data': [],
}
