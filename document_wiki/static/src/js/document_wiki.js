odoo.define('document_wiki.advanced_wiki_snippet',function(require) {
    'use strict';

    var core = require('web.core');
    var options = require('web_editor.snippets.options');
    var rpc = require('web.rpc');
    var wUtils = require('website.utils');
    var _t = core._t;

    var qweb = core.qweb;

    var publicWidget = require('web.public.widget');

    publicWidget.registry.advanced_wiki = publicWidget.Widget.extend({
        selector: '.s_wiki_section',
        xmlDependencies: ['/document_wiki/static/src/xml/document_wiki.xml'],
        disabledInEditableMode: false,

        init: function () {
            this._super.apply(this, arguments);
            let url = window.location.href
            this.url = url.substr(0, url.indexOf('#'))
        },


        start: function () {
            this._fetch()
            return this._super.apply(this, arguments);
        },

        _fetch: function () {
            const self = this;
            return this._rpc({
                route: '/website/wiki/pages',
                params: {current_url: self.url}
            }).then(res => {
                self._render(res)

            });
        },

        _render: function (res) {
            this.$(".document_wiki_pages_list").replaceWith(
                $(qweb.render('document_wiki.wiki_pages', res))
            )
        }
    })
});
