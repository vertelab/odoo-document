{
    "name": "DMS SFTP",
    "summary": "Access OCA DMS documents via SFTP",
    "version": "18.0.1.0.0",
    "category": "Document Management",
    "author": "Vertel AB",
    "license": "AGPL-3",
    "depends": ["dms", "mail"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "external_dependencies": {
        "python": ["paramiko"],
    },
    "post_init_hook": "install_hook",
    "installable": True,
    "application": False,
}
