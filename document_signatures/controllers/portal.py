# Copyright 2020-2021 Tecnativa - Víctor Martínez
import base64

from odoo import _, http
from odoo.http import request
from odoo.osv.expression import OR

# from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.dms.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.main import content_disposition, ensure_db




from odoo import fields, http, _
import json
from odoo.exceptions import AccessError, MissingError
import binascii
from odoo.osv import expression
import logging
_logger = logging.getLogger(__name__)

class ExtendCustomerPortal(CustomerPortal):

    @http.route(
        ["/my/dms/directory/<int:dms_directory_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_dms_directory(
        self,
        dms_directory_id=False,
        sortby=None,
        filterby=None,
        search=None,
        search_in="name",
        access_token=None,
        **kw
    ):
        ensure_db()
        # operations
        searchbar_sortings = {"name": {"label": _("Name"), "order": "name asc"}}
        # default sortby br
        if not sortby:
            sortby = "name"
        sort_br = searchbar_sortings[sortby]["order"]
        # search
        searchbar_inputs = {
            "name": {"input": "name", "label": _("Name")},
        }
        if not filterby:
            filterby = "name"
        # domain
        domain = [("is_hidden", "=", False), ("parent_id", "=", dms_directory_id)]
        # search
        if search and search_in:
            search_domain = []
            if search_in == "name":
                search_domain = OR([search_domain, [("name", "ilike", search)]])
            domain += search_domain
        # content according to pager and archive selected
        if access_token:
            dms_directory_items = (
                request.env["dms.directory"].sudo().search(domain, order=sort_br)
            )
        else:
            dms_directory_items = request.env["dms.directory"].search(
                domain, order=sort_br
            )
        request.session["my_dms_folder_history"] = dms_directory_items.ids
        res = self._dms_check_access("dms.directory", dms_directory_id, access_token)
        if not res:
            if access_token:
                return request.redirect("/")
            else:
                return request.redirect("/my")
        dms_directory_sudo = res
        # dms_files_count
        domain = [
            ("is_hidden", "=", False),
            ("directory_id", "=", dms_directory_id),
            ("project_id.partner_id", "=", request.env.user.partner_id.id),
            ("show_on_customer_portal", "=", True)
        ]
        # search
        if search and search_in:
            search_domain = []
            if search_in == "name":
                search_domain = OR([search_domain, [("name", "ilike", search)]])
            domain += search_domain
        # items
        if access_token:
            dms_file_items = (
                request.env["dms.file"].sudo().search(domain, order=sort_br)
            )
        else:
            dms_file_items = request.env["dms.file"].search(domain, order=sort_br)
        request.session["my_dms_file_history"] = dms_file_items.ids
        dms_parent_categories = dms_directory_sudo.sudo()._get_parent_categories(
            access_token
        )
        # values
        values = {
            "dms_directories": dms_directory_items,
            "page_name": "dms_directory",
            "default_url": "/my/dms",
            "searchbar_sortings": searchbar_sortings,
            "searchbar_inputs": searchbar_inputs,
            "search_in": search_in,
            "sortby": sortby,
            "filterby": filterby,
            "access_token": access_token,
            "dms_directory": dms_directory_sudo,
            "dms_files": dms_file_items,
            "dms_parent_categories": dms_parent_categories,
        }
        return request.render("dms.portal_my_dms", values)

    @http.route(
        ["/my/dms/file/<int:dms_file_id>/download"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_dms_file_download(self, dms_file_id, access_token=None, **kw):
        """Process user's consent acceptance or rejection."""
        ensure_db()
        # operations
        res = self._dms_check_access("dms.file", dms_file_id, access_token)
        if not res:
            if access_token:
                return request.redirect("/")
            else:
                return request.redirect("/my")

        dms_file_sudo = res
        # It's necessary to prevent AccessError in ir_attachment .check() function
        if dms_file_sudo.attachment_id and request.env.user.has_group(
            "base.group_portal"
        ):
            dms_file_sudo = dms_file_sudo.sudo()
        if dms_file_sudo.signed_document:
            filecontent = base64.b64decode(dms_file_sudo.signed_document)
        else:
            filecontent = base64.b64decode(dms_file_sudo.content)
        content_type = ["Content-Type", "application/octet-stream"]
        disposition_content = [
            "Content-Disposition",
            content_disposition(dms_file_sudo.name),
        ]
        return request.make_response(filecontent, [content_type, disposition_content])

    def _document_get_page_view_values(self, order, access_token, **kwargs):
        _logger.warning("1"*999)
        values = {
            "sale_order": order,
            "token": access_token,
            "return_url": "/shop/payment/validate",
            "bootstrap_formatting": True,
            "partner_id": order.partner_id.id,
            "report_type": "html",
            "action": order._get_portal_return_action(),
        }
        if order.company_id:
            values["res_company"] = order.company_id

        if order.has_to_be_paid():
            domain = expression.AND(
                [
                    [
                        "&",
                        ("state", "in", ["enabled", "test"]),
                        ("company_id", "=", order.company_id.id),
                    ],
                    [
                        "|",
                        ("country_ids", "=", False),
                        ("country_ids", "in", [order.partner_id.country_id.id]),
                    ],
                ]
            )
            acquirers = request.env["payment.acquirer"].sudo().search(domain)

            values["acquirers"] = acquirers.filtered(
                lambda acq: (acq.payment_flow == "form" and acq.view_template_id)
                or (acq.payment_flow == "s2s" and acq.registration_view_template_id)
            )
            values["pms"] = request.env["payment.token"].search(
                [("partner_id", "=", order.partner_id.id)]
            )
            values["acq_extra_fees"] = acquirers.get_acquirer_extra_fees(
                order.amount_total, order.currency_id, order.partner_id.country_id.id
            )

        if order.state in ("draft", "sent", "cancel"):
            history = request.session.get("my_quotations_history", [])
        else:
            history = request.session.get("my_orders_history", [])
        values.update(get_records_pager(history, order))

        return values

    def get_signport_api(self):
        return request.env.ref("rest_signport.api_signport")

    @http.route(
        ["/my/dms/file/<int:document_id>/sign_complete"],
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        website=True,
    )
    def complete_signing(self, document_id, access_token, **res):
        _logger.warning("2"*999)
        html_form = base64.b64decode(res.get("EidSignResponse")).decode()
        data = {
            "relayState": res["RelayState"],
            "eidSignResponse": res["EidSignResponse"],
            "binding": res["Binding"],
        }
        _logger.warning("complete_signing controller"*99)
        api_signport = self.get_signport_api()
        res = api_signport.sudo().signport_post(data, document_id, "/CompleteSigning")
        res_json = json.dumps(res)
        try:
            document_sudo = request.env["dms.file"].sudo().browse(document_id)
        except (AccessError, MissingError):
            return request.redirect("/my")

        # use sudo to allow accessing/viewing orders for public user
        # only if he knows the private token
        # Log only once a day
        if document_sudo:
            # store the date as a string in the session to allow serialization
            now = fields.Date.today().isoformat()
            session_obj_date = request.session.get("view_quote_%s" % document_sudo.id)
            if session_obj_date != now and request.env.user.share and access_token:
                request.session["view_quote_%s" % document_sudo.id] = now
                # body = _("Quotation viewed by customer %s", order_sudo.partner_id.name)
                # _message_post_helper(
                #     "sale.order",
                #     order_sudo.id,
                #     body,
                #     token=order_sudo.access_token,
                #     message_type="notification",
                #     subtype_xmlid="mail.mt_note",
                #     partner_ids=order_sudo.user_id.sudo().partner_id.ids,
                # )

        values = self._order_get_page_view_values(document_sudo, access_token, **res)
        # values['message'] = message

        return request.render("sale.sale_order_portal_template", values)

    @http.route(
        ["/my/dms/file/<int:document_id>/sign_start"],
        type="json",
        auth="public",
        website=True,
        methods=["POST"],
    )
    def start_sign(self, document_id):
        _logger.warning("3"*999)
        data = json.loads(request.httprequest.data)
        ssn = data.get("params", {}).get("ssn")
        if not ssn:
            return False
        api_signport = self.get_signport_api()
        res = api_signport.sudo().post_sign_document(
            ssn=ssn,
            document_id=document_id,
            access_token=data.get("params", {}).get("access_token"),
            message="Signering av dokument",
        )
        res_json = json.dumps(res)
        return res_json
