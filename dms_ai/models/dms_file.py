# -*- coding: utf-8 -*-
"""dms.file — OKF-indexerbar (dms_ai).

VARFÖR: ett dokument ÄR kunskap — det är hela poängen med att spara det.
Ändå ligger det i en Binary-kolumn som varken BM25 eller embeddings ser.

VAD SOM INDEXERAS: filnamnet (`name`), mappen (`directory_id`) och
taggarna (`tag_ids`). Filens INNEHÅLL kräver textutvinning (PDF, DOCX)
och är en separat uppgift — den generiska kroppskällan rör inte Binary.

Modellen äger sina KÄLLOR; `ai.okf.mixin` äger fälten och flaggan.
"""

from odoo import models, fields


class DmsFile(models.Model):
    _name = 'dms.file'
    _inherit = ['dms.file', 'ai.okf.mixin']

    # OKF-taggar: egen relationstabell (en many2many kan inte ligga
    # pa en abstrakt mixin — den ger samma tabell for alla arvande).
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'dms_file_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

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
