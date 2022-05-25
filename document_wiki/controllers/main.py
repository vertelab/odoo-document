import base64
import datetime
import json
import os
import re
import logging
import werkzeug.urls
import werkzeug.utils
import werkzeug.wrappers

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
        sub_url = re.split("(?<=[a-z,0-9])/{1}", kwargs.get('current_url'))[1]
        current_website_id = request.website
        page_id = request.env['website.page'].search([
            ('url', '=', f'/{sub_url}'),
            ('website_id', '=', current_website_id.id)
        ], limit=1)
        result = {'wiki_pages': []}
        if page_id and page_id.wiki_ids:
            for wiki_page in page_id.wiki_ids:
                result['wiki_pages'].append({
                    'url': wiki_page.page_id.url,
                    'name': wiki_page.page_id.name,
                })
        return result

    @http.route(['/website/wiki/render_wiki_pages'], type='json', auth='public', website=True)
    def render_latest_posts(self, template, order, **kwargs):
        sub_url = re.split("(?<=[a-z,0-9])/{1}", kwargs.get('current_url'))[1]
        if '#' in sub_url:
            sub_url = sub_url.replace('#', '');
        current_website_id = request.website
        page_id = request.env['website.page'].search([
            ('url', '=', f'/{sub_url}'),
            ('website_id', '=', current_website_id.id)
        ], limit=1)
        pages = page_id.wiki_ids.page_id
        return request.website.viewref(template)._render({'pages': pages})


class NewPage(Website):

    @http.route(['/website/add/', '/website/add/<path:path>'], type='http', auth="user", website=True, methods=['POST'])
    def pagenew(self, path="", noredirect=False, add_menu=False, parent_page_id=False, template=False, **kwargs):
        # for supported mimetype, get correct default template
        _, ext = os.path.splitext(path)
        ext_special_case = ext and ext in _guess_mimetype() and ext != '.html'

        if not template and ext_special_case:
            default_templ = 'website.default_%s' % ext.lstrip('.')
            if request.env.ref(default_templ, False):
                template = default_templ

        template = template and dict(template=template) or {}
        page = request.env['website'].new_page(path, add_menu=add_menu, **template)

        # current page
        current_page_id = request.env['website.page'].search([('view_id', '=', page.get('view_id'))])
        if current_page_id and parent_page_id:
            request.env['wiki.page'].create({
                'parent_id': parent_page_id,
                'page_id': current_page_id.id
            })

        url = page['url']
        if noredirect:
            return werkzeug.wrappers.Response(url, mimetype='text/plain')

        if ext_special_case:  # redirect non html pages to backend to edit
            return werkzeug.utils.redirect('/web#id=' + str(page.get('view_id')) + '&view_type=form&model=ir.ui.view')
        return werkzeug.utils.redirect(url + "?enable_editor=1")
