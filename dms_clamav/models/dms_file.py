# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import base64
import logging

from odoo import api, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DmsFile(models.Model):
    _inherit = "dms.file"

    def _clamav_config(self):
        """Return (host, port) for clamd, from the system parameters."""
        icp = self.env["ir.config_parameter"].sudo()
        host = icp.get_param("dms_clamav.host", "localhost")
        port = int(icp.get_param("dms_clamav.port", "3310") or 3310)
        return host, port

    @api.model
    def _clamav_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "dms_clamav.enabled", "True"
        ) in ("True", "true", "1")

    @api.model
    def _clamav_scan(self, data):
        """Scan ``data`` and return the signature name, or None if clean.

        Returns None as well when clamd cannot be reached - the caller decides
        what that means. Raises nothing for a transport problem: fail-open is a
        documented choice, and an exception here would take the whole DMS down
        whenever ClamAV restarts.
        """
        if not data:
            return None
        try:
            import clamd  # lazy: optional dependency
        except ImportError:
            _logger.warning(
                "dms_clamav: the clamd python package is not installed - "
                "skipping scan (fail-open)"
            )
            return None
        host, port = self._clamav_config()
        try:
            client = clamd.ClamdNetworkSocket(host=host, port=port, timeout=30)
            result = client.instream(data)
        except Exception as error:  # noqa: BLE001 - fail-open by design
            _logger.warning(
                "dms_clamav: clamd at %s:%s unavailable (%s) - "
                "storing without scan (fail-open)",
                host,
                port,
                error,
            )
            return None
        # clamd returns {'stream': ('OK', None)} or {'stream': ('FOUND', 'Name')}
        status, signature = (result or {}).get("stream", (None, None))
        if status == "FOUND":
            return signature or "unknown"
        return None

    def write(self, vals):
        """Scan before storing, so an infected file is never persisted.

        Placed before super().write() and therefore before dms_version's
        snapshot: an infected file must not become a version either. The
        content is still in memory here, which is the only point where the
        bytes can be inspected without reading them back from storage.
        """
        if vals.get("content") and self._clamav_enabled():
            raw = base64.b64decode(vals["content"])
            signature = self._clamav_scan(raw)
            if signature:
                for record in self:
                    _logger.error(
                        "dms_clamav: REJECTED file '%s' (id=%s) uploaded by "
                        "%s (uid=%s): %s",
                        record.name,
                        record.id,
                        self.env.user.login,
                        self.env.uid,
                        signature,
                    )
                raise ValidationError(
                    "The file was rejected by the virus scanner: %s" % signature
                )
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        """Scan on create too - a new file is a write path as well."""
        if self._clamav_enabled():
            for vals in vals_list:
                if not vals.get("content"):
                    continue
                signature = self._clamav_scan(base64.b64decode(vals["content"]))
                if signature:
                    _logger.error(
                        "dms_clamav: REJECTED new file '%s' uploaded by %s "
                        "(uid=%s): %s",
                        vals.get("name"),
                        self.env.user.login,
                        self.env.uid,
                        signature,
                    )
                    raise ValidationError(
                        "The file was rejected by the virus scanner: %s"
                        % signature
                    )
        return super().create(vals_list)
