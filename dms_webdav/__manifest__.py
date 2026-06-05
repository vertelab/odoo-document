{
    "name": "DMS WebDAV",
    "summary": "Access OCA DMS documents via WebDAV",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel AB",
    "license": "AGPL-3",
    "depends": ["dms", "web", "http_routing"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "description": """
WebDAV endpoint for OCA Document Management System at /webdav/.
Allows external clients (Nautilus, Windows Explorer, etc.) to mount
and work with DMS directories and files via the WebDAV protocol.
    """,
}
