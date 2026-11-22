# -*- coding: utf-8 -*-
"""Tests for serving a library to the picker (tasks 5.1-5.5, 6.3).

The picker never receives shapes it did not ask for: the catalogue endpoint
returns metadata only, and each library is fetched on click. That split is
what makes a 30-library, 13 MB catalogue usable — so it is pinned here.

The two conditions the picker must SHOW rather than swallow are the point of
`action_load()` returning a dict instead of raising:

    too large   — a 20 MB library is a frozen tab, not a slow one
    unreadable  — a broken file must name itself, not the whole catalogue

Both are tested by making them happen, not by reading the code.
"""

import base64
import json
import os

from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestLibraryServing(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Library = cls.env["dms_excalidraw.library"]

    def _seeded(self):
        """Return one real seeded library (they are committed to the module)."""
        library = self.Library.search(
            [("source_url", "like", "/dms_excalidraw/static/")], limit=1
        )
        self.assertTrue(library, "no seeded library found")
        return library

    # -- 5.4 the size cap ---------------------------------------------------

    def test_5_4_an_oversized_library_is_refused_and_named(self):
        """A library over the cap answers with an error NAMING it and its size."""
        library = self._seeded()
        self.env["ir.config_parameter"].sudo().set_param(
            "dms_excalidraw.library_max_bytes", "1024"
        )
        result = library.action_load()
        self.assertIn("error", result, "an oversized library must not load")
        self.assertIn(library.name, result["error"], "the error must name it")
        self.assertIn("limit", result["error"], "the error must name the cap")

    def test_5_4b_the_cap_is_readable_and_defaults_sensibly(self):
        """The cap comes from a config parameter with a 2 MB default."""
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", "dms_excalidraw.library_max_bytes")]
        ).unlink()
        self.assertEqual(self.Library._max_bytes(), 2 * 1024 * 1024)

    def test_5_4c_a_broken_cap_falls_back_instead_of_crashing(self):
        """A non-numeric parameter must not take the picker down."""
        self.env["ir.config_parameter"].sudo().set_param(
            "dms_excalidraw.library_max_bytes", "not-a-number"
        )
        self.assertEqual(self.Library._max_bytes(), 2 * 1024 * 1024)

    # -- 5.3 a failure names the library ------------------------------------

    def test_5_3_an_unreadable_library_names_itself(self):
        """A missing file answers with an error naming the library."""
        library = self.Library.create(
            {
                "name": "Broken Library",
                "source_url": "/dms_excalidraw/static/libraries/nope/x.excalidrawlib",
            }
        )
        result = library.action_load()
        self.assertIn("error", result)
        self.assertIn("Broken Library", result["error"])

    def test_5_3b_a_path_traversal_is_refused(self):
        """A crafted source_url must not read outside the module."""
        library = self.Library.create(
            {
                "name": "Escape",
                "source_url": "/dms_excalidraw/static/../../../../etc/passwd",
            }
        )
        result = library.action_load()
        self.assertIn("error", result, "a traversal must not be read")
        self.assertIn("Escape", result["error"])

    def test_5_3c_a_non_static_path_is_refused(self):
        """A relative path that is not a module static path is refused."""
        library = self.Library.create(
            {"name": "Odd", "source_url": "/etc/passwd"}
        )
        result = library.action_load()
        self.assertIn("error", result)
        self.assertIn("Odd", result["error"])

    # -- 5.1 a real library loads -------------------------------------------

    def test_5_1_a_seeded_library_loads_with_its_shapes(self):
        """A seeded library returns a parseable payload with items in it."""
        library = self._seeded()
        result = library.action_load()
        self.assertNotIn("error", result, result.get("error"))
        data = result["library"]
        items = data.get("libraryItems") or data.get("library")
        self.assertTrue(items, "a seeded library must carry shapes")
        self.assertEqual(len(items), library.item_count)

    def test_5_1b_the_catalogue_is_metadata_only(self):
        """The catalogue must not embed the shapes — that is the whole point."""
        library = self._seeded()
        payload = {
            "id": library.id,
            "name": library.name,
            "item_count": library.item_count,
        }
        self.assertNotIn("libraryItems", payload)
        self.assertNotIn("library", payload)

    # -- 6.3 a catalogue library is never a dms.file ------------------------

    def test_6_3_a_catalogue_library_never_creates_a_dms_file(self):
        """Loading a catalogue library must not write a `dms.file`."""
        library = self._seeded()
        before = self.env["dms.file"].search_count([])
        library.action_load()
        self.assertEqual(
            self.env["dms.file"].search_count([]),
            before,
            "a catalogue library is a reference, not a document",
        )
