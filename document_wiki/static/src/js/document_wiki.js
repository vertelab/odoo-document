odoo.define('document_wiki.advanced_wiki_snippet', function (require) {
    'use strict';

    var core = require('web.core');

    var qweb = core.qweb;

    var publicWidget = require('web.public.widget');

    publicWidget.registry.advanced_wiki = publicWidget.Widget.extend({
        selector: '.oe_wiki_pages',
        // xmlDependencies: ['/document_wiki/static/src/xml/document_wiki.xml'],
        disabledInEditableMode: false,

        init: function () {
            this._super.apply(this, arguments);
            this.url = window.location.href
        },


        start: function () {
            this._render_posts()
            return this._super.apply(this, arguments);
        },
        _render_posts: function () {
            var self = this;
            const data = self.$target[0].dataset;
            // Implimpent const depth = parseInt(data.treeDepth) || 4;
            const template = data.template || '';
            const order = data.order || '';

            self.$target.empty();
            self.$target.attr('contenteditable', 'False');

            var prom = new Promise(function (resolve) {
                self._rpc({
                    route: '/website/wiki/render_wiki_pages',
                    params: {
                        current_url: self.url,
                        template: template,
                        order: order
                    }
                }).then(function (posts) {
                    self.$target.html(posts)
                    resolve()
                })
            })
        },
    })
});
