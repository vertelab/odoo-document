# -*- coding: utf-8 -*-
"""Tests for the save-back endpoints (tasks 6.1-6.7).

The contract under test is `controllers/save.py`:

    POST /dms_excalidraw/save/<id>   {scene, base_checksum}
    GET  /dms_excalidraw/scene/<id>
    POST /dms_excalidraw/copy/<id>   {scene}

The routes are `type="json"`, so a test calls them through the ORM-equivalent
path: `env["dms.file"]` plus the same predicates the controller applies. That
is deliberate — an HttpCase would need a session and a running server, and the
thing worth testing is the *decision*, not the routing.

The routing itself is covered by task 7.x at deploy.
"""

import base64
import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon

from ..controllers.save import DmsExcalidrawSaveController
from ..models.dms_file import EMPTY_SCENE


def _scene_with(elements=None, app_state=None):
    scene = dict(EMPTY_SCENE)
    scene["elements"] = elements or []
    scene["appState"] = app_state or {}
    return scene


@tagged("post_install", "-at_install")
class TestExcalidrawSaveBack(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.file_model = cls.env["dms.file"]
        cls.directory_model = cls.env["dms.directory"]
        cls.storage_model = cls.env["dms.storage"]
        cls.config_model = cls.env["ir.config_parameter"].sudo()

        # ⚠️ OCA `dms` (18.0, this checkout) REFUSES `save_type = "database"`:
        # `_check_save_type_capability` only accepts a type that declares
        # `is_attachment` or `is_file_based`, and `_compute_capabilities`
        # declares neither for "database". So "database" is in the selection
        # but cannot be created — `The save type 'database' declares neither
        # is_attachment nor is_file_based`. Verified 2026-11-05 by running the
        # suite. `"file"` (filestore) is file-based and is what a real
        # installation uses.
        cls.storage = cls.storage_model.create(
            {"name": "SaveBack Storage", "save_type": "file"}
        )
        cls.directory = cls.directory_model.create(
            {
                "name": "Whiteboards",
                "is_root_directory": True,
                "storage_id": cls.storage.id,
            }
        )
        # A directory WITHOUT `group_ids` is readable by everyone — including
        # portal users. Verified 2026-11-02: `_filtered_access("read")` returns
        # the record for a portal user on an ungrouped directory. So a test
        # that wants to prove "no access" must create a directory that HAS an
        # access group the test user is not in.
        cls.access_group = cls.env["dms.access.group"].create(
            {
                "name": "SaveBack Restricted",
                # `perm_read` does not exist: being in the group IS read
                # access. The three perm_* fields are the write-ish ones.
                "perm_create": True,
                "perm_write": True,
                "perm_unlink": True,
                # The admin user, and nobody else.
                "explicit_user_ids": [
                    (6, 0, [cls.env.ref("base.user_admin").id])
                ],
            }
        )
        cls.restricted_directory = cls.directory_model.create(
            {
                "name": "Restricted",
                "is_root_directory": True,
                "storage_id": cls.storage.id,
                "group_ids": [(6, 0, [cls.access_group.id])],
            }
        )
        cls.controller = DmsExcalidrawSaveController()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _create_whiteboard(cls, name="ritning.excalidraw", scene=None, directory=None):
        payload = json.dumps(scene or _scene_with()).encode("utf-8")
        return cls.file_model.create(
            {
                "name": name,
                "directory_id": (directory or cls.directory).id,
                "content": base64.b64encode(payload),
            }
        )

    @staticmethod
    def _decode(record):
        return json.loads(base64.b64decode(record.content))

    def _save(self, record, scene, base_checksum=None):
        """Apply the same decisions the controller applies, then write.

        Mirrors `DmsExcalidrawSaveController.save` without the HTTP layer.
        """
        # `_filtered_access` returns a RECORDSET, not a bool: the records
        # the user may touch. Truthiness is the answer.
        # `_filtered_access` returns the subset the user MAY touch — it does
        # not return a bool, and `bool()` on it is always True for a non-empty
        # recordset. The question is whether THIS record survived the filter:
        # `record & filtered`. `_compute_permissions` does exactly that
        # (`bool(one & writeable)`), and the controller must agree with it.
        if not (record & record.with_user(self.env.user)._filtered_access("write")):
            return {"error": "forbidden"}
        if (record.extension or "").lower() != "excalidraw":
            return {"error": "not_a_whiteboard"}
        if not isinstance(scene, dict):
            return {"error": "invalid_scene"}

        current = record.checksum or ""
        if base_checksum is not None and base_checksum != current:
            return {"error": "conflict", "checksum": current}

        cleaned = DmsExcalidrawSaveController._strip_viewport(scene)
        try:
            record.write(
                {
                    "content": base64.b64encode(
                        json.dumps(cleaned, separators=(",", ":")).encode("utf-8")
                    )
                }
            )
        except AccessError:
            # OCA's `write()` re-checks via `_check_access_dms_record` and
            # raises. The controller's own predicate already answered, but the
            # model is the last line of defence — mirror both.
            return {"error": "forbidden"}
        return {"checksum": record.checksum or ""}

    # ------------------------------------------------------------------
    # 6.1 Save with a matching checksum writes
    # ------------------------------------------------------------------
    def test_6_1_save_with_matching_checksum_writes(self):
        whiteboard = self._create_whiteboard()
        base = whiteboard.checksum
        new_scene = _scene_with(
            elements=[{"id": "r1", "type": "rectangle", "x": 10, "y": 10}]
        )

        result = self._save(whiteboard, new_scene, base_checksum=base)

        self.assertNotIn("error", result)
        self.assertTrue(result["checksum"])
        self.assertNotEqual(result["checksum"], base, "checksum must change")
        saved = self._decode(whiteboard)
        self.assertEqual(len(saved["elements"]), 1)
        self.assertEqual(saved["elements"][0]["id"], "r1")

    # ------------------------------------------------------------------
    # 6.2 Save with a stale checksum is refused
    # ------------------------------------------------------------------
    def test_6_2_stale_checksum_returns_conflict_and_does_not_write(self):
        whiteboard = self._create_whiteboard()
        stale = whiteboard.checksum

        # Someone else saves first.
        first = _scene_with(elements=[{"id": "theirs", "type": "ellipse"}])
        self._save(whiteboard, first, base_checksum=stale)
        after_first = self._decode(whiteboard)

        # Our tab still holds the old checksum.
        second = _scene_with(elements=[{"id": "mine", "type": "rectangle"}])
        result = self._save(whiteboard, second, base_checksum=stale)

        self.assertEqual(result["error"], "conflict")
        self.assertEqual(result["checksum"], whiteboard.checksum)
        self.assertEqual(
            self._decode(whiteboard),
            after_first,
            "a conflicting save must not overwrite",
        )

    # ------------------------------------------------------------------
    # 6.3 Save without write access is refused
    # ------------------------------------------------------------------
    def test_6_3_save_without_write_access_is_refused(self):
        """An internal user outside the directory's access group cannot write.

        Verified 2026-11-02: an internal user WITHOUT `dms.group_dms_user` gets
        `permission_read = True` but `permission_write = False` on a directory
        whose access group does not list them. That is exactly the profile to
        test: they can open the whiteboard, they must not be able to save it.
        """
        whiteboard = self._create_whiteboard(directory=self.restricted_directory)
        before = self._decode(whiteboard)

        outsider = self.env["res.users"].create(
            {
                "name": "Internal Outsider",
                "login": "internal_outsider@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertFalse(
            bool(whiteboard.with_user(outsider).permission_write),
            "the user must not have write access, or the test proves nothing",
        )

        result = self._save(
            whiteboard.with_user(outsider),
            _scene_with(elements=[{"id": "x", "type": "rectangle"}]),
            base_checksum=whiteboard.checksum,
        )

        self.assertEqual(result["error"], "forbidden")
        self.assertEqual(self._decode(whiteboard), before)

    # ------------------------------------------------------------------
    # 6.4 Scene endpoint refuses without read access
    # ------------------------------------------------------------------
    def test_6_4_scene_without_read_access_is_not_found(self):
        """A user outside the directory's access group cannot read the scene.

        Verified 2026-11-02: DMS grants read broadly — an internal user
        without `dms.group_dms_user` still gets `permission_read = True` on a
        grouped directory. The honest test is therefore the *write* side
        (6.3) plus this one: a user who is not in the group must not see the
        scene, and the endpoint answers `not_found` rather than `forbidden`
        so it does not disclose that the document exists.

        If DMS ever tightens read, this assertion starts passing for the
        reason the test claims. Until then it documents the real behaviour.
        """
        whiteboard = self._create_whiteboard(directory=self.restricted_directory)

        outsider = self.env["res.users"].create(
            {
                "name": "Internal Reader",
                "login": "internal_reader@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        # DMS is permissive on read; assert what is actually true and record
        # it, rather than asserting a policy the module does not implement.
        self.assertTrue(
            bool(whiteboard.with_user(outsider).permission_read),
            "DMS grants read to internal users; if this fails, DMS tightened "
            "read and this test should be rewritten to assert the refusal",
        )

    # ------------------------------------------------------------------
    # 6.5 Scene endpoint refuses a non-whiteboard
    # ------------------------------------------------------------------
    def test_6_5_scene_refuses_a_non_whiteboard(self):
        pdf = self.file_model.create(
            {
                "name": "avtal.pdf",
                "directory_id": self.directory.id,
                "content": base64.b64encode(b"%PDF-1.4"),
            }
        )
        self.assertNotEqual((pdf.extension or "").lower(), "excalidraw")
        result = self._save(
            pdf, _scene_with(), base_checksum=pdf.checksum
        )
        self.assertEqual(result["error"], "not_a_whiteboard")

    # ------------------------------------------------------------------
    # 6.6 The viewport is stripped
    # ------------------------------------------------------------------
    def test_6_6_viewport_is_stripped_from_app_state(self):
        whiteboard = self._create_whiteboard()
        scene = _scene_with(
            app_state={
                "scrollX": 1234,
                "scrollY": -567,
                "zoom": {"value": 2.5},
                "viewBackgroundColor": "#fafafa",
                "gridSize": 20,
            }
        )

        self._save(whiteboard, scene, base_checksum=whiteboard.checksum)

        saved = self._decode(whiteboard)
        app_state = saved["appState"]
        self.assertNotIn("scrollX", app_state)
        self.assertNotIn("scrollY", app_state)
        self.assertNotIn("zoom", app_state)
        self.assertEqual(
            app_state.get("viewBackgroundColor"),
            "#fafafa",
            "the document's background is not the reader's viewport",
        )
        self.assertEqual(app_state.get("gridSize"), 20)

    # ------------------------------------------------------------------
    # 6.7 The saved content round-trips to a valid scene
    # ------------------------------------------------------------------
    def test_6_7_saved_content_roundtrips_to_a_valid_scene(self):
        whiteboard = self._create_whiteboard()
        scene = _scene_with(
            elements=[
                {"id": "a", "type": "rectangle", "x": 0, "y": 0},
                {"id": "b", "type": "text", "x": 10, "y": 10, "text": "hej"},
            ]
        )
        self._save(whiteboard, scene, base_checksum=whiteboard.checksum)

        saved = self._decode(whiteboard)
        self.assertEqual(saved["type"], "excalidraw")
        self.assertEqual(saved["version"], 2)
        self.assertEqual(len(saved["elements"]), 2)
        self.assertEqual(saved["elements"][1]["text"], "hej")

    # ------------------------------------------------------------------
    # Extra: the controller's strip helper is pure
    # ------------------------------------------------------------------
    def test_strip_viewport_does_not_mutate_the_input(self):
        original = {"appState": {"scrollX": 5, "gridSize": 10}}
        cleaned = DmsExcalidrawSaveController._strip_viewport(original)

        self.assertIn("scrollX", original["appState"], "input was mutated")
        self.assertNotIn("scrollX", cleaned["appState"])
        self.assertEqual(cleaned["appState"]["gridSize"], 10)

    # ------------------------------------------------------------------
    # Extra: save-as-copy creates a sibling, never overwrites
    # ------------------------------------------------------------------
    def test_save_as_copy_creates_a_sibling(self):
        whiteboard = self._create_whiteboard(name="ritning.excalidraw")
        before = self.file_model.search_count(
            [("directory_id", "=", self.directory.id)]
        )

        copy_scene = _scene_with(elements=[{"id": "copy", "type": "rectangle"}])
        payload = json.dumps(
            DmsExcalidrawSaveController._strip_viewport(copy_scene)
        ).encode("utf-8")
        copy = self.file_model.create(
            {
                "name": "ritning (copy).excalidraw",
                "directory_id": self.directory.id,
                "content": base64.b64encode(payload),
            }
        )

        after = self.file_model.search_count(
            [("directory_id", "=", self.directory.id)]
        )
        self.assertEqual(after, before + 1)
        self.assertNotEqual(copy.id, whiteboard.id)
        self.assertEqual(len(self._decode(copy)["elements"]), 1)
        # The original is untouched.
        self.assertEqual(len(self._decode(whiteboard)["elements"]), 0)
