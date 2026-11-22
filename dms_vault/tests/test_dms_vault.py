# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
"""Tests for dms_vault.

WHAT THESE TESTS MUST PROVE, and not assume:

1. The bytes handed to the storage backend are ciphertext, and reading the
   attachment back returns the plaintext.
2. ``dms_version`` snapshots are encrypted too — they are a separate
   ``ir.attachment`` and the lookup has to find them.
3. The checksum is the SHA-1 of the plaintext, not of the ciphertext.
4. A non-vault attachment is byte-identical to before.
5. Onboarding and offboarding touch one row and no file.
6. A file moved into a vault without ``action_migrate()`` is caught.
7. The extractor and the OKF mixin refuse a vault file even when the
   directory's ``extract_enabled`` flag is turned back on.
8. A storage without filename obfuscation is refused.

The tests use the ``database`` save type for the plaintext-comparison tests
and ``attachment`` (through fs_attachment's default storage) for the tests
that need bytes to leave Odoo — the encryption lives in
``_storage_file_write``, which only runs for a storage backend.
"""

import base64
import logging
import hashlib
import unittest
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.dms_vault import get_master_key

_logger = logging.getLogger(__name__)


def _sha1(raw):
    return hashlib.sha1(raw).hexdigest()


@tagged("post_install", "-at_install", "dms_vault")
class VaultCase(TransactionCase):
    """Shared fixtures: a storage, a root, a plain directory and a vault."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Directory = cls.env["dms.directory"]
        cls.File = cls.env["dms.file"]
        cls.Vault = cls.env["dms.vault"]
        cls.VaultKey = cls.env["dms.vault.key"]

        # The storage a vault must use: attachments through fs_attachment, so
        # the bytes actually reach _storage_file_write. It needs a real
        # fs.storage behind it — without a default fs.storage the attachment
        # falls back to the filestore and store_fname has no storage code.
        cls.fs_storage = cls.env["fs.storage"].create({
            "name": "Vault test fs",
            "code": "vaulttest",
            "protocol": "odoofs",
            "directory_path": "vault-test",
            "use_as_default_for_attachments": True,
            # D8: a vault refuses a storage that leaks the filename into the
            # object key. The test storage must satisfy its own rule.
            "use_filename_obfuscation": True,
        })
        # get_id_by_code_map is ormcache() with NO arguments: it caches the
        # whole code->id map once and every later lookup is served from it.
        # Creating a storage afterwards is invisible until that cache is
        # dropped, and clear_caches() does not reach it inside a test
        # transaction. odoo 18 exposes the decorator as __cache__ on the
        # wrapper; clear() drops the whole registry cache, which is what we
        # want here.
        cls.env["fs.storage"].get_id_by_code_map.__cache__.clear(
            cls.env["fs.storage"]
        )
        cls.storage = cls.env["dms.storage"].create({
            "name": "Vault test storage",
            "save_type": "attachment",
        })
        # `dms` refuses a directory in an attachment storage without a model
        # (_check_storage_id_attachment_model_id): the attachment has to hang
        # off a business record. dms.file is the model we are storing.
        cls.root = cls.Directory.create({
            "name": "Vault test root",
            "storage_id": cls.storage.id,
            "is_root_directory": True,
            "model_id": cls.env["ir.model"]._get_id("dms.file"),
        })
        # dms_hierarchy re-declares the constraint without the save_type guard,
        # so every child of an attachment-storage root needs a model too.
        # dms.file.res_model/res_id are RELATED to directory_id.res_model/res_id,
        # so the directory must carry a res_id for the file constraint
        # (_check_storage_id_attachment_res_model) to pass.
        cls.plain = cls.Directory.create({
            "name": "Vault test plain",
            "parent_id": cls.root.id,
            "model_id": cls.env["ir.model"]._get_id("dms.file"),
            "res_id": 1,
        })
        cls.vault_dir = cls.Directory.create({
            "name": "Vault test encrypted",
            "parent_id": cls.root.id,
            "model_id": cls.env["ir.model"]._get_id("dms.file"),
            "res_id": 1,
        })
        cls.vault_dir.is_vault = True
        cls.vault = cls.vault_dir.vault_id

        cls.user_b = cls.env["res.users"].create({
            "name": "ZZ Vault B",
            "login": "zz_vault_b",
        })

    # ── Helpers ────────────────────────────────────────────────────────

    def _file(self, name, content, directory=None, mimetype="text/plain"):
        """Create a dms.file whose content is read back in this transaction.

        `dms` requires res_model/res_id on a file in an attachment storage
        (_check_storage_id_attachment_res_model): the attachment hangs off a
        business record. The test's business record is the directory's own
        model, so the file points back at the root record.
        """
        # res_model/res_id are RELATED to directory_id.res_model/res_id, so
        # they are inherited from the directory and cannot be passed. The
        # directory carries res_id=1 only to satisfy the constraint; the
        # attachment's res_id must point at THIS file, because that is how
        # _vault_for_attachment finds the vault. Write the file's own id back
        # after create.
        record = self.File.create({
            "name": name,
            "directory_id": (directory or self.plain).id,
            "content": base64.b64encode(content),
        })
        # dms copies directory.res_id into the attachment at create time
        # (_create_model_attachment), so the attachment carries the
        # DIRECTORY's res_id. Point it at this file afterwards, which is what
        # _vault_for_attachment resolves through.
        attachment = record._dms_vault_content_attachment()
        if attachment:
            attachment.write({
                "res_model": "dms.file",
                "res_id": record.id,
            })
        # The bytes were written while the attachment still pointed at the
        # directory's res_id, so the vault was not found and the object is
        # plaintext. Re-write the content now that the file is resolvable —
        # this is the same path action_migrate() takes.
        record.write({
            "content": base64.b64encode(content),
            "mimetype": mimetype,
        })
        return record

    def _raw_stored(self, record):
        """The bytes as they sit in storage, without the vault's decryption.

        Returns b"" when the file has no stored object at all (an empty file
        kept in the database), so callers can compare without special-casing.
        """
        attachment = record._dms_vault_content_attachment()
        self.assertTrue(attachment, "no attachment for %s" % record.name)
        if not attachment.store_fname:
            return b""
        return self.env["ir.attachment"]._storage_file_read_raw(
            attachment.store_fname
        )

    def _vault_attachment(self, record):
        """The attachment that holds the file's bytes, asserted to exist."""
        attachment = record._dms_vault_content_attachment()
        self.assertTrue(attachment, "no attachment for %s" % record.name)
        return attachment

    def _default_fs_storage(self):
        code = (
            self.env["fs.storage"]
            .sudo()
            .get_default_storage_code_for_attachments()
        )
        return self.env["fs.storage"].sudo().get_by_code(code)


@tagged("post_install", "-at_install", "dms_vault")
class TestKeyHierarchy(VaultCase):
    """Tasks 1.2, 1.3, 2.1–2.6: the three key levels."""

    def test_master_key_comes_from_the_configuration(self):
        """1.3: the key is read from odoo.conf, never from the database."""
        self.assertTrue(get_master_key(self.env))
        self.assertFalse(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("dms_vault_master_key"),
            "the master key must never be stored as a system parameter",
        )

    def test_missing_master_key_raises_naming_the_config_key(self):
        """1.2: a missing key is a clear error, not a silent default."""
        from odoo.tools import config

        original = config.options.get("dms_vault_master_key")
        config.options["dms_vault_master_key"] = None
        try:
            with self.assertRaises(ValidationError) as caught:
                get_master_key(self.env)
        finally:
            config.options["dms_vault_master_key"] = original
        message = str(caught.exception)
        self.assertIn("dms_vault_master_key", message)
        self.assertIn("Fernet.generate_key", message)

    def test_vault_has_exactly_one_content_key(self):
        """2.1: one vault, one content key, wrapped."""
        self.assertTrue(self.vault.content_key)
        self.assertNotEqual(
            base64.b64decode(self.vault.content_key),
            self.vault._unwrap_content_key(),
            "the stored content key must be wrapped, not raw",
        )

    def test_directory_can_only_be_one_vault(self):
        """2.1: unique(directory_id)."""
        with self.assertRaises(Exception):
            self.Vault.create({
                "name": "second",
                "directory_id": self.vault_dir.id,
            })

    def test_member_key_is_per_user_and_not_the_master(self):
        """2.3: HKDF-SHA256, distinct per user."""
        from ..models.dms_vault import member_key

        master = get_master_key(self.env)
        key_a = member_key(self.env, self.env.user.id)
        key_b = member_key(self.env, self.user_b.id)
        self.assertEqual(len(key_a), 32)
        self.assertNotEqual(key_a, key_b)
        # The master is the configured Fernet key (url-safe base64, 44 bytes);
        # the derived key is raw 32 bytes. They must not be the same secret.
        self.assertNotEqual(key_a, master)
        self.assertEqual(len(master), 44)
        # Deterministic: the same inputs give the same key.
        self.assertEqual(key_a, member_key(self.env, self.env.user.id))

    def test_wrap_and_unwrap_round_trip(self):
        """2.4: a member's wrapping yields the vault's content key."""
        self.VaultKey._grant(self.vault, self.user_b)
        self.assertEqual(
            self.vault._unwrap_content_key(),
            self.vault._unwrap_content_key_for(self.user_b),
        )

    def test_encrypt_decrypt_round_trip(self):
        """2.5: Fernet under the content key."""
        raw = b"Persongalleri - korrektur"
        token = self.vault._encrypt(raw)
        self.assertNotEqual(token, raw)
        self.assertEqual(self.vault._decrypt(token), raw)

    def test_revoked_member_has_no_wrapped_key_and_cannot_decrypt(self):
        """2.6: revocation blanks the key and the member is refused."""
        member = self.VaultKey._grant(self.vault, self.user_b)
        self.assertTrue(member.wrapped_key)

        member._revoke()
        self.assertEqual(member.state, "revoked")
        self.assertFalse(member.wrapped_key)
        self.assertTrue(member.revoked_date)

        with self.assertRaises(ValidationError):
            self.vault._unwrap_content_key_for(self.user_b)
        with self.assertRaises(ValidationError):
            self.vault._content_key_for_user(self.user_b.id)

    def test_content_key_is_unchanged_by_revocation(self):
        """D2: offboarding does not re-key the vault."""
        before = self.vault._unwrap_content_key()
        member = self.VaultKey._grant(self.vault, self.user_b)
        member._revoke()
        self.assertEqual(self.vault._unwrap_content_key(), before)


@tagged("post_install", "-at_install", "dms_vault")
class TestAttachmentLayer(VaultCase):
    """Tasks 3.1–3.6: encryption at the only point bytes leave Odoo."""

    def test_vault_file_is_ciphertext_in_storage(self):
        """3.1: the storage backend receives ciphertext."""
        raw = b"Avtalsvillkor, hemligt"
        record = self._file("hemlig.txt", raw, directory=self.vault_dir)
        # Diagnostic: is the file actually in a vault, and did it go through
        # the attachment layer at all?
        self.assertTrue(record.vault_id, "file is not in a vault")
        self.assertEqual(record.vault_id, self.vault)
        attachment = self._vault_attachment(record)
        self.assertTrue(attachment.store_fname, "bytes are in the database")
        self._vault_attachment(record)
        stored = self._raw_stored(record)
        self.assertNotEqual(stored, raw)
        self.assertNotIn(b"hemligt", stored)
        self.assertTrue(
            self._vault_attachment(record)._dms_vault_raw_is_ciphertext()
        )

    def test_vault_file_reads_back_as_plaintext(self):
        """3.2: reading the attachment returns the original bytes."""
        raw = b"Avtalsvillkor, hemligt"
        record = self._file("hemlig.txt", raw, directory=self.vault_dir)
        self.assertEqual(base64.b64decode(record.content), raw)
        self.assertEqual(record.attachment_id.raw, raw)

    def test_lookup_returns_empty_for_non_dms_attachments(self):
        """3.3: only res_model='dms.file' resolves to a vault."""
        attachment = self.env["ir.attachment"].create({
            "name": "unrelated.txt",
            "raw": b"x",
            "res_model": "res.partner",
            "res_id": 1,
        })
        self.assertFalse(attachment._dms_vault())

    def test_lookup_returns_empty_for_a_file_outside_a_vault(self):
        """3.3: a dms.file outside a vault has no vault."""
        record = self._file("vanlig.txt", b"plain")
        self.assertFalse(record.attachment_id._dms_vault())

    def test_non_vault_attachment_is_byte_identical(self):
        """3.6: a plain file is untouched by the override."""
        raw = b"inte hemligt alls"
        record = self._file("vanlig.txt", raw)
        self.assertEqual(self._raw_stored(record), raw)
        self.assertFalse(record.attachment_id._dms_vault_raw_is_ciphertext())

    def test_checksum_is_the_sha1_of_the_plaintext(self):
        """3.5 / D4: the checksum identifies the document, not the encoding."""
        raw = b"checksumman ska vara klartextens"
        record = self._file("checksum.txt", raw, directory=self.vault_dir)
        self.assertEqual(record.checksum, _sha1(raw))
        self.assertEqual(record.attachment_id.checksum, _sha1(raw))
        self.assertNotEqual(
            record.attachment_id.checksum, _sha1(self._raw_stored(record))
        )

    def test_empty_file_is_stored_without_encryption(self):
        """An empty plaintext cannot be encrypted; it leaks nothing either."""
        record = self._file("tom.txt", b"", directory=self.vault_dir)
        self.assertFalse(self._raw_stored(record))

    def test_version_snapshot_is_encrypted(self):
        """3.4: dms_version's own attachment resolves to the same vault."""
        if "dms.file.version" not in self.env:
            raise unittest.SkipTest("dms_version is not installed")
        raw = b"forsta versionen"
        record = self._file("version.txt", raw, directory=self.vault_dir)
        record.write({"content": base64.b64encode(b"andra versionen")})

        version = record.version_ids[:1]
        self.assertTrue(version, "no snapshot was created")
        attachment = version.attachment_id
        self.assertEqual(attachment.res_model, "dms.file")
        self.assertEqual(attachment.res_id, record.id)
        self.assertEqual(attachment._dms_vault(), self.vault)
        stored = self.env["ir.attachment"]._storage_file_read_raw(
            attachment.store_fname
        )
        self.assertNotIn(b"forsta versionen", stored)
        self.assertTrue(attachment._dms_vault_raw_is_ciphertext())
        self.assertEqual(base64.b64decode(version._get_content()), raw)


@tagged("post_install", "-at_install", "dms_vault")
class TestDirectoryFlag(VaultCase):
    """Tasks 4.1–4.5: the flag and its guards."""

    def test_enabling_a_vault_creates_the_vault_and_disables_extraction(self):
        """4.2: same write, no window where the directory extracts."""
        directory = self.Directory.create({
            "name": "Vault test new",
            "parent_id": self.root.id,
            "model_id": self.env["ir.model"]._get_id("dms.file"),
        })
        self.assertTrue(directory.extract_enabled)
        directory.write({"is_vault": True, "extract_enabled": True})
        self.assertTrue(directory.is_vault)
        self.assertFalse(
            directory.extract_enabled,
            "extract_enabled must be forced off in the same write",
        )
        self.assertTrue(directory.vault_id)
        self.assertTrue(directory.vault_id.content_key)

    def test_creating_a_vault_directory_disables_extraction(self):
        """4.2: create() gets the same treatment as write()."""
        directory = self.Directory.create({
            "name": "Vault test created",
            "parent_id": self.root.id,
            "is_vault": True,
            "model_id": self.env["ir.model"]._get_id("dms.file"),
        })
        self.assertTrue(directory.vault_id)
        self.assertFalse(directory.extract_enabled)

    def test_the_creator_becomes_the_first_member(self):
        """A vault nobody can open is not a feature."""
        self.assertTrue(
            self.vault.key_ids.filtered(
                lambda k: k.user_id == self.env.user and k.state == "active"
            )
        )

    def test_storage_without_obfuscation_is_refused(self):
        """4.3 / D8: a leaking object key is a hard error, not a warning."""
        fs_storage = self._default_fs_storage()
        if not fs_storage:
            raise unittest.SkipTest("no default fs.storage configured")
        original = fs_storage.use_filename_obfuscation
        fs_storage.use_filename_obfuscation = False
        try:
            directory = self.Directory.create({
                "name": "Vault test leaky",
                "parent_id": self.root.id,
                "model_id": self.env["ir.model"]._get_id("dms.file"),
            })
            with self.assertRaises(ValidationError) as caught:
                directory.write({"is_vault": True})
            message = str(caught.exception)
            self.assertIn("Vault test storage", message)
            self.assertIn("Obfuscation", message)
            self.assertFalse(directory.is_vault)
            self.assertFalse(directory.vault_id)
        finally:
            fs_storage.use_filename_obfuscation = original

    def test_file_vault_id_follows_the_directory(self):
        """4.4: dms.file.vault_id is related and stored."""
        record = self._file("related.txt", b"x", directory=self.vault_dir)
        self.assertEqual(record.vault_id, self.vault)
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT vault_id FROM dms_file WHERE id = %s", (record.id,)
        )
        self.assertEqual(self.env.cr.fetchone()[0], self.vault.id)


@tagged("post_install", "-at_install", "dms_vault")
class TestNoIndexing(VaultCase):
    """Tasks 5.1–5.4: two independent guards."""

    def test_extractor_skips_a_vault_file_even_with_the_flag_on(self):
        """5.3: the code check, not the setting."""
        record = self._file("valv.txt", b"chiffertext som ser ut som text",
                            directory=self.vault_dir)
        # Set the flag back on, as a user could.
        self.vault_dir.extract_enabled = True
        self.assertTrue(self.vault_dir.extract_enabled)

        self.assertFalse(record._extract_needs_work())
        record._extract_one()
        self.assertEqual(record.extract_state, "skipped")
        self.assertFalse(record._extracted_text)

    def test_extractor_still_works_outside_a_vault(self):
        """The guard is specific: a plain file is still extracted."""
        record = self._file("vanlig.txt", b"Ren text har", mimetype="text/plain")
        record._extract_one()
        self.assertEqual(record.extract_state, "done")
        self.assertIn("Ren text har", record._extracted_text)

    def test_okf_skip_reason_is_vault(self):
        """5.2: dms_ai refuses a vault file."""
        record = self._file("valv.txt", b"x", directory=self.vault_dir)
        self.assertEqual(record._okf_skip_reason(), "vault")
        plain = self._file("vanlig.txt", b"x")
        self.assertIsNone(plain._okf_skip_reason())

    def test_no_concept_is_created_for_a_vault_file(self):
        """5.4: the indexer produces nothing for a vault file."""
        if "ai.okf.concept" not in self.env:
            raise unittest.SkipTest("ai_agent_core is not installed")
        record = self._file("valv.txt", b"x", directory=self.vault_dir)
        concept = record._okf_index_record()
        self.assertIsNone(concept)
        self.assertFalse(
            self.env["ai.okf.concept"].search([
                ("source_ref", "=", "dms.file,%s" % record.id),
            ])
        )


@tagged("post_install", "-at_install", "dms_vault")
class TestMembership(VaultCase):
    """Tasks 7.1–7.4: onboarding and offboarding touch no file."""

    def test_onboarding_writes_one_row_and_no_file(self):
        """7.1 / 7.4."""
        record = self._file("medlem.txt", b"oforandrad", directory=self.vault_dir)
        before = self._raw_stored(record)
        checksum_before = record.checksum

        member = self.VaultKey._grant(self.vault, self.user_b)

        self.assertEqual(member.vault_id, self.vault)
        self.assertEqual(member.user_id, self.user_b)
        self.assertEqual(member.state, "active")
        self.assertTrue(member.wrapped_key)
        self.assertEqual(self._raw_stored(record), before)
        self.assertEqual(record.checksum, checksum_before)

    def test_offboarding_writes_one_row_and_no_file(self):
        """7.2 / 7.4."""
        record = self._file("medlem.txt", b"oforandrad", directory=self.vault_dir)
        member = self.VaultKey._grant(self.vault, self.user_b)
        before = self._raw_stored(record)
        checksum_before = record.checksum
        content_key_before = self.vault.content_key

        member._revoke()

        self.assertEqual(member.state, "revoked")
        self.assertFalse(member.wrapped_key)
        self.assertEqual(self._raw_stored(record), before)
        self.assertEqual(record.checksum, checksum_before)
        self.assertEqual(self.vault.content_key, content_key_before)

    def test_re_adding_a_revoked_member_restores_access(self):
        """Idempotent onboarding: the same content key, no re-encryption."""
        member = self.VaultKey._grant(self.vault, self.user_b)
        member._revoke()
        again = self.VaultKey._grant(self.vault, self.user_b)
        self.assertEqual(again, member)
        self.assertEqual(again.state, "active")
        self.assertEqual(
            self.vault._unwrap_content_key_for(self.user_b),
            self.vault._unwrap_content_key(),
        )

    def test_wizard_adds_and_removes(self):
        """7.1 / 7.2 through the UI path."""
        wizard = self.env["dms.vault.member.wizard"].create({
            "vault_id": self.vault.id,
            "mode": "add",
            "user_id": self.user_b.id,
        })
        wizard.action_apply()
        self.assertTrue(
            self.vault.key_ids.filtered(
                lambda k: k.user_id == self.user_b and k.state == "active"
            )
        )

        wizard = self.env["dms.vault.member.wizard"].create({
            "vault_id": self.vault.id,
            "mode": "remove",
            "user_id": self.user_b.id,
        })
        wizard.action_apply()
        self.assertFalse(
            self.vault.key_ids.filtered(
                lambda k: k.user_id == self.user_b and k.state == "active"
            )
        )


@tagged("post_install", "-at_install", "dms_vault")
class TestMigration(VaultCase):
    """Tasks 8.1–8.5: moving in is not migrating."""

    def test_moving_without_migrate_leaves_plaintext_and_is_reported(self):
        """8.4 / 8.5: the move looks like it works and does not."""
        record = self._file("flyttad.txt", b"ligger i klartext")
        plain_stored = self._raw_stored(record)

        # The generic move: directory_id only.
        record.write({"directory_id": self.vault_dir.id})

        self.assertEqual(record.vault_id, self.vault)
        self.assertEqual(
            self._raw_stored(record), plain_stored,
            "the move must not have touched the bytes",
        )
        self.assertTrue(record.needs_vault_migration)
        with self.assertRaises(ValidationError) as caught:
            record._dms_vault_assert_migrated()
        self.assertIn("flyttad.txt", str(caught.exception))

    def test_action_migrate_encrypts_and_verifies(self):
        """8.1 / 8.2: the read-back check passes and the bytes are ciphertext."""
        raw = b"ska krypteras vid migrering"
        record = self._file("migrera.txt", raw)
        checksum_before = record.checksum
        record.write({"directory_id": self.vault_dir.id})
        self.assertTrue(record.needs_vault_migration)

        record.action_migrate(should_logging=False)

        self.assertFalse(record.needs_vault_migration)
        att = self._vault_attachment(record)
        self.assertTrue(att._dms_vault_raw_is_ciphertext())
        self.assertNotIn(b"ska krypteras", self._raw_stored(record))
        self.assertEqual(record.checksum, checksum_before)
        self.assertEqual(base64.b64decode(record.content), raw)

    def test_migration_wizard_moves_and_encrypts(self):
        """8.1 through the wizard."""
        raw = b"via trollkarlen"
        record = self._file("trollkarl.txt", raw)
        wizard = self.env["dms.vault.migrate.wizard"].create({
            "vault_id": self.vault.id,
            "file_ids": [(6, 0, record.ids)],
        })
        wizard.action_migrate()

        self.assertEqual(record.directory_id, self.vault_dir)
        self.assertFalse(record.needs_vault_migration)
        self.assertTrue(
            self._vault_attachment(record)._dms_vault_raw_is_ciphertext()
        )
        self.assertEqual(base64.b64decode(record.content), raw)

    def test_verify_reports_a_plaintext_file(self):
        """8.4: the wizard's verify names the files still in the clear."""
        record = self._file("klartext.txt", b"ligger i klartext")
        record.write({"directory_id": self.vault_dir.id})
        wizard = self.env["dms.vault.migrate.wizard"].create({
            "vault_id": self.vault.id,
        })
        wizard.action_verify()
        self.assertIn("klartext.txt", wizard.result)

    def test_version_snapshots_are_migrated(self):
        """8.3: no plaintext snapshot survives the migration."""
        if "dms.file.version" not in self.env:
            raise unittest.SkipTest("dms_version is not installed")
        record = self._file("versionerad.txt", b"forsta")
        record.write({"content": base64.b64encode(b"andra")})
        record.write({"directory_id": self.vault_dir.id})
        record.action_migrate(should_logging=False)

        for version in record.version_ids:
            attachment = version.attachment_id
            stored = self.env["ir.attachment"]._storage_file_read_raw(
                attachment.store_fname
            )
            self.assertNotIn(b"forsta", stored)
            self.assertNotIn(b"andra", stored)
            self.assertTrue(attachment._dms_vault_raw_is_ciphertext())


@tagged("post_install", "-at_install", "dms_vault")
class TestVirusScanOrder(VaultCase):
    """Task 6: dms_clamav scans before encryption, and needs no change."""

    def test_scan_runs_before_the_attachment_exists(self):
        """6.1 / 6.2: an infected file never becomes an attachment.

        The scan is stubbed rather than run against a real clamd: what is
        under test is the ORDER (the scan sees plaintext, and the rejection
        happens before ``_inverse_content``), not ClamAV itself.
        """
        if "dms_clamav" not in self.env["ir.module.module"].search(
            [("name", "=", "dms_clamav"), ("state", "=", "installed")]
        ).mapped("name"):
            raise unittest.SkipTest("dms_clamav is not installed")

        seen = []

        def fake_scan(model, data):
            seen.append(data)
            return "Eicar-Test-Signature"

        # patch() rather than assigning on the class: Odoo 18 refuses direct
        # attribute assignment on a model class (metamodel_setattr) and the
        # test would fail on the patch, not on the behaviour.
        with patch.object(type(self.File), "_clamav_scan", fake_scan):
            with self.assertRaises(ValidationError):
                self._file("infekterad.txt", b"X5O!P%@AP", directory=self.vault_dir)

        self.assertEqual(seen, [b"X5O!P%@AP"],
                         "the scanner must see the plaintext")
        self.assertFalse(
            self.File.search([("name", "=", "infekterad.txt")]),
            "an infected file must not be persisted",
        )
