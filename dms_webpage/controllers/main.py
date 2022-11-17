# Copyright 2020-2021 Tecnativa - Víctor Martínez
import base64

from odoo import _, http
from odoo.http import request

from odoo.addons.dms.controllers.portal import CustomerPortal

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError
import logging

_logger = logging.getLogger(__name__)


class ExtendDMSPortal(CustomerPortal):

    @http.route(["/my/dms/file/<int:dms_file_id>"], type="http", auth="public", website=True)
    def portal_my_dms_file(self, dms_file_id=False, access_token=None, **kw):
        access_token = access_token or request.httprequest.args.get('access_token')
        try:
            rec_sudo = self._document_check_access("dms.file", dms_file_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        values = {
            'dms_file': rec_sudo
        }
        return request.render("dms_webpage.portal_my_dms_file", values)
