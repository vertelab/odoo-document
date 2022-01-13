import base64
import datetime
import json
import os
import logging

import odoo

from odoo import http, models, fields, _
from odoo.http import request
from odoo.tools import OrderedSet
from odoo.addons.http_routing.models.ir_http import slug, slugify, _guess_mimetype
from odoo.addons.web.controllers.main import Binary
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.website.controllers.main import Website

logger = logging.getLogger(__name__)


class WikiDoc(http.Controller):

    @http.route('/website/wiki/pages', type='json', auth="public", website=True)
    def website_wiki(self, **kwargs):
        base_url = request.env['ir.config_parameter'].get_param('web.base.url')
        sub_url = kwargs.get('current_url').split(base_url)[1]
        current_website_id = request.website
        page_id = request.env['website.page'].search([
            ('url', '=', sub_url),
            ('website_id', '=', current_website_id.id)
        ], limit=1)
        print(page_id)
        result = {'wiki_pages': []}
        if page_id and page_id.wiki_ids:
            for wiki_page in page_id.wiki_ids:
                # result['wiki_pages'].append(wiki_page)
                result['wiki_pages'].append({
                    'url': wiki_page.page_id.url,
                    'name': wiki_page.page_id.name,
                })
        return request.env['ir.ui.view']._render_template("document_wiki.s_document_wiki_pages_list", result)
