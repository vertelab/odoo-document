# -*- coding: utf-8 -*-
"""dms.directory — OKF-indexerbar (dms_ai).

VARFÖR: en mapp är kunskap om kunskapen — dess namn och placering säger
vad som finns i den. En mappstruktur är ett innehållsförteckningsträd.

VAD SOM INDEXERAS: mappnamnet (`name`), föräldern (`parent_id`) och
taggarna (`tag_ids`).

Modellen äger sina KÄLLOR; `ai.okf.mixin` äger fälten och flaggan.
"""

from odoo import models, fields


class DmsDirectory(models.Model):
    _name = 'dms.directory'
    _inherit = ['dms.directory', 'ai.okf.mixin']

    # OKF-taggar: egen relationstabell.
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'dms_directory_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

    # ── Källor ─────────────────────────────────────────────────────────
    #
    # `okf_body`  generisk: `name` (mappnamnet)
    # `okf_tags`  generisk: `tag_ids` (målmodellen dms.tag)
    # `okf_links` generisk: `parent_id` (self-relation — mappträdet),
    #             `storage_id`, `group_ids`

    def _okf_artifact_type(self):
        """Bryggans egen typ (okf-mixin D12)."""
        return 'dms_directory'

    def _okf_dirty_fields(self):
        """Fält vars ändring gör OKF-fälten inaktuella.

        `parent_path` och `complete_name` är compute av `parent_id` och
        behöver inte listas. `count_*` är räknare.
        """
        return {'name', 'parent_id', 'tag_ids', 'storage_id',
                'category_id', 'active'}

    def _okf_skip_reason(self):
        """Arkiverad mapp = "tomt just nu", inte "tomt för alltid"."""
        return None

    # ── Registrering (okf-mixin D11) ───────────────────────────────────

    def _register_hook(self):
        """Registrera modellen för dirty-indexering."""
        res = super()._register_hook()
        self.env['ai.okf.mixin']._okf_register_indexable('dms.directory')
        return res
