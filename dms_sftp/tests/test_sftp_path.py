from odoo.tests.common import TransactionCase


class TestSftpPath(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Storage = self.env["dms.storage"]
        self.Directory = self.env["dms.directory"]
        self.File = self.env["dms.file"]

        self.storage = self.Storage.create({"name": "TestStorage"})
        self.root_dir = self.Directory.create({
            "name": "RootDir",
            "storage_id": self.storage.id,
            "is_root_directory": True,
        })
        self.sub_dir = self.Directory.create({
            "name": "SubDir",
            "parent_id": self.root_dir.id,
        })
        self.test_file = self.File.create({
            "name": "test.txt",
            "directory_id": self.root_dir.id,
            "content": self._b64encode(b"hello"),
        })

    def _b64encode(self, data):
        import base64
        return base64.b64encode(data)

    def _resolve(self, path):
        path = path.strip("/")
        parts = path.split("/")
        storage = self.Storage.search([("name", "=", parts[0])], limit=1)
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

            directory = self.Directory.search(domain, limit=1)
            if directory:
                current_dir = directory
                if i == len(parts) - 1:
                    return current_dir, "directory"
            else:
                if i == len(parts) - 1 and current_dir:
                    file_rec = self.File.search([
                        ("name", "=", part),
                        ("directory_id", "=", current_dir.id),
                    ], limit=1)
                    if file_rec:
                        return file_rec, "file"
                return None, None
        if current_dir:
            return current_dir, "directory"
        return None, None

    def test_resolve_storage(self):
        record, rtype = self._resolve("/TestStorage")
        self.assertEqual(record, self.storage)
        self.assertEqual(rtype, "storage")

    def test_resolve_directory(self):
        record, rtype = self._resolve("/TestStorage/RootDir")
        self.assertEqual(record, self.root_dir)
        self.assertEqual(rtype, "directory")

    def test_resolve_subdirectory(self):
        record, rtype = self._resolve("/TestStorage/RootDir/SubDir")
        self.assertEqual(record, self.sub_dir)
        self.assertEqual(rtype, "directory")

    def test_resolve_file(self):
        record, rtype = self._resolve("/TestStorage/RootDir/test.txt")
        self.assertEqual(record, self.test_file)
        self.assertEqual(rtype, "file")

    def test_resolve_nonexistent(self):
        record, rtype = self._resolve("/TestStorage/NoExist")
        self.assertIsNone(record)

    def test_resolve_file_under_subdir(self):
        sub_file = self.File.create({
            "name": "subfile.txt",
            "directory_id": self.sub_dir.id,
            "content": self._b64encode(b"sub"),
        })
        record, rtype = self._resolve("/TestStorage/RootDir/SubDir/subfile.txt")
        self.assertEqual(record, sub_file)
        self.assertEqual(rtype, "file")
