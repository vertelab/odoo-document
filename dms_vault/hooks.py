# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""post_init_hook — refuse to install without a master key.

WHY INSTALLATION MUST FAIL: a vault module that installs without
``dms_vault_master_key`` is a module that looks ready and does nothing. The
first file written into a vault would then either raise deep inside
``ir.attachment`` (a stack trace nobody can act on) or, worse, be stored in
the clear if the check were ever softened. Failing at install time puts the
error in front of the person who can fix it, with the command that fixes it.
"""

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Verify the master key is configured; raise with the fix if it is not."""
    # Imported here and not at module level: the model module imports the
    # hook's constants, and a top-level import would be circular.
    from .models.dms_vault import get_master_key

    get_master_key(env)
    _logger.info(
        "dms_vault: master key found in the configuration, module is ready"
    )
