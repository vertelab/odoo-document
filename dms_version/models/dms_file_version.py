# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import base64
import hashlib
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CONTENT_SOURCES = [
    ("form", "Form"),
    ("webdav", "WebDAV"),
    ("sftp", "SFTP"),
    ("api", "API"),
    ("pwa", "Mobile"),
    ("restore", "Restore"),
]


class DmsFileVersion(models.Model):
    """One stored snapshot of a dms.file's content.

    The content itself lives in an ir.attachment so versions follow the same
    storage backend as the file (fs_attachment_s3 when S3 is enabled).
    """

    _name = "dms.file.version"
    _description = "DMS File Version"
    _order = "version_number desc, id desc"

    file_id = fields.Many2one(
        "dms.file",
        string="File",
        required=True,
        ondelete="cascade",
        index=True,
    )
    version_number = fields.Integer(required=True, index=True)
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Stored Content",
        required=True,
        ondelete="restrict",
    )
    checksum = fields.Char(string="Checksum/SHA1", index=True)
    size = fields.Integer()
    mimetype = fields.Char()
    content_source = fields.Selection(
        CONTENT_SOURCES,
        string="Source",
        default="form",
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Saved By",
        default=lambda self: self.env.user,
    )
    note = fields.Char()
    name = fields.Char(related="file_id.name", store=False)

    _sql_constraints = [
        (
            "version_number_uniq",
            "unique(file_id, version_number)",
            "Version numbers must be unique per file.",
        ),
    ]

    @api.model
    def _next_version_number(self, file_id):
        """Return the next free version number for ``file_id``.

        Uses max() rather than a count so a pruned history never reuses a
        number that was handed out before.
        """
        self.env.cr.execute(
            "SELECT COALESCE(MAX(version_number), 0) FROM dms_file_version "
            "WHERE file_id = %s",
            (file_id,),
        )
        return (self.env.cr.fetchone()[0] or 0) + 1

    @api.model
    def _create_version(self, file_record, content_b64, source=None, note=None):
        """Store ``content_b64`` as a new version of ``file_record``.

        :param file_record: dms.file the version belongs to
        :param content_b64: base64 encoded bytes (as dms.file.content holds it)
        :param source: content_source selection key; falls back to the
                       ``dms_source`` context key, then ``form``
        :return: the created dms.file.version record, or empty recordset when
                 there is nothing to store
        """
        file_record.ensure_one()
        if not content_b64:
            return self.browse()
        source = source or self.env.context.get("dms_source") or "form"
        if source not in dict(CONTENT_SOURCES):
            source = "form"
        raw = base64.b64decode(content_b64)
        checksum = hashlib.sha1(raw).hexdigest()
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": "%s.v%s" % (file_record.name or "file",
                                        self._next_version_number(file_record.id)),
                    "datas": content_b64,
                    "mimetype": file_record.mimetype or "application/octet-stream",
                    "res_model": "dms.file",
                    "res_id": file_record.id,
                }
            )
        )
        return self.sudo().create(
            {
                "file_id": file_record.id,
                "version_number": self._next_version_number(file_record.id),
                "attachment_id": attachment.id,
                "checksum": checksum,
                "size": len(raw),
                "mimetype": file_record.mimetype or "application/octet-stream",
                "content_source": source,
                "user_id": self.env.user.id,
                "note": note,
            }
        )

    def _get_content(self):
        """Return this version's content as base64 bytes."""
        self.ensure_one()
        return self.attachment_id.datas

    def action_restore(self):
        """Restore this version onto its file.

        The content currently on the file is kept as a new version first, so a
        restore is never destructive.
        """
        self.ensure_one()
        file_record = self.file_id
        file_record.check_access("write")
        content = self._get_content()
        if not content:
            return False
        file_record.with_context(dms_source="restore").write({"content": content})
        return True
