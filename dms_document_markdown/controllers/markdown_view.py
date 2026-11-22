##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2026- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

"""Render a `.md` file from DMS as a document, not as raw text.

WHY A ROUTE AND NOT THE BUILT-IN PREVIEW
========================================
DMS's file preview shows a `.md` file as plain text. A Markdown file is meant
to be read as a document — headings, lists, code blocks, links — and reading
it as source is the wrong view for everyone except the author.

WHY THE HTML IS SANITISED
=========================
A `.md` file is user content. `markdown` passes raw HTML through by default,
so a file containing `<script>` would execute it in the reader's session —
stored XSS with the reader's DMS permissions. The output is therefore
restricted to a fixed tag/attribute whitelist before it is rendered.

`markdown` ships no sanitiser. Rather than add `bleach` (deprecated) or
`nh3` (a Rust dependency), the whitelist is applied with the stdlib's
`html.parser`: the subset of tags Markdown actually produces is small and
does not change.
"""

import base64
import html.parser
import logging

import markdown
from markupsafe import Markup
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Tags `markdown` can produce. Anything else is escaped, not dropped: a
# reader should see that the file contained something odd, not silently lose
# a paragraph.
ALLOWED_TAGS = {
    "a", "abbr", "blockquote", "br", "code", "dd", "del", "div", "dl", "dt",
    "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "img", "ins", "li", "ol",
    "p", "pre", "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "tr", "ul",
}

# Attributes that are safe on the tags above. `href`/`src` are checked
# separately: `javascript:` in an href is the classic XSS vector.
ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"align"},
    "th": {"align"},
    "div": {"class"},
    "span": {"class"},
    "code": {"class"},
    "pre": {"class"},
}

SAFE_URL_SCHEMES = ("http://", "https://", "mailto:", "/", "#")


class _Sanitizer(html.parser.HTMLParser):
    """Rebuild the document, keeping only whitelisted tags and attributes.

    Not a full HTML parser: it re-emits what it is given, escaping anything
    it does not recognise. That is enough because the input is the output of
    `markdown`, not arbitrary HTML.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object", "embed"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in ALLOWED_TAGS:
            return
        allowed = ALLOWED_ATTRS.get(tag, set())
        parts = [tag]
        for key, value in attrs:
            if key not in allowed:
                continue
            if key in ("href", "src"):
                lowered = (value or "").strip().lower()
                if not lowered.startswith(SAFE_URL_SCHEMES):
                    continue
            parts.append('%s="%s"' % (key, (value or "").replace('"', "&quot;")))
        self.out.append("<%s>" % " ".join(parts))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object", "embed"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in ALLOWED_TAGS:
            self.out.append("</%s>" % tag)

    def handle_data(self, data):
        if not self._skip_depth:
            self.out.append(data.replace("<", "&lt;").replace(">", "&gt;"))

    def get_html(self):
        return "".join(self.out)


def render_markdown(text):
    """Return sanitised HTML for `text`."""
    raw = markdown.markdown(
        text or "",
        extensions=["fenced_code", "tables", "toc", "sane_lists"],
    )
    parser = _Sanitizer()
    parser.feed(raw)
    return parser.get_html()


class DmsMarkdownController(http.Controller):
    @http.route(
        "/dms_excalidraw/markdown/<int:file_id>",
        auth="user",
        type="http",
        website=False,
    )
    def view_markdown(self, file_id):
        """Render a `.md` file as a document.

        The route lives under `/dms_excalidraw/` because that is where the
        kanban override points; it is not an Excalidraw feature, and a future
        cleanup should move both to a shared prefix.
        """
        dms_file = request.env["dms.file"].browse(file_id)

        if not dms_file.sudo().exists():
            return request.not_found()

        if not dms_file.permission_read:
            return request.not_found()

        extension = (dms_file.extension or "").lower()
        if extension not in ("md", "markdown"):
            return request.not_found()

        try:
            raw = base64.b64decode(dms_file.content or "")
            text = raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            _logger.warning(
                "dms_document_markdown: dms.file %s is not utf-8 text", file_id
            )
            text = ""

        return request.render(
            "dms_document_markdown.markdown_page",
            {
                "file_id": dms_file.id,
                "file_name": dms_file.name,
                # Markup: the HTML is already sanitised by _Sanitizer above.
                # A plain str would be escaped again by `t-out`, which is what
                # the first version did — the page showed the tags as text.
                "body": Markup(render_markdown(text)),
                "back_url": self._back_url(dms_file),
            },
        )

    @staticmethod
    def _back_url(dms_file):
        """Return the URL the back button should go to.

        "Back" must return to where the user came from, not to the file's
        form. The kanban icon opens this page in a new tab, and the user was
        browsing a directory — sending them to the record form loses that.

        The URL is `<directory_action>/<id>/<files_action>` — what DMS
        produces when the "Files" stat button is clicked in a directory form,
        and the only form that restores both the directory and the filter.

        `action_dms_files_directory` (179) is NOT usable as a bare URL: it
        requires `active_id` from a directory record and crashes the web
        client with "Something went wrong" when opened directly.

        The `?from=` argument is accepted for forward compatibility but not
        used: the file's own directory is the only correct answer, and
        trusting a query parameter would let a crafted link point the back
        button somewhere the user has no access to.
        """
        directory = dms_file.directory_id

        if directory:
            return "/odoo/action-dms.action_dms_directory/%s/action-dms.action_dms_file" % (
                directory.id,
            )

        return "/odoo/action-dms.action_dms_file"
