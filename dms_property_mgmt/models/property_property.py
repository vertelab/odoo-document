# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class Property(models.Model):
    _inherit = "property.property"

    doc_count = fields.Integer(compute='_compute_attached_docs_count', string="Number of documents attached")

    directory_count = fields.Integer(compute='_compute_linked_directories_count', string="Number of Directories")

    def _set_property_parent_dir(self):
        for rec in self:
            dms_directory_id = self.env["dms.directory"].search([
                ("name", "=", rec.name),
                ("is_root_directory", "=", False),
                ("res_id", "=", rec.id),
                ("model_id.model", "=", "property.property"),
            ], limit=1)
            if dms_directory_id:
                rec.has_property_parent_dir = True
            else:
                rec.has_property_parent_dir = False

    has_property_parent_dir = fields.Boolean(string="Has Parent Dir", compute=_set_property_parent_dir)

    def create_parent_dir(self):
        self.env["dms.directory"].create({
            'name': self.name,
            'parent_id': self.env["dms.directory"].search([
                ('model_id.model', '=', 'property.property'), ("res_id", "=", False)], limit=1).id,
            'model_id': self.env["ir.model"].search([
                ('model', '=', 'property.property')
            ], limit=1).id,
            'record_ref': "{},{}".format("property.property", self.id),
            'res_model': "property.property",
            'res_id': self.id,
        })

    def _compute_linked_directories_count(self):
        directory_id = self.env['dms.directory']
        for property in self:
            property.directory_count = directory_id.search_count([
                ('model_id.model', '=', 'property.property'), ('res_id', '=', property.id),
            ])

    def _compute_attached_docs_count(self):
        Document = self.env['dms.file']
        for property in self:
            property.doc_count = Document.search_count([
                ('res_model', '=', 'property.property'), ('res_id', '=', property.id),
            ])

    def action_view_dms_files(self):
        kanban_view = self.env.ref('dms.view_dms_file_kanban')

        domain = [
            ('res_model', '=', 'property.property'),
            ('res_id', 'in', self.ids),
        ]

        context_vals = {
            'default_directory_id': self.env["dms.directory"].search([("name", "=", self.name)]).id,
            'related_dir_ids': self.env["dms.directory"].search([
                ("model_id", "=", "property.property"),
                ("res_id", "=", self.id),
            ]).ids
        }

        return {
            'name': _('Files'),
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,list,form',
            'res_model': 'dms.file',
            'views': [(kanban_view.id, 'kanban'), (False, 'list'), (False, 'form')],
            'view_id': kanban_view.id,
            'target': 'self',
            'domain': domain,
            'context': context_vals
        }

    def action_view_dms_directory(self):
        kanban_view = self.env.ref('dms.view_dms_directory_kanban')

        dms_directory_id = self.env["dms.directory"].search([("name", "=", self.name)])
        if self.directory_count == 0:
            context_vals = {
                'default_parent_id': self.env["dms.directory"].search([
                    ('model_id.model', '=', 'property.property'), ("res_id", "=", False)
                ], limit=1).id,
                'default_model_id': self.env["ir.model"].search([
                    ('model', '=', 'property.property')
                ], limit=1).id,
                'default_record_ref': "{},{}".format("property.property", self.id),
                'default_res_model': "property.property",
                'special_res_id': self.id,
                'special': True,
                'related_dir_ids': self.env["dms.directory"].search([
                    ("model_id", "=", "property.property"),
                    ("res_id", "=", self.id),
                ]).ids
            }
        else:
            context_vals = {
                'default_parent_id': dms_directory_id.id,
                'default_model_id': dms_directory_id.model_id.id,
                'related_dir_ids': self.env["dms.directory"].search([
                    ("model_id", "=", "property.property"),
                    ("res_id", "=", self.id),
                ]).ids

            }
        return {
            'name': _('Directories'),
            'type': 'ir.actions.act_window',
            'view_mode': 'kanban,list,form',
            'res_model': 'dms.directory',
            'views': [(kanban_view.id, 'kanban'), (False, 'list'), (False, 'form')],
            'view_id': kanban_view.id,
            'target': 'self',
            'domain': [
                ('model_id.model', '=', 'property.property'),
                ('res_id', 'in', self.ids)
            ],
            'context': context_vals
        }



