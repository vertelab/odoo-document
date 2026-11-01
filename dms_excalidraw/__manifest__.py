# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2026- Vertel Sverige AB (<https://vertel.se>).
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'Document: DMS Excalidraw',
    'version': '18.0.1.0.0',
    'summary': 'Whiteboard (Excalidraw) kopplad till DMS-dokument',
    'description': '''
DMS Excalidraw
==============

Gör en Excalidraw-ritning till ett dokument bland alla andra — knutet till
samma affärsobjekt som övriga DMS-filer (kund, order, projekt, uppgift).

Varför en brygga och inte en egen modell
----------------------------------------
En whiteboard är en fil, inte en post. Genom att spara ritningen som en
``dms.file`` med ``extension = excalidraw`` ärver den allt som redan finns:

  * backup (borg/restic) — DMS-filer ingår i backupen
  * retention och legal hold
  * revision (``document_version``)
  * delning och behörighet (``dms.access.group``)
  * koppling till affärsobjekt (``res_model``/``res_id``)

En separat modell hade krävt egen backup, egen behörighet och egen
revisionslogg — och hade inte synts i kundens dokumentflik.

Funktioner
----------
  * "New whiteboard" i DMS-filvyn — skapar en tom ``.excalidraw``-fil
  * "Open in Excalidraw" på ``dms.file`` när ``extension = excalidraw``
  * Ritningen öppnas i den fristående Excalidraw-tjänsten
    (se /srv/salt/excalidraw/README.md) med filen hämtad via
    DMS-WebDAV, och sparas tillbaka samma väg
  * Fungerar på alla modeller som redan har DMS-koppling
    (``res.partner``, ``sale.order``, ``project.project``, ``project.task`` …)

Vad som INTE ingår
------------------
Realtidssamarbete. Excalidraw:s kollaborativa läge kräver en WebSocket-relay
(y-websocket/Liveblocks). Utan den är detta en "rita, spara, öppna igen"-
whiteboard. Det är fortfarande en riktig whiteboard — men det är inte
Nextclouds realtidsläge.
    ''',
    'category': 'Productivity/Documents',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-document/dms_excalidraw',
    'license': 'AGPL-3',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-document',
    'depends': [
        'dms',
        'dms_webdav',
    ],
    'data': [
        'data/excalidraw_data.xml',
        'views/dms_file_view.xml',
        'views/res_config_settings_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
