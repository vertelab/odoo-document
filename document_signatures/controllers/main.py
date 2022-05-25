from odoo import fields, http, _
from odoo.http import request
import json
import logging
import base64
from odoo.exceptions import AccessError, MissingError
import binascii
from odoo.addons.payment.controllers.portal import PaymentProcessing
from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.osv import expression
from odoo.addons.portal.controllers.portal import (
    CustomerPortal,
    pager as portal_pager,
    get_records_pager,
)


_logger = logging.getLogger(__name__)


class DocumentMultiApproval(http.Controller):

    @http.route(['/web/signport_form/document/<int:document_id>/<int:signport_id>/start_sign'], 
        type='http', 
        auth="none",
    )
    def start_sign(self, document_id, signport_id, **kw):

        signport_request = request.env["signport.request"].sudo().browse(signport_id)
        values = {
            'relay_state': signport_request.relay_state,
            'eid_sign_request': signport_request.eid_sign_request,
            'binding': signport_request.binding,
            'signing_service_url': signport_request.signing_service_url,
        }
        _logger.warning(f"/web/signport_form/document/<int:document_id>/<int:signport_id>/start_sign {values=}")
        return request.render("document_signatures.signport_form", values)



    @http.route(
        ["/web/document/<int:document_id>/<int:approval_id>/sign_complete"],
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        website=True,
    )
    def complete_signing(self, document_id, approval_id, **res):
        data = {
            "relayState": res["RelayState"],
            "eidSignResponse": res["EidSignResponse"],
            "binding": res["Binding"],
        }
        _logger.warning("complete"*999)

        api_signport = request.env.ref("rest_signport.api_signport")
        res = api_signport.sudo().document_signport_post(data, document_id, "/CompleteSigning", sign_type="employee")
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return request.redirect(f"{base_url}/web#id={document_id}&model=dms.file&view_type=form")
