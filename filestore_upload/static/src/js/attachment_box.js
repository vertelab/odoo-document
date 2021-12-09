odoo.define('filestore_upload/static/src/js/attachment_box.js', function (require) {
    'use strict';

    const components = {
        AttachmentBox: require('mail/static/src/components/attachment_box/attachment_box.js'),
    };

    const { patch } = require('web.utils');
    var Dialog = require('web.Dialog');
    var core = require('web.core');
    var _t = core._t;

    var QWeb = core.qweb;
    var rpc = require('web.rpc');


    patch(components.AttachmentBox, 'filestore_upload/static/src/js/attachment_box.js', {
        _onClickAddLargeFile(ev) {
            ev.preventDefault();
            console.log(this.props)
            console.log(this)
            const record_details = this.props.threadLocalId.split('_')

            let self = this

            const action = {
                type: 'ir.actions.act_window',
                name: self.env._t("Upload"),
                res_model: 'upload.filestore',
                view_mode: 'form',
                views: [[false, 'form']],
                target: 'new',
                context: {
                    default_res_model: record_details[1] ,
                    default_res_id: record_details[2] ,
                },
            };
            return self.env.bus.trigger('do-action', {
                action,
                options: {
                    on_close: () => {
                        self.trigger('reload', { keepChanges: true });
                    },
                },
            });
        }

    })
})
