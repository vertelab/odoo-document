# -*- coding: utf-8 -*-
"""dms.directory — per-directory extraction switch (dms-content-extraction D6).

VARFÖR EN EGENSKAP OCH INTE EN HEURISTIK: en Vaultwarden-mapp innehåller
chiffertext. Att utvinna text ur den indexerar brus — och värre, det ger en
body som ingen kan verifiera. Att i stället gissa på byten (försök dekryptera,
se om det ser ut som text) skulle tyst indexera en trasig PDF som om den vore
krypterad. En flagga på mappen är ett beslut någon fattat; en heuristik är en
gissning som råkar se ut som ett beslut.
"""

from odoo import models, fields


class DmsDirectory(models.Model):
    _inherit = 'dms.directory'

    extract_enabled = fields.Boolean(
        'Extract text',
        default=True,
        help='Extract text from files in this directory and its children.\n'
             'Turn off for directories holding ciphertext (Vaultwarden) or '
             'content that must not become searchable.\n'
             'NOTE: extraction has no group guard — the OKF mixin refuses '
             'fields with `groups`, but extracted text is not a field with '
             '`groups`. A directory with restricted content must switch this '
             'off explicitly.')
