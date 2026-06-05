from odoo import api, models


class DmsWebdavPath(models.AbstractModel):
    _name = "dms.webdav.path"
    _description = "WebDAV Path Resolver"

    @api.model
    def resolve(self, path):
        """Resolve a WebDAV path to (record, type) where type is 'storage', 'directory', or 'file'.

        Returns (model_record, record_type) or (None, None) if not found.
        Path format: /{storage_name}/{directory_path}/{file_name}
        """
        path = path.strip("/")
        if not path:
            return None, None

        parts = path.split("/")

        storage = self.env["dms.storage"].search([("name", "=", parts[0])], limit=1)
        if not storage:
            return None, None

        if len(parts) == 1:
            return storage, "storage"

        current_dir = False
        for i, part in enumerate(parts[1:], start=1):
            domain = [("name", "=", part), ("storage_id", "=", storage.id)]
            if current_dir:
                domain.append(("parent_id", "=", current_dir.id))
            else:
                domain.append(("parent_id", "=", False))

            directory = self.env["dms.directory"].search(domain, limit=1)
            if directory:
                current_dir = directory
                if i == len(parts) - 1:
                    return current_dir, "directory"
            else:
                if i == len(parts) - 1 and current_dir:
                    file_rec = self.env["dms.file"].search([
                        ("name", "=", part),
                        ("directory_id", "=", current_dir.id),
                    ], limit=1)
                    if file_rec:
                        return file_rec, "file"
                return None, None

        if current_dir:
            return current_dir, "directory"
        return None, None

    @api.model
    def list_directory(self, directory):
        """List children of a directory — returns list of (record, type) tuples."""
        result = []
        for child in directory.child_directory_ids:
            if not child.is_hidden:
                result.append((child, "directory"))
        for file_rec in directory.file_ids:
            result.append((file_rec, "file"))
        return result

    @api.model
    def list_storage(self, storage):
        """List root directories of a storage."""
        result = []
        for root_dir in storage.root_directory_ids:
            if not root_dir.is_hidden:
                result.append((root_dir, "directory"))
        return result

    @api.model
    def list_storages(self):
        """List all visible storages."""
        return self.env["dms.storage"].search([("is_hidden", "=", False)])
