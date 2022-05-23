odoo.define('document_signatures.sign_bankid', function (require) {
    'use strict';


    var publicWidget = require('web.public.widget');

    publicWidget.registry.DocumentSignButton = publicWidget.Widget.extend({
        selector: '.modal',
        events: {
            'click button#start_signing_document_bankid': '_onClick',
        }, 
        renderElement: function(){
            var self = this;
            this._super();
            // _.each(this.getChildren(), function(child){child.renderElement()});
        },

        /**
         * Calls the route to get updated values of the line and order
         * when the quantity of a product has changed
         *
         * @private
         * @param {integer} order_id
         * @param {Object} params
         * @return {Deferred}
         */
        _callBankidSigninRoute(document_id, params) {
            return this._rpc({
                route: "/my/dms/file/" + document_id + "/sign_start",
                params: params,
            });
        },
        /**
         * @override
         */
        async start() {
            await this._super(...arguments);
            this.document = this.$el.find('document_id').data();
        },
        /**
         * Reacts to the press of the sign button in the sign document modal
         *
         * @param {Event} e
         */
        _onClick(e) {
            console.log(e)
            e.preventDefault();
            console.log("VICTOR TEST");
            this.document = parseInt($(e.delegateTarget).find('#document_id')[0]['innerText']);
            this.directory = parseInt($(e.delegateTarget).find('#directory_id')[0]['innerText']);
            console.log("document_id: " + this.document);
            var self = this;
            debugger

            var ssn = $(e.delegateTarget).find('#personnumber').val();
            console.log(ssn);
            const queryString = window.location.search;
            const urlParams = new URLSearchParams(queryString);

            this._callBankidSigninRoute(self.document, {
                'ssn': ssn,
                'document': self.document,
                'directory': self.directory,
                'access_token': urlParams.get('access_token')
            }).then((data) => {
              data = JSON.parse(data)
              $('#relayState').val(data['relayState']);
              $('#eidSignRequest').val(data['eidSignRequest']);
              $('#binding').val(data['binding']);
              $('#autosubmit').attr('action', data['signingServiceUrl']);
              $('#autosubmit').submit();
              // this.renderElement();
            });

        }
    });
    });
