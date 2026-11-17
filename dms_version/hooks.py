# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Give every existing dms.file an initial version.

    Runs as a post-init hook rather than in create(): _inverse_content already
    runs on create and would otherwise produce a version of every file the
    migration itself creates.

    Idempotent — files that already have versions are skipped, so re-running
    after an upgrade creates no duplicates.
    """
    env.cr.execute(
        """
        SELECT f.id
          FROM dms_file f
         WHERE NOT EXISTS (
                 SELECT 1 FROM dms_file_version v WHERE v.file_id = f.id)
        """
    )
    file_ids = [row[0] for row in env.cr.fetchall()]
    if not file_ids:
        _logger.info("dms_version: no files need an initial version")
        return

    version_model = env["dms.file.version"]
    created = 0
    skipped = 0
    for file_record in env["dms.file"].browse(file_ids):
        content = file_record.content
        if not content:
            skipped += 1
            continue
        version_model._create_version(
            file_record, content, source="form", note="Initial version"
        )
        created += 1
    _logger.info(
        "dms_version: created %s initial version(s), skipped %s empty file(s)",
        created,
        skipped,
    )
