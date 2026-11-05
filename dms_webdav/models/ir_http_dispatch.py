"""Keep the request body out of the route arguments.

Odoo's ``Dispatcher.dispatch()`` does::

    self.request.params = dict(self.request.get_http_params(), **args)

and ``get_http_params()`` merges ``args``, ``form`` and ``files``. Touching
``.form`` runs Werkzeug's form parser whenever the request carries a
``Content-Type`` header -- it does not look at the method -- and that parser
consumes the stream. For a WebDAV PUT whose body happens to look like
``key=value`` (or is sent as ``application/x-www-form-urlencoded``, which is
what ``curl --data-binary`` uses by default) the payload therefore ends up as
a key in ``request.params``.

``@http.route`` wraps the endpoint with ``filter_kwargs()``, keeps only the
names the endpoint declares and logs the rest as ``called ignoring args``.
The route methods take exactly the URL arguments, so the body is dropped and
``_put()`` writes zero bytes -- with a 200/201 response, so the client sees
success. That is how a live file was silently emptied.

Rather than reimplementing dispatch, this patch snapshots the raw body just
before the call, and afterwards asks Werkzeug for the bytes it cached on the
request object. ``get_data(cache=True)`` is enough for normal clients, but a
client that sends a form-ish ``Content-Type`` puts the payload in
``request.form`` instead, so that is checked as a fallback. The recovered
bytes are pushed back into ``httprequest._cached_data``, which is where
``get_data()`` reads from.

Scoped to this module's own routes on purpose: other controllers in Odoo rely
on the stock behaviour, and changing it globally would be a surprise.
"""

import logging

from odoo import models
from odoo.http import HttpDispatcher

_logger = logging.getLogger(__name__)

WEBDAV_PREFIX = "/webdav/"

# HttpDispatcher defines its own dispatch(), so patching the abstract base
# (Dispatcher) would have no effect. This is the class Request instantiates
# for type='http' routes: ``self.dispatcher = _dispatchers['http'](self)``.
_original_webserver_dispatch = HttpDispatcher.dispatch


def webserver_dispatch_keeps_body(self, endpoint, args):
    path = self.request.httprequest.path
    if not path.startswith(WEBDAV_PREFIX):
        return _original_webserver_dispatch(self, endpoint, args)

    body = _recover_body(self.request)
    response = _original_webserver_dispatch(self, endpoint, args)
    body = _recover_body_from_params(self.request, body)
    if body:
        _restore_body(self.request, body)
    return response


def _recover_body(odoo_request):
    """Return the body bytes, whatever the Content-Type did to them."""
    httprequest = odoo_request.httprequest
    # ``get_data(cache=True)`` must run *before* the dispatcher reads
    # ``.form``; Werkzeug then feeds its parser from a copy of the cache
    # (``_get_stream_for_parsing()``) and the cache survives.
    return httprequest.get_data(cache=True)


def _recover_body_from_params(odoo_request, body):
    """Fallback when the dispatcher already parsed the payload as form data."""
    if body:
        return body
    httprequest = odoo_request.httprequest
    declared = httprequest.content_length or 0
    if not declared or httprequest.method not in ("PUT", "POST", "PATCH"):
        # No body was sent (a legitimate empty PUT must stay empty), or the
        # verb carries no payload worth recovering.
        return b""
    # ``httprequest.form`` holds only the parsed fields. ``request.params``
    # would also contain the route arguments (seg1, resource_path, ...), which
    # is why the earlier version mis-reported every PUT as an unrecoverable
    # multi-field form.
    form = httprequest.form
    if len(form) == 1:
        value = next(iter(form.values()))
        if isinstance(value, str) and value:
            recovered = value.encode("utf-8")
            if len(recovered) == declared:
                _logger.warning(
                    "[WebDAV] body was parsed as form data on %s; recovered "
                    "%d bytes. The client should send "
                    "Content-Type: application/octet-stream.",
                    httprequest.path,
                    len(recovered),
                )
                return recovered
    if form:
        _logger.error(
            "[WebDAV] binary body on %s (%d bytes declared) arrived as %d "
            "form fields and cannot be recovered. Client sent "
            "Content-Type %r.",
            httprequest.path,
            declared,
            len(form),
            httprequest.headers.get("Content-Type"),
        )
    return b""


def _restore_body(odoo_request, body):
    httprequest = odoo_request.httprequest
    httprequest._cached_data = body
    # ``get_data()`` returns the cache, but ``stream`` was already consumed
    # by the form parser; point it at the cached copy as Werkzeug does.
    try:
        from io import BytesIO

        httprequest.stream = BytesIO(body)
    except Exception:  # pragma: no cover - a read-only property is harmless
        pass


def _patch():
    if HttpDispatcher.dispatch is not webserver_dispatch_keeps_body:
        HttpDispatcher.dispatch = webserver_dispatch_keeps_body


class IrHttpDispatch(models.AbstractModel):
    _name = "dms.webdav.ir.http.dispatch"
    _description = "Keeps WebDAV PUT bodies out of the route arguments"

    def _register_hook(self):
        _patch()
        return super()._register_hook()
