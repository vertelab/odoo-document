odoo.define('document_wiki.new.menu',function(require) {
    'use strict';

    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var websiteNavbarData = require('website.navbar');
    var wUtils = require('website.utils');
    var tour = require('web_tour.tour');

    var qweb = core.qweb;
    var _t = core._t;

    var NewContentMenu = require('website.newMenu');

    var websiteNavbarData = require('website.navbar');

    NewContentMenu.include({
        xmlDependencies: (NewContentMenu.prototype.xmlDependencies || []).concat(
            ['/document_wiki/static/src/xml/website_editor.xml']
        ),

        start: function () {
            var defs = [this._super.apply(this, arguments)];
            var self = this;

            defs.push(this._rpc({
                model: 'website.page',
                method: 'search_read',
                domain: [
                    ['website_id', '=', 1],
                ],
                fields: ['id', 'name'],
            }).then(function (pages) {
                self.website_pages = pages
            }));
            return Promise.all(defs);
        },
         /**
         * Asks the user information about a new page to create, then creates it and
         * redirects the user to this new page.
         *
         * @private
         * @returns {Promise} Unresolved if there is a redirection
         */
        _createNewPage: function () {
            var self = this;
            return wUtils.prompt({
                id: 'editor_new_page',
                window_title: _t("New Page"),
                input: _t("Page Title"),
                init: function () {
                    var $group = this.$dialog.find('div.form-group');
                    $group.removeClass('mb0');

                    var $add = $('<div/>', {'class': 'form-group mb0 row'})
                        .append($('<span/>', {'class': 'offset-md-3 col-md-9 text-left'})
                            .append(qweb.render('website.components.switch', {
                                id: 'switch_addTo_menu',
                                label: _t("Add to menu")
                            })));
                    $add.find('input').prop('checked', true);
                    $group.after($add);

                    // add parent page field to the dialog

                    var $parent_page = $('<div/>', {'class': 'form-group mb0 row'})
                        .append(
                            $(qweb.render('document_wiki.parent_page', {
                                website_pages: self.website_pages,
                            }))
                        );
                    $add.after($parent_page)
                }
            }).then(function (result) {
                var val = result.val;
                var $dialog = result.dialog;
                if (!val) {
                    return;
                }
                var url = '/website/add/' + encodeURIComponent(val);
                const res = wUtils.sendRequest(url, {
                    add_menu: $dialog.find('input[type="checkbox"]').is(':checked') || '',
                    parent_page_id: $dialog.find('select#parent_page').val() || ''
                });
                return new Promise(function () {
                });
            });
        }
    })
})
