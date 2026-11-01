# -*- coding: utf-8 -*-

import base64
import json

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDmsExcalidraw(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "dms_excalidraw.url", "https://whiteboard.example.com"
        )
        cls.storage = cls.env["dms.storage"].create(
            {
                "name": "Excalidraw test storage",
                "save_type": "file",
            }
        )
        cls.root = cls.env["dms.directory"].create(
            {
                "name": "Whiteboards",
                "is_root_directory": True,
                "storage_id": cls.storage.id,
            }
        )
        cls.subdir = cls.env["dms.directory"].create(
            {
                "name": "Kund A",
                "parent_id": cls.root.id,
                "storage_id": cls.storage.id,
            }
        )

    def _make_file(self, name="ritning.excalidraw"):
        scene = json.dumps({"type": "excalidraw", "version": 2, "elements": []})
        return self.env["dms.file"].create(
            {
                "name": name,
                "directory_id": self.subdir.id,
                "content": base64.b64encode(scene.encode()),
                "mimetype": "application/json",
            }
        )

    def test_extension_controls_flag(self):
        """Bara .excalidraw ska få knappen."""
        drawing = self._make_file()
        self.assertTrue(drawing.can_open_in_excalidraw)

        other = self.env["dms.file"].create(
            {
                "name": "avtal.pdf",
                "directory_id": self.subdir.id,
                "content": base64.b64encode(b"%PDF-1.4"),
                "mimetype": "application/pdf",
            }
        )
        self.assertFalse(other.can_open_in_excalidraw)

    def test_open_raises_without_url(self):
        """Utan konfigurerad URL ska felet vara tydligt, inte en trasig länk."""
        self.env["ir.config_parameter"].sudo().set_param(
            "dms_excalidraw.url", ""
        )
        drawing = self._make_file()
        with self.assertRaises(UserError):
            drawing.open_in_excalidraw_action()

    def test_open_builds_webdav_url(self):
        """Sökvägen ska innehålla katalogkedjan, inte bara filnamnet."""
        drawing = self._make_file()
        action = drawing.open_in_excalidraw_action()
        self.assertEqual(action["type"], "ir.actions.act_url")
        url = action["url"]
        self.assertIn("whiteboard.example.com", url)
        self.assertIn("/webdav/", url)
        self.assertIn("Kund A", url)
        self.assertIn("ritning.excalidraw", url)

    def test_open_raises_on_wrong_extension(self):
        other = self.env["dms.file"].create(
            {
                "name": "avtal.pdf",
                "directory_id": self.subdir.id,
                "content": base64.b64encode(b"%PDF-1.4"),
                "mimetype": "application/pdf",
            }
        )
        with self.assertRaises(UserError):
            other.open_in_excalidraw_action()

    def _new_whiteboard(self, directory_id, name):
        """Skapa en whiteboard och returnera den skapade dms.file-posten.

        `action_new_whiteboard()` returnerar en action (dict), inte posten —
        den öppnar ritningen direkt i Excalidraw. Testet behöver posten, så
        vi hämtar den ur katalogen i stället för att anta en returtyp.
        """
        self.env["dms.file"].with_context(
            default_directory_id=directory_id,
            default_name=name,
        ).action_new_whiteboard()
        return self.env["dms.file"].search(
            [("directory_id", "=", directory_id)], order="id desc", limit=1
        )

    def test_new_whiteboard_creates_valid_scene(self):
        """Den skapade filen måste vara en giltig Excalidraw-scen."""
        drawing = self._new_whiteboard(self.subdir.id, "Flödesschema")

        self.assertEqual(drawing.name, "Flödesschema.excalidraw")
        self.assertEqual(drawing.directory_id, self.subdir)
        self.assertTrue(drawing.can_open_in_excalidraw)

        scene = json.loads(base64.b64decode(drawing.content))
        self.assertEqual(scene["type"], "excalidraw")
        self.assertEqual(scene["version"], 2)
        self.assertEqual(scene["elements"], [])
        self.assertIn("appState", scene)
        self.assertIn("files", scene)

    def test_new_whiteboard_requires_directory(self):
        """Utan katalog ska det vara ett tydligt fel."""
        with self.assertRaises(UserError):
            self.env["dms.file"].action_new_whiteboard()

    def test_new_whiteboard_appends_extension(self):
        drawing = self._new_whiteboard(self.subdir.id, "Redan döpt.excalidraw")
        self.assertEqual(drawing.name, "Redan döpt.excalidraw")

    def test_new_whiteboard_returns_an_action(self):
        """Metoden ska returnera en act_url mot Excalidraw — inte posten.

        Regressionstestet för den tidigare krashen: action_new_whiteboard()
        anropades på en TOM recordset från katalogvyn och föll på
        `ensure_one()` innan den nådde context-fallbacken.
        """
        action = self.env["dms.file"].with_context(
            default_directory_id=self.subdir.id,
            default_name="Aktionsprov",
        ).action_new_whiteboard()
        self.assertIsInstance(action, dict)
        self.assertEqual(action.get("type"), "ir.actions.act_url")
        self.assertIn("url", action)

    def test_webdav_path_skips_nested_root(self):
        """Rotkatalogen är monteringspunkten och ska bara förekomma en gång."""
        drawing = self._make_file()
        path = drawing._excalidraw_webdav_path("/webdav")
        self.assertEqual(path, "/webdav/Whiteboards/Kund A/ritning.excalidraw")
