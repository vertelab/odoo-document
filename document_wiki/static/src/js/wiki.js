odoo.define('document_wiki.wiki_snippet',function(require) {
    'use strict';

    var core = require('web.core');
    var options = require('web_editor.snippets.options');
    var rpc = require('web.rpc');
    var wUtils = require('website.utils');
    var _t = core._t;

    var publicWidget = require('web.public.widget');

    publicWidget.registry.visitor = publicWidget.Widget.extend({
        selector: ".oe_wiki_pages",
        disabledInEditableMode: false,

        start: function () {
            let url = window.location.href
            url = url.substr(0, url.indexOf('#'))
            var defs = [this._super.apply(this, arguments)];
            var self = this;
            var $wikiList = this.$('.document_wiki_pages_list');
            this._originalContent = $wikiList[0].outerHTML;
            defs.push(this._rpc({route: '/website/wiki/pages', params: {current_url: url}}).then(function (data) {
                if (data) {
                    self._$loadedContent = $(data);

                    self._$loadedContent.attr('contentEditable', false);
                    self._$loadedContent.addClass('o_temp_auto_element');
                    self._$loadedContent.attr('data-temp-auto-element-original-content', self._originalContent);

                    $wikiList.replaceWith(self._$loadedContent);

                }
            }))
            return Promise.all(defs);
        },

        destroy: function () {
            this._super.apply(this, arguments);
            if (this._$loadedContent) {
            //     this._$loadedContent.replaceWith(this._originalContent);
            }
        },
    })
})
