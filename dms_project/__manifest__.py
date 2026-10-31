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
    'name': 'Document: DMS Project',
    'version': '18.0.1.1.1',
    'summary': 'DMS Project.',
    'description': '''
DMS Project
===========

Gives every project a document directory, created with the project and
linked by ``res_model``/``res_id`` rather than by name.

The directory lives in an attachment storage with
``inherit_access_from_parent_record``, so it inherits the project's own
access rule. Note that ``project.project`` defaults to
``privacy_visibility='portal'``, where every internal user sees every
project's documents; set ``privacy_visibility='followers'`` on a project
that should be genuinely per-project.

Builds on ``project.project`` and ``project.task`` via ``dms.record.mixin``.
    ''',
    'category': 'Technical',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-document/dms_project',
    'images': ['static/description/banner.png'],  # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    # any module necessary for this one to work correctly
    'depends': ['project', 'dms', 'dms_record'],
    'auto_install': True,

    # always loaded
    'data': [
        'data/project_data.xml',
        'views/views.xml',
        'views/dms_directory.xml',
        'views/dms_file.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
