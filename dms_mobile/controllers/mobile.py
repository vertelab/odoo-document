# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""The phone landing page.

Lists the directories marked as mobile targets that the current user may
write to, each with a camera button. Deliberately plain: a phone on a bad
connection should render this without waiting for the Odoo web client.
"""

import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class DmsMobileController(http.Controller):
    @http.route("/dms/mobile", type="http", auth="user", methods=["GET"],
                sitemap=False)
    def dms_mobile(self):
        directories = request.env["dms.directory"].search([
            ("mobile_target", "=", True),
        ])
        # Filter on the user's own rights rather than sudo: a directory the
        # user cannot write to must not appear with a camera button.
        writable = directories.filtered(
            lambda d: d._filtered_access("create")
        )
        cards = "\n".join(self._card(directory) for directory in writable)
        if not cards:
            cards = (
                '<p class="empty">Inga kataloger är markerade för mobil '
                'uppladdning. Be en administratör sätta "Mobile target" på '
                'en DMS-katalog.</p>'
            )
        html = _MOBILE_HTML.replace("<!-- CARDS -->", cards)
        return Response(html, headers=[
            ("Content-Type", "text/html; charset=utf-8"),
            ("Cache-Control", "no-store, must-revalidate"),
        ])

    def _card(self, directory):
        from html import escape

        name = escape(directory.name or "")
        href = "/pwa/capture?app=dms-capture&directory_id=%s" % directory.id
        return (
            '<a class="card" href="%s">'
            '<span class="name">%s</span>'
            '<span class="go">Fota</span>'
            "</a>" % (href, name)
        )


_MOBILE_HTML = r"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>DMS Mobil</title>
<style>
:root { --bg:#fff; --card:#f5f7fa; --border:#e0e0e0; --text:#1a1a2e;
        --muted:#666; --accent:#1976d2; --radius:12px;
        --font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:var(--font); background:var(--bg); color:var(--text);
       min-height:100vh; padding:24px; display:flex; flex-direction:column;
       gap:16px; }
h1 { font-size:1.25rem; }
.card { display:flex; align-items:center; justify-content:space-between;
        background:var(--card); border:1px solid var(--border);
        border-radius:var(--radius); padding:18px; text-decoration:none;
        color:var(--text); font-size:1.05rem; }
.card .go { color:var(--accent); font-weight:600; }
.empty { color:var(--muted); font-size:.95rem; line-height:1.5; }
</style>
</head>
<body>
<h1>Fota in i DMS</h1>
<!-- CARDS -->
</body>
</html>
"""
