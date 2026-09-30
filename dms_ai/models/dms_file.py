# -*- coding: utf-8 -*-
"""dms.file — OKF-indexerbar (dms_ai).

VARFÖR: ett dokument ÄR kunskap — det är hela poängen med att spara det.
Ändå ligger det i en Binary-kolumn som varken BM25 eller embeddings ser.

VAD SOM INDEXERAS: filnamnet (`name`), mappen (`directory_id`) och
taggarna (`tag_ids`). Filens INNEHÅLL kräver textutvinning (PDF, DOCX)
och är en separat uppgift — den generiska kroppskällan rör inte Binary.

DESSUTOM (office-document-agent): förlage-markeringen. En "förlaga" är ett
DMS-dokument som AI-agenten utgår från för stil och generiska sidor. Den
bor här och inte i kärnan — `ai_agent_core` får aldrig nämna `dms`.

Modellen äger sina KÄLLOR; `ai.okf.mixin` äger fälten och flaggan.
"""

from odoo import models, fields, api

# Taggen som markerar en förlaga. Matchas skiftlägesoberoende på namn.
FORLAGA_TAG = 'förlaga'


class DmsFile(models.Model):
    _name = 'dms.file'
    _inherit = ['dms.file', 'ai.okf.mixin']

    # OKF-taggar: egen relationstabell (en many2many kan inte ligga
    # pa en abstrakt mixin — den ger samma tabell for alla arvande).
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'dms_file_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

    is_forlaga = fields.Boolean(
        'Förlaga',
        compute='_compute_is_forlaga', store=True,
        help='Sant när filen är taggad som förlaga — ett dokument som '
             'AI-agenten utgår från för stil och generiska sidor.')

    @api.depends('tag_ids', 'tag_ids.name')
    def _compute_is_forlaga(self):
        for rec in self:
            rec.is_forlaga = any(
                (t.name or '').strip().lower() == FORLAGA_TAG
                for t in rec.tag_ids)

    @api.model
    def _ai_find_forlagor(self, name=None, limit=20):
        """Hitta förlagor — de dokument agenten kan utgå från.

        Sökväg för AI-agenten: hellre denna än att gissa taggnamn. `name`
        filtrerar på filnamn (skiftlägesoberoende delsträng).
        """
        domain = [('active', '=', True)]
        if name:
            domain.append(('name', 'ilike', name))
        recs = self.search(domain)
        recs = recs.filtered('is_forlaga')
        return recs[:limit or 20]

    def _ai_forlaga_info(self):
        """Metadata om en förlaga — det agenten behöver för att välja.

        Inga bytes: filens innehåll hämtas med odoo_attach.
        """
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'extension': self.extension or '',
            'mimetype': self.mimetype or '',
            'size': self.size or 0,
            'directory': self.directory_id.name or '',
            'is_locked': bool(self.is_locked),
            'locked_by': self.locked_by.name if self.locked_by else '',
        }

    def _ai_check_editable(self):
        """Får agenten skriva till denna fil just nu?

        Incheckning (`locked_by`) betyder att en människa redigerar filen
        i Euro-Office. Att skriva då skulle tysta skriva över deras arbete.
        Returnerar (ok, orsak).
        """
        self.ensure_one()
        if self.is_locked and self.locked_by != self.env.user:
            return (False,
                    'Dokumentet är incheckat av %s'
                    % (self.locked_by.name or 'en annan användare'))
        return (True, '')

    # ── Källor ─────────────────────────────────────────────────────────
    #
    # `okf_body`  generisk: `name` (filnamnet). `path_json` är metadata
    #             om sökvägen, inte innehåll.
    # `okf_tags`  generisk: `tag_ids` (målmodellen dms.tag)
    # `okf_links` generisk: `directory_id` (dms.directory bär mixinen),
    #             `storage_id`, `locked_by` (res.users), `create_uid`

    def _okf_artifact_type(self):
        """Bryggans egen typ (okf-mixin D12)."""
        return 'dms_file'

    def _okf_dirty_fields(self):
        """Fält vars ändring gör OKF-fälten inaktuella.

        `content` ingår INTE: filens binärdata läses inte av källorna,
        så en ny filversion ska inte tvinga en omindexering av namnet.
        `size` och `checksum` är metadata som ändras vid varje uppladdning.
        """
        return {'name', 'directory_id', 'tag_ids', 'mimetype',
                'category_id', 'active'}

    def _okf_skip_reason(self):
        """Arkiverad fil = "tomt just nu", inte "tomt för alltid"."""
        return None

    # ── Registrering (okf-mixin D11) ───────────────────────────────────

    def _register_hook(self):
        """Registrera modellen för dirty-indexering.

        Registrering, inte överridning: `_okf_indexable_models()` är
        `@api.model` på en abstrakt modell (mätt på luke18 2026-09-22).
        """
        res = super()._register_hook()
        self.env['ai.okf.mixin']._okf_register_indexable('dms.file')
        return res
