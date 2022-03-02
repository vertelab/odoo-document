odoo.define('document_wiki.pages',function(require) {
    'use strict';

    var core = require('web.core');

    var _t = core._t;

    var contentMenu = require('website.contentMenu').PagePropertiesDialog;

    contentMenu.include({
        template: 'website.pagesMenu.page_info',
        xmlDependencies: (contentMenu.prototype.xmlDependencies || []).concat(
            ['/document_wiki/static/src/xml/website.pageProperties.xml']
        ),
        events: _.extend({}, contentMenu.prototype.events, {
            'change select#parent_page': '_onParentPageChanged',
        }),

        init: function (parent, page_id, options) {
            this._super.apply(this, arguments);
        },

        _onParentPageChanged: function (ev) {
            this.parent_page_name = this.$('select#parent_page option:selected').text();
            this.parent_page_error = ''
            this.selected_parent_page = null
            self.$('.parent_page_error').html(this.parent_page_error)
        },

        willStart: async function () {
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
                self.website_pages = pages.filter(page => page.id !== self.page_id)
            }));

            const selected_page_parent = await this._rpc({
                model: 'wiki.page',
                method: 'search_read',
                domain: [
                    ['page_id', '=', parseInt(self.page_id)],
                ],
                fields: ['id', 'parent_id'],
                limit: 1
            })

            if (selected_page_parent.length) {
                this.selected_parent_page = selected_page_parent[0].parent_id[0]
            }

            return Promise.all(defs);

        },

        parent_page_action: async function () {
            var parent_page = this.$('select#parent_page').val();
            var self = this;
            if (parent_page) {
                console.log(parent_page)
                const search_rec = await self._rpc({
                    model: 'wiki.page',
                    method: 'search_read',
                    domain: [
                        ['parent_id', '=', parseInt(parent_page)],
                        ['page_id', '=', self.page_id],
                    ],
                    fields: ['id', 'page_id', 'parent_id'],
                    limit: 1
                });
                console.log(search_rec)
                if (search_rec.length === 0) {
                    await self._rpc({
                        model: 'wiki.page',
                        method: 'create',
                        args: [{ parent_id: parseInt(parent_page), page_id:  self.page_id}],
                    });
                }
            }
        },

        /**
         * @override
         */
        save: async function (data) {
            var self = this;
            var context;
            this.trigger_up('context_get', {
                callback: function (ctx) {
                    context = ctx;
                },
            });
            var url = this.$('#page_url').val();

            var $datePublish = this.$("#date_publish");
            $datePublish.closest(".form-group").removeClass('o_has_error').find('.form-control, .custom-select').removeClass('is-invalid');
            var datePublish = $datePublish.val();
            if (datePublish !== "") {
                datePublish = this._parse_date(datePublish);
                if (!datePublish) {
                    $datePublish.closest(".form-group").addClass('o_has_error').find('.form-control, .custom-select').addClass('is-invalid');
                    return;
                }
            }
            var params = {
                id: this.page.id,
                name: this.$('#page_name').val(),
                // Replace duplicate following '/' by only one '/'
                url: url.replace(/\/{2,}/g, '/'),
                is_menu: this.$('#is_menu').prop('checked'),
                is_homepage: this.$('#is_homepage').prop('checked'),
                website_published: this.$('#is_published').prop('checked'),
                create_redirect: this.$('#create_redirect').prop('checked'),
                redirect_type: this.$('#redirect_type').val(),
                website_indexed: this.$('#is_indexed').prop('checked'),
                visibility: this.$('#visibility').val(),
                date_publish: datePublish,
            };
            if (this.page.hasSingleGroup && this.$('#visibility').val() === 'restricted_group') {
                params['group_id'] = this.$('#group_id').data('group-id');
            }
            if (this.$('#visibility').val() === 'password') {
                var field_pwd = $('#visibility_password');
                if (!field_pwd.get(0).reportValidity()) {
                    return;
                }
                if (field_pwd.data('dirty')) {
                    params['visibility_pwd'] = field_pwd.val();
                }
            }

            await this.parent_page_action()

            this._rpc({
                model: 'website.page',
                method: 'save_page_info',
                args: [[context.website_id], params],
            }).then(function (url) {
                // If from page manager: reload url, if from page itself: go to
                // (possibly) new url
                var mo;
                self.trigger_up('main_object_request', {
                    callback: function (value) {
                        mo = value;
                    },
                });
                if (mo.model === 'website.page') {
                    window.location.href = url.toLowerCase();
                } else {
                    window.location.reload(true);
                }
            });
        },
    })
})
