# dms_vault

Encrypted directories in the DMS. A file placed in a vault is stored as
ciphertext, is never extracted, and never reaches the OKF index.

## What this protects — and what it does not

**Read the losses first. They are the reason the rest of this document exists.**

### The threat model is (b): a database dump without the master key

The key that unwraps everything lives in `odoo.conf`, on the application
server. The ciphertext lives in the storage backend — a filestore directory or
an S3 bucket. The two are separate, and the vault is the gap between them.

* **A stolen database dump alone reads nothing.** `pg_dump` gives you the
  `ir.attachment` rows, the `store_fname` keys and the wrapped content keys.
  Without `dms_vault_master_key` none of it unwraps.
* **A stolen storage bucket alone reads nothing.** Every object is Fernet
  ciphertext. The object keys are obfuscated (see below), so not even the
  filenames leak.
* **An administrator with both can read everything.** This is not end-to-end
  encryption and does not pretend to be. The server holds the master key
  because the server has to decrypt in order to serve the file. Anyone who can
  read `odoo.conf` and the storage can read every vault.
* **A member who has downloaded a file has it.** Revocation stops future
  access. It does not, and cannot, reach into a laptop that already has a copy.

### What the vault does NOT give you

| Not protected | Why |
|---|---|
| A compromised Odoo server | The master key is on that server, by design |
| Metadata: who uploaded what, when, to which directory | Stored in the clear in the database |
| File size | The ciphertext is the plaintext plus a fixed overhead |
| Files a member already downloaded | Revocation is forward-looking only |
| Re-scanning a file already in a vault | The bytes are ciphertext; ClamAV cannot read them |
| Recovery from a lost master key | There is none. See below |

## The key hierarchy

```
dms_vault_master_key            (odoo.conf — one per installation)
        │
        ├── HKDF-SHA256(master, "vault-member:<uid>")
        │           │
        │           └── wraps ──> dms.vault.key.wrapped_key   (per member)
        │
        └── wraps ──> dms.vault.content_key                   (per vault)
                            │
                            └── Fernet ──> the stored bytes
```

Three levels, each with one job:

1. **The master key** never leaves `odoo.conf`. It is a 44-byte URL-safe
   base64 Fernet key. `hooks.py` refuses to install the module without it and
   names the command to generate one.
2. **The member key is derived, not distributed.** `HKDF-SHA256(master,
   "vault-member:<uid>")` means adding a member creates one row and touches no
   file. There is no key material to send anywhere, and no way for one member
   to derive another's.
3. **The content key is per vault** and is what actually encrypts bytes. It is
   wrapped under the master key at creation — before any member exists — and
   under each member key on onboarding. Rotating a member's wrapping does not
   re-encrypt a single file.

`dms.vault.key.state` is `active` or `revoked`. A revoked member's
`wrapped_key` is cleared, so the unwrap fails for the right reason rather than
by accident.

## Where the encryption happens

At `ir.attachment`, in `_file_write` / `_storage_file_read`. Not at
`dms.file`.

The reason is coverage. Three different code paths put a file's bytes into
storage:

* `dms.file.content_file` — the `attachment=True` field
* `dms_version` — creates its own `ir.attachment` per snapshot
* anything else that stores through `ir.attachment`

Encrypting at `dms.file` would have left `dms_version` writing plaintext
snapshots into `ir.attachment` — the exact leak the vault exists to prevent.
Encrypting one layer lower covers all three without any of them knowing.

### The checksum describes the plaintext, deliberately

`_get_datas_related_values` computes `checksum = sha1(bin_data)` **before**
`_file_write`, so the checksum column is the hash of the plaintext even though
the stored object is ciphertext. Two consequences, both intended:

1. `ir.attachment.checksum` will not match the hash of the object in the
   bucket. It identifies the document, not its storage encoding.
2. `_get_fs_path()` uses that checksum as the object key, so identical files
   share one object even across vaults. That is deduplication, and it is safe:
   the object is ciphertext under a key the sharing party may not hold.

The read side must therefore decrypt before anything compares bytes to the
checksum — which is what `_storage_file_read` does.

## The guards

Two independent guards keep a vault file out of the index, because the failure
mode of the first is silent.

1. **The setting.** `dms.directory.extract_enabled` is forced to `False` in the
   same `write()` that sets `is_vault`. A setting can be flipped back by
   someone who does not know what it does.
2. **The code.** `models/dms_extract_guard.py` checks `vault_id` and answers
   `skipped` regardless of the flag. `dms_extract` is a hard dependency
   precisely so this override cannot lose the MRO race to `dms_extract`'s own
   definition — without it the load order is undefined and the guard can be
   silently skipped.

`dms_ai` adds a third: `_okf_skip_reason()` returns `'vault'`. A file in a
vault is never indexed, and its text never enters a concept body.

## Filename obfuscation is mandatory

A vault stores ciphertext, but an object key built from the filename still
exposes the document name to anyone who can list the bucket. The directory's
storage must have `use_filename_obfuscation = true`; enabling a vault on a
storage without it raises a `ValidationError` naming the storage. This is a
hard error, not a warning — a warning would be read once and forgotten.

## Virus scanning

`dms_clamav` hooks `dms.file.write()` **before** `super()`, which runs before
`_inverse_content` creates the attachment. The scan therefore sees plaintext,
which is the only thing ClamAV can read, and a rejected file never becomes an
`ir.attachment` at all.

The cost is real: **a file already in a vault can never be re-scanned.** The
bytes are ciphertext. A periodic re-scan would have to decrypt them, which
means running the scan with the master key in hand. That is not built.

## Migration

Moving a file into a vault directory is not enough. `wizard.dms.file.move`
writes `directory_id` and nothing else — the bytes stay where they were, in the
clear, while the file claims to be in a vault. `action_migrate()` is the only
path that encrypts an existing file, and it:

1. Re-writes the bytes on the attachment that holds them, with the vault in the
   context so `_file_write` encrypts.
2. Does the same for every `dms_version` snapshot — they were written before
   the file entered the vault and are plaintext too.
3. Reads the file back, compares the plaintext SHA-1 with the checksum taken
   before the migration, and **checks that the stored object is actually
   ciphertext**. A read-back through `content` decrypts transparently, so it
   proves the bytes are readable, not that they are encrypted.

`needs_vault_migration` marks a file that sits in a vault without having been
migrated. `_dms_vault_assert_migrated()` raises on it, and the wizard's verify
step lists them.

## Operational rules

* **`odoo.conf` and the database must never share a backup archive.** The whole
  point is that a dump without the master key reads nothing. A backup that
  contains both hands an attacker everything.
* **Losing the master key is unrecoverable.** There is no recovery path and no
  escrow. Every file in every vault becomes permanently unreadable. Store the
  key the way you store the only copy of anything.
* **Changing the master key is not a rotation.** Every member key is derived
  from it and every content key is wrapped under it. A new master key means
  every existing vault is unreadable. The schema supports rotation; the code
  does not implement it, and there is no UI for it.

## Tests

```
checkmodule -d dms -m dms_vault -t --test-tags '/dms_vault' --multi-user
```

50 tests across eight classes. They cover the key hierarchy, the attachment
layer (ciphertext in storage, plaintext on read, version snapshots), the
directory flag and its guards, the two indexing guards, the scan order, member
onboarding and offboarding, and migration including the plaintext-after-move
case.
