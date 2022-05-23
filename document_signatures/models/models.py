# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)
import requests
import werkzeug
from odoo.http import request
import json
import base64
from odoo.exceptions import UserError
from datetime import datetime
import uuid

    
class DmsAddApproverWizard(models.TransientModel):
    _name = "dms.approver.add.wizard"
    _description = "DMS Approval Wizard"

    def _get_document(self):
        document = self.env["dms.file"].browse(self.env.context.get('active_ids'))
        return document

    @api.model
    def _get_approvers_domain(self):
        group_ids = []
        group_ids.append(self.env.ref('res_user_groups_skogsstyrelsen.group_sks_signerare').id)
        offlimit_ids = [i.id for i in self.env["dms.file"].browse(self.env.context.get('active_ids')).approval_ids]
        return [('groups_id', 'in', group_ids), ('id', 'not in', offlimit_ids)]

    document = fields.Many2one(comodel_name='dms.file', string='Document', default=_get_document, readonly=True)
    user_id = fields.Many2one(comodel_name='res.users', string='Approver to add', domain= _get_approvers_domain)

    def set_approver(self):
        line = self.env["dms.approval.line"].create({'approver_id': self.user_id.id, 'document_id': self.document.id, 'approval_status': False})
        self.document.write({'approval_ids': [(4, line.id, 0)]})


class SignportRequest(models.TransientModel):
    _name = 'signport.request'
    _description = "Sign Port Request"

    relay_state = fields.Char()
    eid_sign_request = fields.Char()
    binding = fields.Char()
    signing_service_url = fields.Char()

    def apply_configuration(self):
        """Function for applying the approval configuration"""
        return True


class DmsApproval(models.Model):
    _name = 'dms.approval'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Document Approval'

    name = fields.Char(default='Approval Configuration')
    approve_customer_document = fields.Boolean(string="Approval on Documents",
                                              help='Enable this field for adding the approvals for the documents')
    document_approver_ids = fields.Many2many('res.users', 'document_id', string='Document Approver', domain=lambda self: [
        ('groups_id', 'in', self.env.ref('base.group_user').id)],
                                            help='In this field you can add the approvers for the document')

    def apply_configuration(self):
        """Function for applying the approval configuration"""
        return True


class DmsApprovalLine(models.Model):
    _name = 'dms.approval.line'
    _description = 'Approval line in document'

    document_id = fields.Many2one('dms.file', readonly=0)
    approver_id = fields.Many2one('res.users', string='Approver', readonly=1)
    approval_status = fields.Boolean(string='Status', readonly=1)
    signed_document = fields.Binary(string='Signed Document', readonly=1)
    signer_ca = fields.Binary(string='Signer Ca', readonly=1)
    assertion = fields.Binary(string='Assertion', readonly=1)
    relay_state = fields.Binary(string='Relay State', readonly=1)
    signed_on = fields.Datetime(string='Signed on')
    
    
class Project(models.Model):
    _inherit = "project.project"

    document_ids = fields.One2many(comodel_name='dms.file', inverse_name='project_id', string='Documents')
    

class DmsFile(models.Model):
    _inherit = "dms.file"

    document_fully_approved = fields.Boolean(compute='_compute_document_fully_approved')
    check_approve_ability = fields.Boolean(compute='_compute_check_approve_ability')
    approval_ids = fields.One2many('dms.approval.line', 'document_id')
    is_approved = fields.Boolean(compute='_compute_is_approved')
    document_locked = fields.Boolean()
    show_on_customer_portal = fields.Boolean(string="Show on Customer Portal")
    signed_document = fields.Binary(string='Signed Document', readonly=1)
    signed_by = fields.Many2one(comodel_name='res.users', string='Signed by')
    signed_on = fields.Datetime(string='Signed on')
    signer_ca = fields.Binary(string='Signer Ca', readonly=1)
    assertion = fields.Binary(string='Assertion', readonly=1)
    relay_state = fields.Binary(string='Relay State', readonly=1)
    page_visibility = fields.Boolean(compute='_compute_page_visibility')
    project_id = fields.Many2one(comodel_name='project.project', string='Project')
    requires_customer_signature = fields.Boolean(string='Requires customer signature', default=False)
    
    @api.depends('directory_id')
    def _compute_project_id(self):
        for document in self:
            _logger.warning("#"*99)
            _logger.warning(document.directory_id.model_id.model)
            if document.project_id:
                _logger.info("Project id already set")
            elif document.directory_id.model_id.model == "project.project":
                _logger.warning(document.directory_id.record_ref)
                document.project_id = document.record_ref


    @api.depends('approval_ids')
    def _compute_page_visibility(self):
        """Compute function for making the approval page visible/invisible"""
        if self.approval_ids:
            self.page_visibility = True
        else:
            self.page_visibility = False

    def document_approve(self):
        """This is the function of the approve button also
        updates the approval table values according to the
        approval of the users"""
        self.ensure_one()
        _logger.warning("hej"*999)
        _logger.warning(f"{self.record_ref=}")
        current_user = self.env.uid
        for approval_id in self.approval_ids:
            if current_user == approval_id.approver_id.id:
                signport = self.env.ref("rest_signport.api_signport")
                data = json.loads(request.httprequest.data)
                access_token=data.get("params", {}).get("access_token")
                res = signport.sudo().post_sign_document(
                    ssn=self.env.user.partner_id.social_sec_nr and self.env.user.partner_id.social_sec_nr.replace("-", "") or False,
                    document_id=self.id,
                    directory_id=self.directory_id,
                    access_token=access_token,
                    message="Signering av dokument",
                    sign_type="employee",
                    approval_id=approval_id.id
                )
                _logger.warning(res)
                base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
                signport_request = self.env["signport.request"].sudo().create({
                    'relay_state': res['relayState'],
                    'eid_sign_request': res['eidSignRequest'],
                    'binding': res['binding'],
                    'signing_service_url': res['signingServiceUrl']
                })
                return {
                    'type': 'ir.actions.act_url',
                    'target': 'self',
                    'url': f"{base_url}/web/signport_form/document/{self.id}/{signport_request.id}/start_sign",
                }

    def document_unlock(self):
        self.document_locked = False
        for signature in self.approval_ids:
            signature.write({'approval_status': False, 'signed_document': None, 'signer_ca': None, 'assertion': None, 'relay_state': None, 'signed_on': False})
        self.signed_document = False

    @api.depends('approval_ids.approver_id')
    def _compute_check_approve_ability(self):
        """This is the compute function which check the current
        logged in user is eligible or not for approving the document"""
        current_user = self.env.uid
        approvers_list = []
        for approver in self.approval_ids:
            approvers_list.append(approver.approver_id.id)
        if current_user in approvers_list:
            self.check_approve_ability = True
        else:
            self.check_approve_ability = False

    def _compute_is_approved(self):
        """In this compute function we are verifying whether the document
        is approved/not approved by the current logged in user"""
        current_user = self.env.uid
        if self.content and self.approval_ids:
            for approval_id in self.approval_ids:
                if current_user == approval_id.approver_id.id:
                    if approval_id.approval_status:
                        self.is_approved = True
                        break
                    else:
                        self.is_approved = False
                else:
                    self.is_approved = False
        else:
            self.is_approved = False

    @api.depends('approval_ids')
    def _compute_document_fully_approved(self):
        """This is the compute function which verifies whether
        the document is completely approved or not"""
        approval_ids = self.approval_ids
        approve_lines = approval_ids.filtered(lambda item: item.approval_status)
        if len(approve_lines) == len(approval_ids):
            self.document_fully_approved = True
        else:
            self.document_fully_approved = False


class RestApiSignport(models.Model):
    _inherit = "rest.api"

    def post_sign_document(self, ssn, document_id, directory_id, access_token, message=False, sign_type="customer", approval_id=False):
        # export_wizard = self.env['xml.export'].with_context({'active_model': 'sale.order', 'active_ids': order_id}).create({})
        # action = export_wizard.download_xml_export()
        # self.env['ir.attachment'].browse(action['res_id']).update({'res_id': order_id, 'res_model': 'sale.order'})

        document = (self.env["dms.file"].sudo().browse(document_id))
        if not document:
            return False
        # TODO: attach pdf or xml of order to the request

        if self.env['dms.file'].browse(document_id).signed_document:
            document_content = self.env['dms.file'].browse(document_id).signed_document.decode()
        else:
            document_content = document.content.decode()
        _logger.warning(f"document content: {document_content}")

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json; charset=utf8",
        }
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        if sign_type == "customer":
            response_url = f"{base_url}/my/dms/file/{document_id}/{directory_id}/sign_complete?access_token={access_token}"
        elif sign_type == "employee":
            response_url = f"{base_url}/web/document/{document_id}/{approval_id}/sign_complete?access_token={access_token}"
        _logger.warning("before add signature page")
        guid = str(uuid.uuid1())
        _logger.warning(f" {guid}")
        add_signature_page_vals = {
        "clientCorrelationId": guid,
        "documents": [
            {
            "content": document_content,
            "signaturePageTemplateId": "e33d2a21-1d23-4b4f-9baa-def11634ceb4",
            "signaturePagePosition": "last",
            }
        ]
        }

        res = self.call_endpoint(
            method="POST",
            endpoint_url="/AddSignaturePage",
            headers=headers,
            data_vals=add_signature_page_vals,
        )
        _logger.warning(f"resresres: {res}")
        document_content = res['documents'][0]['content']
        role = _("Unknown")
        if sign_type == "customer":
            role = self.customer_string
        elif sign_type == "employee":
            role = self.employee_string

        get_sign_request_vals = {
            "username": f"{self.user}",
            "password": f"{self.password}",
            "spEntityId": f"{self.sp_entity_id}",  # "https://serviceprovider.com/", # lägg som inställning på rest api
            "idpEntityId": f"{self.idp_entity_id}",  # "https://eid.test.legitimeringstjanst.se/sc/mobilt-bankid/",# lägg som inställning på rest api
            "signResponseUrl": response_url,
            "signatureAlgorithm": f"{self.signature_algorithm}",  # "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",# lägg som inställning på rest api
            "loa": f"{self.loa}",  # "http://id.swedenconnect.se/loa/1.0/uncertified-loa3",# lägg som inställning på rest api
            "certificateType": "PKC",
            "signingMessage": {
                "body": f"{message}",
                "mustShow": True,
                "encrypt": True,
                "mimeType": "text",
            },
            "document": [
                {
                    "mimeType": document.mimetype,  # TODO: check mime type
                    "content": document_content,  # TODO: include document to sign
                    "fileName": document.display_name,  # TODO: add filename
                    # "encoding": False  # TODO: should we use this?
                    "documentName": document.display_name,  # TODO: what is this used for?
                    "adesType": "bes",  # TODO: what is "ades"? "bes" or "none"
                }
            ],
            "requestedSignerAttribute": [
                {
                    "name": "urn:oid:1.2.752.29.4.13",  # swedish "personnummer", hardcoded
                    "type": "xsd:string",
                    "value": f"{ssn}",
                }
            ],
            "signaturePage": {
                "initialPosition": "last",
                "templateId": "e33d2a21-1d23-4b4f-9baa-def11634ceb4",
                "allowRemovalOfExistingSignatures": False,
                "signerAttributes": [{
                    "label": _("Role"),
                    "value": role
                },
                {
                    "label": _("Namn"),
                    "value": self.env.user.name
                }
                ],
                "signatureTitle": "Signed by",
            },
        }
        res = self.call_endpoint(
            method="POST",
            endpoint_url="/GetSignRequest",
            headers=headers,
            data_vals=get_sign_request_vals,
        )
        return res

    def document_signport_post(self, data_vals={}, document_id=False, endpoint=False, sign_type="customer"):
        _logger.warning("document_signport_post"*99)
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json; charset=utf8",
        }
        _logger.warning("signport post"*99)
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        data_vals["username"] = f"{self.user}"
        data_vals["password"] = f"{self.password}"
        res = self.call_endpoint(
            method="POST",
            endpoint_url=endpoint,
            headers=headers,
            data_vals=data_vals,
        )
        _logger.warning(f"FINAL res: {res}")
        if not res['status']['success']:
            if 'not valid personal number' in res['status']['statusCodeDescription']:
                raise UserError('Invalid Personalnumber, please format it like "YYYYMMDDXXXX"')
            else:
                raise UserError(res)

        # username = self.env.user.name
        # document = (
        #     self.env["ir.attachment"]
        #     .sudo()
        #     .search(
        #         [
        #             ("res_model", "=", "dms.file"),
        #             ("res_id", "=", document_id),
        #             ("mimetype", "=", "application/pdf"),
        #             ("name", "=", f"{self.env['dms.file'].browse(document_id).name}.pdf")
        #         ],
        #         limit=1,
        #     )
        # )
        if sign_type == "employee":
            _logger.warning("if"*99)
            self.env['dms.file'].browse(document_id).signed_document = res["document"][0]["content"]
            approval_line = self.env["dms.approval.line"].search([("document_id", "=", document_id), ("approver_id", "=", self.env.uid)], limit=1)
            approval_line.signed_on = fields.Datetime.now()
            approval_line.signed_document = res["document"][0]["content"]
            approval_line.signer_ca = res["signerCa"]
            approval_line.assertion = res["assertion"]
            approval_line.relay_state = base64.b64encode(res["relayState"].encode())
            approval_line.approval_status = True
        elif sign_type == "customer":
            _logger.warning("else"*99)
            document = self.env['dms.file'].browse(document_id)
            _logger.warning(f"{document=}, {self.env.user.id=}, {fields.datetime.now()=}")
            document.signed_by = self.env.user.id
            document.signed_on = fields.datetime.now()
            document.signed_document = res["document"][0]["content"]
            document.signer_ca = res["signerCa"]
            document.assertion = res["assertion"]
            document.relay_state = base64.b64encode(res["relayState"].encode())

        return res
