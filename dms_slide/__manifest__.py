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
    'name': 'Document: DMS Slides',
    'version': '18.0.1.0.0',
    'summary': 'A document directory for every course and every lesson.',
    'description': '''
Document: DMS Slides
====================

Gives every ``slide.channel`` (a course) and every ``slide.slide`` (a lesson) a
document directory of its own, so handouts, exercises and certificates live
with the course that uses them.

Two storages, not one nested inside the other. A lesson's directory sits under
the *lesson* storage's root, not under its course's directory: the lesson is
the record that owns the file, and nesting would make a lesson's files
disappear when it is moved to another course.

Access mode is ``inherit`` for both: course material is readable by whoever may
read the course or lesson, decided by that record's own ``ir.rule``. That
requires each storage to be ``save_type='attachment'`` with
``inherit_access_from_parent_record`` set, because ``dms.security.mixin``
hardcodes both when it resolves inherited access.

This module auto-installs when both ``website_slides`` and ``dms`` are installed.
    ''',
    'category': 'Document Management',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-document/dms_slide',
    'license': 'AGPL-3',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    'depends': ['website_slides', 'dms', 'dms_record'],
    'auto_install': True,
    'data': [
        'data/slide_data.xml',
        'views/slide_views.xml',
    ],
}
