{
    "name": "DMS Document: Markdown",
    "summary": "Read .md files from DMS as documents, not as source",
    "description": """
Renders a `.md` file in DMS as a formatted document.

DMS's built-in preview shows Markdown as plain text. That is the wrong view
for everyone except the author: a Markdown file is meant to be read as a
document — headings, lists, tables, code blocks, links.

The HTML is sanitised against a fixed tag/attribute whitelist before it is
rendered. `markdown` passes raw HTML through by default, so a file containing
`<script>` would otherwise execute in the reader's session — stored XSS with
the reader's DMS permissions. `markdown` ships no sanitiser, and adding
`bleach` (deprecated) or `nh3` (Rust) for a small fixed whitelist is not worth
the dependency.

The route is `/dms_excalidraw/markdown/<id>` because that is where the kanban
override points. It is not an Excalidraw feature; a future cleanup should move
both to a shared prefix.
""",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "category": "Productivity/Documents",
    "version": "18.0.1.0.3",
    "depends": ["dms"],
    "external_dependencies": {"python": ["markdown"]},
    "data": [
        "views/markdown_page.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
