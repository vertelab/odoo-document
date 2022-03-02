from odoo import models, fields, api, _


class WebsitePage(models.Model):
    _inherit = 'website.page'

    wiki_ids = fields.One2many('wiki.page', 'parent_id', string="Wiki Page")


class WikiPages(models.Model):
    _name = 'wiki.page'
    _rec_name = 'page_id'

    page_id = fields.Many2one('website.page', string="Child Page")
    parent_id = fields.Many2one('website.page', string="Main Page")
