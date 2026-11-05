# -*- coding: utf-8 -*-
"""Tests for dms_excalidraw (tasks 8.1-8.8).

Each test names the task it covers. The contract under test is the model in
models/dms_file.py:

    dms.file.can_open_in_excalidraw            computed bool
    dms.file._excalidraw_webdav_path(root)     derived path
    dms.file.open_in_excalidraw_action()       ir.actions.act_url
    dms.file.action_new_whiteboard()           creates a file, returns act_url
    dms.directory.action_new_whiteboard_url()  act_url to the controller
    EMPTY_SCENE                                module constant

The tests build their own storage and directory rather than importing
dms/tests/common.py: that module is OCA's test helper and is free to change
under this module.

**The WebDAV path starts at the storage name, then the root directory.**
`dms.webdav.path.resolve()` reads `/{storage_name}/{directory_path}/{file}`
and looks the first segment up in `dms.storage`; a root directory is found by
`parent_id = False` under that storage, so it contributes its own segment.
The assertions below follow the resolver, not intuition.
"""

import base64
import json

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon

from ..models.dms_file import EMPTY_SCENE

SCENE_KEYS = {"type", "version", "elements", "appState", "files"}


@tagged("post_install", "-at_install")
class TestDmsExcalidraw(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.file_model = cls.env["dms.file"]
        cls.directory_model = cls.env["dms.directory"]
        cls.storage_model = cls.env["dms.storage"]
        cls.config_model = cls.env["ir.config_parameter"].sudo()

        # `dms.file` has mail.thread tracking on `directory_id`; disable it so
        # the suite does not write chatter to the test database (the same
        # choice dms_webdav's own tests make).
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # ⚠️ OCA `dms` (18.0, this checkout) REFUSES `save_type = "database"`:
        # `_check_save_type_capability` only accepts a type that declares
        # `is_attachment` or `is_file_based`, and `_compute_capabilities`
        # declares neither for "database". So "database" is in the selection
        # but cannot be created — `The save type 'database' declares neither
        # is_attachment nor is_file_based`. Verified 2026-11-05 by running the
        # suite. `"file"` (filestore) is file-based and is what a real
        # installation uses.
        cls.storage = cls.storage_model.create(
            {"name": "Excalidraw Storage", "save_type": "file"}
        )
        cls.root_directory = cls.directory_model.create(
            {
                "name": "Whiteboards",
                "is_root_directory": True,
                "storage_id": cls.storage.id,
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _scene_content(cls):
        return base64.b64encode(json.dumps(EMPTY_SCENE).encode("utf-8"))

    @classmethod
    def _create_file(cls, name, directory=None):
        return cls.file_model.create(
            {
                "name": name,
                "directory_id": (directory or cls.root_directory).id,
                "content": cls._scene_content(),
            }
        )

    @classmethod
    def _create_child_directory(cls, name="Kund A"):
        return cls.directory_model.create(
            {
                "name": name,
                "is_root_directory": False,
                "parent_id": cls.root_directory.id,
                "storage_id": cls.storage.id,
            }
        )

    def _set_url(self, url):
        self.config_model.set_param("dms_excalidraw.url", url or "")

    # ------------------------------------------------------------------
    # 8.1 Extension controls the flag
    # ------------------------------------------------------------------
    def test_8_1_extension_controls_the_flag(self):
        """A .excalidraw file is openable; a .pdf is not."""
        whiteboard = self._create_file("ritning.excalidraw")
        self.assertTrue(
            whiteboard.can_open_in_excalidraw,
            "a file with extension 'excalidraw' must be openable",
        )

        pdf = self._create_file("avtal.pdf")
        self.assertFalse(
            pdf.can_open_in_excalidraw,
            "a .pdf must not be openable in Excalidraw",
        )

    # ------------------------------------------------------------------
    # 8.2 Opening without a configured URL raises a user-facing error
    # ------------------------------------------------------------------
    def test_8_2_empty_url_raises_user_error(self):
        """An empty dms_excalidraw.url raises rather than producing a bad link."""
        whiteboard = self._create_file("ritning.excalidraw")
        self._set_url("")
        with self.assertRaises(UserError):
            whiteboard.open_in_excalidraw_action()

    # ------------------------------------------------------------------
    # 8.3 The WebDAV URL contains the directory chain and the file name
    # ------------------------------------------------------------------
    def test_8_3_webdav_url_contains_chain_and_name(self):
        """A nested whiteboard's path carries the storage, every directory and
        the filename, in the order `dms.webdav.path.resolve()` reads them.

        The root directory IS a segment: the resolver finds it by
        `parent_id = False` under the storage, so it sits between the storage
        name and the child directory.
        """
        child = self._create_child_directory("Kund A")
        whiteboard = self._create_file("ritning.excalidraw", directory=child)

        path = whiteboard._excalidraw_webdav_path()
        self.assertEqual(
            path,
            "/webdav/Excalidraw Storage/Whiteboards/Kund A/ritning.excalidraw",
            "the path must be /<root>/<storage>/<dirs>/<file>",
        )
        self.assertIn("Kund A", path)
        self.assertIn("ritning.excalidraw", path)

    # ------------------------------------------------------------------
    # 8.4 Opening a non-whiteboard raises a user-facing error
    # ------------------------------------------------------------------
    def test_8_4_non_whiteboard_raises_user_error(self):
        """The action refuses a file that is not a whiteboard."""
        self._set_url("https://dms.example.org/whiteboard")
        pdf = self._create_file("avtal.pdf")
        with self.assertRaises(UserError):
            pdf.open_in_excalidraw_action()

    # ------------------------------------------------------------------
    # 8.5 A new whiteboard contains a valid scene
    # ------------------------------------------------------------------
    def test_8_5_new_whiteboard_has_valid_scene(self):
        """A created whiteboard parses to the Excalidraw scene shape (design D5)."""
        self._set_url("https://dms.example.org/whiteboard")
        whiteboard = self._create_file("ritning.excalidraw")

        scene = json.loads(base64.b64decode(whiteboard.content))
        self.assertTrue(
            SCENE_KEYS.issubset(scene.keys()),
            f"scene is missing keys: {SCENE_KEYS - set(scene)}",
        )
        self.assertEqual(scene["type"], "excalidraw")
        self.assertEqual(scene["version"], 2)
        self.assertEqual(scene["elements"], [])
        self.assertEqual(scene["files"], {})

    # ------------------------------------------------------------------
    # 8.6 A new whiteboard without a directory raises a user-facing error
    # ------------------------------------------------------------------
    def test_8_6_new_whiteboard_without_directory_raises(self):
        """Creating a whiteboard with no record in context raises UserError.

        `dms.file.directory_id` is `required=True`, so a saved record always
        has a directory and the `if not directory:` branch below it is
        defensive. The reachable case is the empty recordset: the action is
        bound to a list/kanban view, so a user can invoke it without selecting
        a row. The model checks `if not self:` BEFORE `ensure_one()`, so that
        case raises a user-facing error rather than a bare ValueError.
        """
        with self.assertRaises(UserError):
            self.file_model.action_new_whiteboard()

    # ------------------------------------------------------------------
    # 8.7 The extension is appended when missing
    # ------------------------------------------------------------------
    def test_8_7_extension_appended_when_missing(self):
        """A name without .excalidraw gets the extension added.

        The extension is appended by `action_new_whiteboard()`, not by
        `create()` -- so the test must go through the action. Creating a file
        named `ritning` directly and asserting its name would test OCA's
        `create()`, which does not append anything.
        """
        self._set_url("https://dms.example.org/whiteboard")
        action = self.file_model.action_new_whiteboard(
            name="ritning", directory=self.root_directory
        )
        self.assertEqual(action["type"], "ir.actions.act_url")

        created = self.file_model.search(
            [
                ("directory_id", "=", self.root_directory.id),
                ("name", "like", "ritning"),
            ],
            limit=1,
        )
        self.assertTrue(created, "the action did not create a file")
        self.assertEqual(
            created.name,
            "ritning.excalidraw",
            f"expected the extension to be appended, got {created.name!r}",
        )

    # ------------------------------------------------------------------
    # 8.8 The WebDAV path includes the root directory exactly once
    # ------------------------------------------------------------------
    def test_8_8_root_directory_appears_exactly_once(self):
        """The mount point appears exactly once, and the root directory does
        contribute its own segment.

        `dms.webdav.path.resolve()` finds a root directory by
        `parent_id = False` under the storage, so it IS a path segment -- the
        storage name is the mount point and the root directory sits under it.
        The path must therefore be
        `/webdav/<storage>/<root>/<child>/<file>`, with each name exactly once.
        """
        child = self._create_child_directory("Kund A")
        whiteboard = self._create_file("ritning.excalidraw", directory=child)
        path = whiteboard._excalidraw_webdav_path()

        self.assertEqual(
            path.count("Excalidraw Storage"),
            1,
            f"the storage mount point is repeated in {path!r}",
        )
        self.assertEqual(
            path.count("Whiteboards"),
            1,
            f"the root directory must appear exactly once in {path!r}",
        )
        self.assertEqual(
            path,
            "/webdav/Excalidraw Storage/Whiteboards/Kund A/ritning.excalidraw",
            f"unexpected path shape: {path!r}",
        )
        self.assertFalse(
            path.startswith("/webdav/webdav"),
            f"the WebDAV root is doubled in {path!r}",
        )

    # ------------------------------------------------------------------
    # 8.9 The path the builder produces is the path the resolver reads
    # ------------------------------------------------------------------
    def test_8_9_path_roundtrips_through_the_webdav_resolver(self):
        """`_excalidraw_webdav_path()` must produce a path `dms.webdav.path`
        resolves back to the same file.

        This is the only test that would catch a wrong segment order. Tests
        8.3/8.8 assert a string the module itself produced; this one asserts
        that `dms_webdav` agrees with it, which is the contract that matters
        (the browser fetches the file through that resolver).
        """
        child = self._create_child_directory("Kund A")
        whiteboard = self._create_file("ritning.excalidraw", directory=child)

        path = whiteboard._excalidraw_webdav_path()
        # The resolver takes the path WITHOUT the /webdav route prefix.
        resolver_path = path[len("/webdav"):]
        record, kind = self.env["dms.webdav.path"].resolve(resolver_path)

        self.assertEqual(
            kind,
            "file",
            f"the resolver did not see a file in {resolver_path!r}",
        )
        self.assertEqual(
            record,
            whiteboard,
            f"the resolver landed on {record!r}, not the whiteboard",
        )

    # ------------------------------------------------------------------
    # 8.10 The controller's call shape works on an empty recordset
    # ------------------------------------------------------------------
    def test_8_10_empty_recordset_with_explicit_directory_creates(self):
        """`env["dms.file"].action_new_whiteboard(directory=...)` must work.

        This is the shape the controller uses: it browses only the directory,
        so the recordset is EMPTY. A guard that raises on `not self`
        unconditionally would turn every "New whiteboard" click into a 404,
        and test 8.6 (which calls with no directory) would not notice.
        """
        self._set_url("https://dms.example.org/whiteboard")
        action = self.file_model.action_new_whiteboard(
            name="från kontrollern", directory=self.root_directory
        )
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("/dms_excalidraw/whiteboard/", action["url"])

        created = self.file_model.search(
            [("directory_id", "=", self.root_directory.id),
             ("name", "=", "från kontrollern.excalidraw")],
            limit=1,
        )
        self.assertTrue(created, "the empty recordset call created nothing")

    # ------------------------------------------------------------------
    # 8.11 The created content is real base64, not raw bytes
    # ------------------------------------------------------------------
    def test_8_11_created_content_is_base64_encoded(self):
        """`content` must be base64 TEXT: the inverse runs `b64decode`.

        Passing raw JSON bytes raises `binascii.Error: Incorrect padding` on
        create. The test helper `_create_file` encodes correctly, so a bug in
        `action_new_whiteboard` would not show up there — this test goes
        through the action.
        """
        self._set_url("https://dms.example.org/whiteboard")
        self.file_model.action_new_whiteboard(
            name="base64", directory=self.root_directory
        )
        created = self.file_model.search(
            [("directory_id", "=", self.root_directory.id),
             ("name", "=", "base64.excalidraw")],
            limit=1,
        )
        self.assertTrue(created)

        # Must decode without error, and decode to a valid scene.
        raw = base64.b64decode(created.content)
        scene = json.loads(raw)
        self.assertEqual(scene["type"], "excalidraw")
        self.assertEqual(scene["version"], 2)

    # ------------------------------------------------------------------
    # 8.12 The action opens the host page, not the bare service
    # ------------------------------------------------------------------
    def test_8_12_open_url_opens_the_host_page(self):
        """The action must open `/dms_excalidraw/whiteboard/<id>`.

        It used to open the Excalidraw service with `#url=<webdav path>`.
        That loads the drawing but cannot save it: the service is a built SPA
        with no `onChange` hook we can attach to, so the only save path is
        "Save to disk" — a download, not a write back to the document.

        The host page renders `<Excalidraw>` itself and owns the callbacks.
        """
        self._set_url("https://dms.example.org/whiteboard")
        whiteboard = self._create_file("ritning.excalidraw")
        url = whiteboard.open_in_excalidraw_action()["url"]

        self.assertEqual(
            url,
            f"/dms_excalidraw/whiteboard/{whiteboard.id}",
            f"the action must open the host page, got {url!r}",
        )
        self.assertNotIn("#json=", url)
        self.assertNotIn("#url=", url)

    # ------------------------------------------------------------------
    # 8.13 The service URL is still required
    # ------------------------------------------------------------------
    def test_8_13_service_url_is_still_required(self):
        """The host page loads its assets from the service, so the setting
        must still be configured — and an empty one must name the setting.
        """
        whiteboard = self._create_file("ritning.excalidraw")
        self._set_url("")
        with self.assertRaises(UserError):
            whiteboard.open_in_excalidraw_action()
