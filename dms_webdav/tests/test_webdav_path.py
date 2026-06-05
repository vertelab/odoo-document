from odoo.tests.common import TransactionCase


class TestWebdavPath(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Storage = cls.env["dms.storage"]
        cls.Directory = cls.env["dms.directory"]
        cls.File = cls.env["dms.file"]
        cls.PathResolver = cls.env["dms.webdav.path"]

        cls.storage = cls.Storage.create({
            "name": "TestStorage",
            "save_type": "database",
        })
        cls.root_dir = cls.Directory.create({
            "name": "RootDir",
            "is_root_directory": True,
            "storage_id": cls.storage.id,
        })
        cls.sub_dir = cls.Directory.create({
            "name": "SubDir",
            "parent_id": cls.root_dir.id,
        })
        cls.hidden_root = cls.Directory.create({
            "name": "HiddenRoot",
            "is_root_directory": True,
            "storage_id": cls.storage.id,
            "is_hidden": True,
        })
        cls.test_file = cls.File.create({
            "name": "test.txt",
            "directory_id": cls.root_dir.id,
            "content": cls._b64encode(b"hello"),
        })

    @staticmethod
    def _b64encode(data):
        import base64
        return base64.b64encode(data)

    def test_resolve_storage(self):
        record, rtype = self.PathResolver.resolve("/TestStorage")
        self.assertEqual(record, self.storage)
        self.assertEqual(rtype, "storage")

    def test_resolve_storage_trailing_slash(self):
        record, rtype = self.PathResolver.resolve("/TestStorage/")
        self.assertEqual(record, self.storage)
        self.assertEqual(rtype, "storage")

    def test_resolve_root_directory(self):
        record, rtype = self.PathResolver.resolve("/TestStorage/RootDir")
        self.assertEqual(record, self.root_dir)
        self.assertEqual(rtype, "directory")

    def test_resolve_subdirectory(self):
        record, rtype = self.PathResolver.resolve("/TestStorage/RootDir/SubDir")
        self.assertEqual(record, self.sub_dir)
        self.assertEqual(rtype, "directory")

    def test_resolve_file(self):
        record, rtype = self.PathResolver.resolve("/TestStorage/RootDir/test.txt")
        self.assertEqual(record, self.test_file)
        self.assertEqual(rtype, "file")

    def test_resolve_nonexistent_storage(self):
        record, rtype = self.PathResolver.resolve("/NoSuchStorage")
        self.assertIsNone(record)
        self.assertIsNone(rtype)

    def test_resolve_nonexistent_directory(self):
        record, rtype = self.PathResolver.resolve("/TestStorage/NoDir")
        self.assertIsNone(record)

    def test_resolve_nonexistent_file(self):
        record, rtype = self.PathResolver.resolve("/TestStorage/RootDir/nonexistent.txt")
        self.assertIsNone(record)

    def test_resolve_empty_path(self):
        record, rtype = self.PathResolver.resolve("")
        self.assertIsNone(record)

    def test_resolve_root_path(self):
        record, rtype = self.PathResolver.resolve("/")
        self.assertIsNone(record)

    def test_list_storages(self):
        storages = self.PathResolver.list_storages()
        self.assertIn(self.storage, storages)

    def test_hidden_storage_excluded(self):
        hidden = self.Storage.create({
            "name": "HiddenStorage",
            "save_type": "database",
            "is_hidden": True,
        })
        storages = self.PathResolver.list_storages()
        self.assertNotIn(hidden, storages)

    def test_list_storage(self):
        children = self.PathResolver.list_storage(self.storage)
        self.assertIn((self.root_dir, "directory"), children)
        self.assertNotIn((self.hidden_root, "directory"), children)

    def test_list_directory(self):
        children = self.PathResolver.list_directory(self.root_dir)
        self.assertIn((self.sub_dir, "directory"), children)
        self.assertIn((self.test_file, "file"), children)

    def test_list_directory_subdir(self):
        sub_file = self.File.create({
            "name": "subfile.txt",
            "directory_id": self.sub_dir.id,
            "content": self._b64encode(b"sub"),
        })
        children = self.PathResolver.list_directory(self.sub_dir)
        self.assertIn((sub_file, "file"), children)

    def test_resolve_file_with_special_chars(self):
        special_file = self.File.create({
            "name": "my file (2).txt",
            "directory_id": self.root_dir.id,
            "content": self._b64encode(b"special"),
        })
        record, rtype = self.PathResolver.resolve("/TestStorage/RootDir/my file (2).txt")
        self.assertEqual(record, special_file)
        self.assertEqual(rtype, "file")

    def test_resolve_deeply_nested(self):
        deep1 = self.Directory.create({"name": "Level1", "parent_id": self.root_dir.id})
        deep2 = self.Directory.create({"name": "Level2", "parent_id": deep1.id})
        deep3 = self.Directory.create({"name": "Level3", "parent_id": deep2.id})
        deep_file = self.File.create({
            "name": "deep.txt",
            "directory_id": deep3.id,
            "content": self._b64encode(b"deep"),
        })
        record, rtype = self.PathResolver.resolve("/TestStorage/RootDir/Level1/Level2/Level3/deep.txt")
        self.assertEqual(record, deep_file)
        self.assertEqual(rtype, "file")
