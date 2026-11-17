# -*- coding: utf-8 -*-
"""Tests for the shape-library catalogue (tasks 7.1-7.7).

The contract under test is `models/dms_excalidraw_library.py`:

    dms_excalidraw.library._parse_library(blob)   validate + normalise
    dms_excalidraw.library._library_items(data)   v1 `library` / v2 `libraryItems`
    dms_excalidraw.library._item_count(items)     the count shown in the picker

and the sync in `models/dms_excalidraw_library_sync.py`:

    _sync_from_upstream()   upsert by upstream_id, deactivate the vanished
    _authors_text(authors)  flatten the upstream author list

**The format has TWO shapes, not one.** The design documented only v2
(`libraryItems`), but 10 of the 30 seeded libraries are v1 (`library`, a list
of bare element arrays, and `"version": "1"` as a STRING). Both load in
Excalidraw 0.18.1. A parser that only knows v2 silently hides a third of the
catalogue — so the tests below pin both shapes, including the string version.
"""

import json

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon

from ..models.dms_excalidraw_library import UnknownLibraryVersion


def _v2_library(items=None):
    """A minimal v2 library, the shape the design documented."""
    return json.dumps(
        {
            "type": "excalidrawlib",
            "version": 2,
            "source": "https://excalidraw.com",
            "libraryItems": items
            if items is not None
            else [{"id": "a", "status": "published", "elements": []}],
        }
    )


def _v1_library(items=None):
    """A minimal v1 library — `library`, bare element arrays, STRING version.

    This is the shape 10 of the 30 committed seed files actually have.
    """
    return json.dumps(
        {
            "type": "excalidrawlib",
            "version": "1",
            "library": items if items is not None else [[{"type": "line"}]],
        }
    )


@tagged("post_install", "-at_install")
class TestLibraryFormat(BaseCommon):
    """Tasks 7.1, 7.2 and 4.1-4.3: the parser."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.Library = cls.env["dms_excalidraw.library"]

    # ------------------------------------------------------------------
    # 7.1 A malformed library is rejected
    # ------------------------------------------------------------------
    def test_7_1_malformed_library_is_rejected(self):
        cases = {
            "not JSON": "{not json",
            "not an object": "[1, 2, 3]",
            "wrong type": json.dumps({"type": "excalidraw", "version": 2}),
            "no item list": json.dumps(
                {"type": "excalidrawlib", "version": 2}
            ),
            "items not a list": json.dumps(
                {"type": "excalidrawlib", "version": 2, "libraryItems": {}}
            ),
        }
        for label, blob in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    self.Library._parse_library(blob)

    def test_7_1b_non_utf8_bytes_are_rejected(self):
        with self.assertRaises(ValueError):
            self.Library._parse_library(b"\xff\xfe\x00bad")

    # ------------------------------------------------------------------
    # 7.2 An unknown version is skipped, the rest load
    # ------------------------------------------------------------------
    def test_7_2_unknown_version_raises_the_skip_signal(self):
        blob = json.dumps(
            {"type": "excalidrawlib", "version": 99, "libraryItems": []}
        )
        with self.assertRaises(UnknownLibraryVersion):
            self.Library._parse_library(blob)

    def test_7_2b_unknown_version_is_also_a_valueerror(self):
        # The sync catches `UnknownLibraryVersion` to skip and continue; a
        # caller that only knows `ValueError` must still behave sanely.
        blob = json.dumps(
            {"type": "excalidrawlib", "version": 99, "libraryItems": []}
        )
        with self.assertRaises(ValueError):
            self.Library._parse_library(blob)

    def test_7_2c_one_bad_library_does_not_stop_the_others(self):
        blobs = [
            _v2_library(),
            json.dumps({"type": "excalidrawlib", "version": 99, "libraryItems": []}),
            _v1_library(),
        ]
        parsed, skipped = [], 0
        for blob in blobs:
            try:
                parsed.append(self.Library._parse_library(blob))
            except UnknownLibraryVersion:
                skipped += 1
        self.assertEqual(skipped, 1)
        self.assertEqual(len(parsed), 2)

    # ------------------------------------------------------------------
    # 4.1 / 4.2 Both real formats parse
    # ------------------------------------------------------------------
    def test_4_1_v2_library_parses(self):
        items = self.Library._parse_library(_v2_library())
        self.assertEqual(len(items), 1)

    def test_4_2_v1_library_parses_despite_a_string_version(self):
        # `"version": "1"` — a string. Comparing the raw value against (1, 2)
        # would reject every v1 library upstream ships.
        items = self.Library._parse_library(_v1_library())
        self.assertEqual(len(items), 1)

    def test_4_2b_v1_and_v2_report_through_the_same_key(self):
        v1 = json.loads(_v1_library())
        v2 = json.loads(_v2_library())
        self.assertIsNotNone(self.Library._library_items(v1))
        self.assertIsNotNone(self.Library._library_items(v2))
        self.assertIsNone(self.Library._library_items({"type": "excalidrawlib"}))

    # ------------------------------------------------------------------
    # 4.3 item_count is computed from the item list
    # ------------------------------------------------------------------
    def test_4_3_item_count_matches_the_item_list(self):
        items = self.Library._parse_library(_v2_library([{}, {}, {}]))
        self.assertEqual(self.Library._item_count(items), 3)


@tagged("post_install", "-at_install")
class TestLibrarySync(BaseCommon):
    """Tasks 7.3, 7.4 and 3.x: the sync, with the network stubbed out."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.Library = cls.env["dms_excalidraw.library"]
        cls.config = cls.env["ir.config_parameter"].sudo()

    def setUp(self):
        super().setUp()
        # The sync must never reach the network in a test. Each test installs
        # its own index by patching `_fetch_json`.
        self._index = []
        self._fetch_calls = []

    def _install_index(self, index):
        """Make the sync read a canned index instead of the network.

        ⚠️ Patching the model is a dead end. `self.Library._fetch_json = ...`
        raises `AttributeError: ... is read-only` (a `MetaModel`'s attributes
        are read-only), and patching the CLASS instead makes Odoo's test
        loader fail the whole suite with
        `AssertionError: Found unexpected attributes on
        dms_excalidraw.library: _fetch_json` — it compares the model's
        attribute set before and after each test.

        So the seam is `urllib` itself: `_fetch_json` builds a
        `urllib.request.Request` and calls `urlopen`, which is what gets
        replaced. That also exercises the real `_fetch_json` — the JSON
        decoding, the error wrapping and the timeout — instead of skipping it.
        """
        import urllib.error
        import urllib.request

        # An Exception means "the fetch fails"; it has no JSON payload.
        payload = (
            b""
            if isinstance(index, Exception)
            else json.dumps(index).encode("utf-8")
        )

        class _FakeResponse:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def _fake_urlopen(request, timeout=None):
            url = getattr(request, "full_url", str(request))
            self._fetch_calls.append(url)
            if isinstance(index, Exception):
                raise index
            return _FakeResponse(payload)

        original = urllib.request.urlopen
        urllib.request.urlopen = _fake_urlopen
        self.addCleanup(setattr, urllib.request, "urlopen", original)

    # ------------------------------------------------------------------
    # 7.3 Sync is idempotent by upstream_id
    # ------------------------------------------------------------------
    def test_7_3_sync_is_idempotent_by_upstream_id(self):
        self._install_index(
            [
                {
                    "id": "abc123",
                    "name": "Test library",
                    "description": "d",
                    "authors": [{"name": "A", "url": "https://a.example"}],
                    "source": "a/test.excalidrawlib",
                    "preview": "a/test.png",
                }
            ]
        )

        first = self.Library._sync_from_upstream()
        self.assertEqual(first["created"], 1)
        self.assertEqual(self.Library.search_count([("upstream_id", "=", "abc123")]), 1)

        second = self.Library._sync_from_upstream()
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 1)
        # The whole point: a second sync must not duplicate.
        self.assertEqual(self.Library.search_count([("upstream_id", "=", "abc123")]), 1)

    def test_7_3b_upstream_id_is_unique_at_the_database_level(self):
        self.Library.create({"name": "One", "upstream_id": "dup"})
        with self.assertRaises(Exception):
            self.Library.create({"name": "Two", "upstream_id": "dup"})

    def test_7_3c_source_url_is_built_from_the_relative_source(self):
        self._install_index(
            [{"id": "x1", "name": "N", "source": "author/lib.excalidrawlib"}]
        )
        self.Library._sync_from_upstream()
        record = self.Library.search([("upstream_id", "=", "x1")])
        self.assertTrue(
            record.source_url.endswith("/libraries/author/lib.excalidrawlib")
        )

    # ------------------------------------------------------------------
    # 7.4 A library removed upstream is deactivated, not deleted
    # ------------------------------------------------------------------
    def test_7_4_vanished_library_is_deactivated_not_deleted(self):
        self._install_index([{"id": "keep", "name": "Keep", "source": "k/k.excalidrawlib"}])
        self.Library._sync_from_upstream()

        # Second sync: "keep" is gone from upstream.
        self._install_index([{"id": "other", "name": "Other", "source": "o/o.excalidrawlib"}])
        counters = self.Library._sync_from_upstream()

        self.assertEqual(counters["deactivated"], 1)
        gone = self.Library.with_context(active_test=False).search(
            [("upstream_id", "=", "keep")]
        )
        self.assertTrue(gone, "the record must still exist")
        self.assertFalse(gone.active, "it must be deactivated, not deleted")
        # And it is gone from the default (active-only) search.
        self.assertFalse(self.Library.search([("upstream_id", "=", "keep")]))

    def test_7_4b_seeded_libraries_survive_a_sync_that_does_not_know_them(self):
        # A seed record has `last_sync = False`; it was never synced, so a
        # sync cannot conclude that it vanished upstream.
        seed = self.Library.create(
            {"name": "Seed", "upstream_id": "seed1", "source_url": "/x"}
        )
        self.assertFalse(seed.last_sync)

        self._install_index([{"id": "up", "name": "Up", "source": "u/u.excalidrawlib"}])
        self.Library._sync_from_upstream()

        seed.invalidate_recordset()
        self.assertTrue(seed.active, "a never-synced seed must not be deactivated")

    def test_7_4c_a_reappearing_library_is_reactivated(self):
        self._install_index([{"id": "flip", "name": "Flip", "source": "f/f.excalidrawlib"}])
        self.Library._sync_from_upstream()
        self._install_index([])
        self.Library._sync_from_upstream()
        self._install_index([{"id": "flip", "name": "Flip", "source": "f/f.excalidrawlib"}])
        self.Library._sync_from_upstream()

        record = self.Library.with_context(active_test=False).search(
            [("upstream_id", "=", "flip")]
        )
        self.assertTrue(record.active)

    # ------------------------------------------------------------------
    # 3.5 A failed sync leaves the catalogue intact
    # ------------------------------------------------------------------
    def test_3_5_a_failed_fetch_leaves_the_catalogue_intact(self):
        self.Library.create({"name": "Existing", "upstream_id": "e1"})
        before = self.Library.with_context(active_test=False).search_count([])

        self._install_index(UserError("Could not reach the upstream index"))
        with self.assertRaises(UserError):
            self.Library._sync_from_upstream()

        after = self.Library.with_context(active_test=False).search_count([])
        self.assertEqual(before, after)

    def test_3_5b_a_non_list_index_is_refused(self):
        self._install_index({"not": "a list"})
        with self.assertRaises(UserError):
            self.Library._sync_from_upstream()

    def test_3_5c_entries_without_id_or_name_are_skipped(self):
        self._install_index(
            [
                {"name": "No id", "source": "a/a.excalidrawlib"},
                {"id": "noid_name", "source": "b/b.excalidrawlib"},
                {"id": "good", "name": "Good", "source": "c/c.excalidrawlib"},
            ]
        )
        counters = self.Library._sync_from_upstream()
        self.assertEqual(counters["skipped"], 2)
        self.assertEqual(counters["created"], 1)

    # ------------------------------------------------------------------
    # 3.1 Sync is opt-in
    # ------------------------------------------------------------------
    def test_3_1_no_outbound_request_when_sync_is_disabled(self):
        self.config.set_param("dms_excalidraw.library_sync_enabled", "False")
        self._install_index([{"id": "x", "name": "X", "source": "x/x.excalidrawlib"}])

        with self.assertRaises(UserError):
            self.Library.action_sync_now()

        self.assertEqual(
            self._fetch_calls, [], "no fetch may happen while sync is off"
        )

    # ------------------------------------------------------------------
    # Authors
    # ------------------------------------------------------------------
    def test_authors_are_flattened_with_their_urls(self):
        text = self.Library._authors_text(
            [
                {"name": "Alice", "url": "https://a.example"},
                {"name": "Bob"},
            ]
        )
        self.assertIn("Alice", text)
        self.assertIn("https://a.example", text)
        self.assertIn("Bob", text)

    def test_authors_absent_is_false(self):
        self.assertFalse(self.Library._authors_text(None))
        self.assertFalse(self.Library._authors_text([]))


@tagged("post_install", "-at_install")
class TestLibrarySeed(BaseCommon):
    """Task 2.3 and 6.3: the seed is present, and is not a dms.file."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.Library = cls.env["dms_excalidraw.library"]

    def test_2_3_seed_catalogue_is_present(self):
        seeds = self.Library.search([("source_url", "like", "/static/lib/libraries/")])
        self.assertGreaterEqual(
            len(seeds),
            25,
            "the shipped seed should be ~30 libraries",
        )

    def test_2_3b_every_seed_points_at_a_static_path(self):
        for record in self.Library.search([]):
            if not record.source_url:
                continue
            with self.subTest(library=record.name):
                self.assertTrue(
                    record.source_url.startswith("/dms_excalidraw/static/"),
                    "a seed library must not point at the network: %s"
                    % record.source_url,
                )

    def test_2_3c_seed_records_report_an_item_count(self):
        for record in self.Library.search([("upstream_id", "!=", False)]):
            with self.subTest(library=record.name):
                self.assertGreater(record.item_count, 0)

    # ------------------------------------------------------------------
    # 7.6 A catalogue library does not create a dms.file
    # ------------------------------------------------------------------
    def test_7_6_a_catalogue_library_is_not_a_dms_file(self):
        before = self.env["dms.file"].search_count([])
        self.Library.create(
            {
                "name": "Not a document",
                "upstream_id": "notadoc",
                "source_url": "/dms_excalidraw/static/lib/libraries/x/library.excalidrawlib",
            }
        )
        after = self.env["dms.file"].search_count([])
        self.assertEqual(
            before,
            after,
            "a catalogue library must not create a dms.file — it has no "
            "folder, no retention and no business object",
        )


@tagged("post_install", "-at_install")
class TestDmsRuleWorkaround(BaseCommon):
    """The OCA `dms` rule workaround (security/dms_rule_workaround.xml).

    WHY THIS TEST EXISTS
    ====================
    `dms` 18.0 ships global record rules that compare a BOOLEAN field with a
    USER ID:

        domain_force = [('permission_create', '=', user.id)]

    `True == 2` is false, so the rule denies every record to every user. OCA
    works around it inside `_filtered_access()`, but `create()` takes a
    different path (`_check_access_dms_record` -> `ir.rule._compute_domain`)
    where the workaround never runs.

    The symptom is that an ADMINISTRATOR cannot create a folder:

        Uh-oh! ... Administrator (id=2) doesn't have 'create' access to
        - Directory (dms.directory)

    Our module rewrites the eight rules to `('permission_x', '=', True)`.
    This test pins that: if the rules ever revert (an OCA upgrade, a
    `repo_apply` that reinstalls `dms`), the test fails with the reason
    instead of a user hitting the bug in production.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

    def test_the_computed_rules_compare_against_true_not_user_id(self):
        for model_name in ("dms.directory", "dms.file"):
            model = self.env["ir.model"]._get(model_name)
            rules = self.env["ir.rule"].sudo().search(
                [
                    ("model_id", "=", model.id),
                    ("name", "like", "Apply computed"),
                ]
            )
            self.assertEqual(
                len(rules), 4, "%s should have four computed rules" % model_name
            )
            for rule in rules:
                with self.subTest(model=model_name, rule=rule.name):
                    self.assertNotIn(
                        "user.id",
                        rule.domain_force,
                        "The rule still compares a boolean with user.id, "
                        "which denies everyone. The workaround in "
                        "security/dms_rule_workaround.xml is not applied.",
                    )
                    # The stored domain is
                    #   [('permission_create', '=', True)]
                    # so match on the field and the True literal separately
                    # rather than on a formatting-specific substring.
                    self.assertIn(
                        "permission_",
                        rule.domain_force,
                        "The rule should filter on a permission field.",
                    )
                    self.assertRegex(
                        rule.domain_force,
                        r"\bTrue\b",
                        "The rule should compare the permission field "
                        "against the boolean True, not against user.id.",
                    )

    def test_an_administrator_can_create_a_directory(self):
        """The end-to-end proof: admin creates a folder and a subfolder."""
        Storage = self.env["dms.storage"].sudo()
        Group = self.env["dms.access.group"].sudo()
        Directory = self.env["dms.directory"]

        admin = self.env.ref("base.user_admin")

        storage = Storage.create(
            {"name": "Workaround test storage", "save_type": "file"}
        )
        access_group = Group.create(
            {
                "name": "Workaround test group",
                "perm_create": True,
                "perm_write": True,
                "perm_unlink": True,
                "explicit_user_ids": [(6, 0, [admin.id])],
            }
        )
        # Flush so the m2m rows exist before the rule's SQL subquery runs.
        access_group.flush_recordset()

        as_admin = Directory.with_user(admin)

        root = as_admin.create(
            {
                "name": "Workaround root",
                "is_root_directory": True,
                "storage_id": storage.id,
                "group_ids": [(6, 0, [access_group.id])],
            }
        )
        self.assertTrue(root.id)

        child = as_admin.create(
            {
                "name": "Workaround child",
                "parent_id": root.id,
                "storage_id": storage.id,
            }
        )
        self.assertTrue(child.id)

        child.unlink()
        root.unlink()
        access_group.unlink()
        storage.unlink()

    def test_a_fresh_install_has_an_access_group_for_administrators(self):
        """A new installation must be able to create a folder out of the box.

        `dms` ships zero access groups and its onboarding never mentions
        them, so without this seed the first action a user takes — create a
        folder — fails with an access error that names no missing group.
        """
        group = self.env.ref(
            "dms_excalidraw.access_group_administrators", raise_if_not_found=False
        )
        self.assertTrue(
            group,
            "data/dms_access_group_seed.xml did not create the "
            "'Administrators' access group",
        )
        self.assertTrue(group.perm_create)
        self.assertTrue(group.perm_write)
        self.assertTrue(group.perm_unlink)
        self.assertIn(
            self.env.ref("base.group_system"),
            group.group_ids,
            "base.group_system must be a member of the seed group, so an "
            "administrator can create the first directory",
        )
