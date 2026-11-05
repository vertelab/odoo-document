{
    "name": "DMS Excalidraw Bridge",
    "summary": "Open DMS whiteboards in an Excalidraw service",
    "description": """
Adds an "Open in Excalidraw" action to DMS files whose extension is
`excalidraw`, and a "New whiteboard" action to DMS directories.

A whiteboard is a `dms.file`, not a model of its own: it inherits the
directory's access groups, retention, revision history and backup, appears in
the linked record's Documents counter, and carries its `res_model`/`res_id`
link to the business object without any code building that link. The same
pattern as `dms_euro_office`.

A whiteboard is opened in a host page served by Odoo
(`/dms_excalidraw/whiteboard/<id>`) that renders the Excalidraw editor and
owns its callbacks, so an edit is saved back to the same `dms.file`. The page
fills the viewport -- a whiteboard boxed into a form is not a whiteboard.

Saving goes through this module's own routes, not WebDAV: `dms_webdav`'s PUT
authenticates with Basic auth, so a same-origin page would have to hold the
user's password in JavaScript. Odoo's `/jsonrpc` is no better -- it wants
db+login+password in the body. These routes use the session cookie the browser
already has, and write through the same `dms.file.content` inverse WebDAV uses.

Two tabs on the same whiteboard cannot silently overwrite each other: a save
carries the checksum it loaded, and a mismatch is refused with a conflict
dialog.

The Excalidraw service URL is an `ir.config_parameter`
(`dms_excalidraw.url`), surfaced under Settings > Documents > Excalidraw.

A whiteboard whose scene contains `frame` elements can be PRESENTED as a slide
deck: frames become slides in ascending y-order and elements that share a
`customData.name` animate between them. The presentation is a mode in the same
page, not a new document type -- the file stays `extension = excalidraw` and
presenting never writes.

The shape-library catalogue (`dms_excalidraw.library`) ships 30 libraries as
module data, so a fresh install has something to browse with no network.
Refreshing it from the upstream catalogue is opt-in
(`dms_excalidraw.library_sync_enabled`, default off).
""",
    "author": "Vertel Sverige AB",
    "website": "https://vertel.se",
    "category": "Productivity/Documents",
    "version": "18.0.2.7.0",
    "depends": ["dms", "dms_webdav"],
    "data": [
        # MUST come before anything that reads a directory: it repairs the
        # OCA `dms` record rules that deny everyone the right to create.
        "security/dms_rule_workaround.xml",
        "security/dms_excalidraw_library_security.xml",
        "data/excalidraw_data.xml",
        "data/dms_access_group_seed.xml",
        "data/library_seed.xml",
        "views/dms_file_view.xml",
        "views/dms_directory_view.xml",
        "views/res_config_settings_view.xml",
        "views/whiteboard_page.xml",
        "views/dms_excalidraw_wizard_view.xml",
        "views/dms_excalidraw_library_view.xml",
        "views/dms_document_wizard_view.xml",
        "security/ir.model.access.csv",
    ],
    "assets": {
        # The kanban record override must load in the BACKEND, where the
        # kanban view lives — not in the whiteboard page's own bundle.
        "web.assets_backend": [
            "dms_excalidraw/static/src/xml/kanban_buttons.xml",
            "dms_excalidraw/static/src/js/file_kanban_record.esm.js",
            "dms_excalidraw/static/src/js/file_kanban_view.esm.js",
        ],
    },
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
