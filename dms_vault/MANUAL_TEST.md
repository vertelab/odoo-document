# Manual test — dms_vault

A person who has never seen the module should be able to follow this and
verify that a vault actually encrypts, actually hides files from the index,
and actually refuses to lie about a half-done migration.

Run it on a test database with `dms`, `dms_extract`, `dms_ai` and `dms_clamav`
installed.

## 0. Before you start

Generate a master key and put it in `odoo.conf`:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```
dms_vault_master_key = <the 44-character key>
```

Restart Odoo. Without the key the module refuses to install — that is step 1 of
the test, not a problem to work around.

## 1. The module refuses to install without a key

1. Remove the `dms_vault_master_key` line from `odoo.conf`.
2. Restart Odoo and try to install `dms_vault`.

**Expect:** a `ValidationError` that names `dms_vault_master_key` and shows the
command to generate one. The module is not installed.

3. Put the key back and install.

**Expect:** the install completes.

## 2. Create a vault

1. Go to **Documents** and open a directory whose storage is `Attachment
   Storage`.
2. Open the directory's form and tick **Is Vault**.

**Expect:**
- A vault is created and linked to the directory.
- **Extract Enabled** is now unticked.
- You are listed as the first member with state **Active**.

3. Open the vault record.

**Expect:** a member list containing you, and a warning that revoking a member
does not re-encrypt anything they already downloaded.

## 3. A storage without obfuscation is refused

1. Go to **Settings → Technical → Storage → fs.storage** and open the storage
   behind your directory.
2. Untick **Use Filename Obfuscation** and save.
3. Go back to a *different* directory in that storage and tick **Is Vault**.

**Expect:** a `ValidationError` naming the storage and telling you to turn
obfuscation on. The directory is not made a vault.

4. Turn obfuscation back on.

## 4. Upload a file and verify the bytes are ciphertext

1. Upload `hemligt.txt` containing the text `detta ar hemligt` into the vault
   directory.
2. Find the file's `store_fname`:

```sql
SELECT id, store_fname, checksum, file_size
FROM ir_attachment
WHERE res_model = 'dms.file' AND res_field = 'content_file'
ORDER BY id DESC LIMIT 1;
```

3. Read the object from the storage backend:

```bash
cat <the storage path>/<store_fname without the protocol prefix>
```

**Expect:** the file on disk does **not** contain `detta ar hemligt`. It is
Fernet ciphertext — it starts with the byte `0x80` and is base64.

4. Open the file in Odoo.

**Expect:** it reads back as `detta ar hemligt`. The decryption is transparent;
the user sees no difference.

5. Compare the `checksum` column with the plaintext:

```bash
printf 'detta ar hemligt' | sha1sum
```

**Expect:** the checksum matches the **plaintext**, not the ciphertext. This is
deliberate — the checksum identifies the document, not its storage encoding.

## 5. The file is never indexed

1. Set the directory's **Extract Enabled** back on, as a user could.
2. Wait for the extraction cron, or run it:

```bash
sudo -u odoo odoo shell -d <db> --no-http
```

```python
env["dms.file"].search([("name", "=", "hemligt.txt")])._extract_one()
env.cr.commit()
```

**Expect:** `extract_state` is `skipped` and `extracted_text` is empty. The
code check beats the setting.

3. Search the OKF index for `hemligt`.

**Expect:** no concept exists for the file. A vault file never enters the
index.

## 6. Add and remove a member

1. Open the vault and add a second user as a member.

**Expect:** one new `dms.vault.key` row. No file's bytes changed — check a
`store_fname` before and after.

2. Log in as the second user and open `hemligt.txt`.

**Expect:** it reads normally.

3. Remove the second user from the vault.

**Expect:** their `dms.vault.key` is `revoked` and `wrapped_key` is empty.

4. Log in as that user again and open the file.

**Expect:** access is refused. The file's bytes are unchanged — revocation
does not re-encrypt.

## 7. Migration — the case that must not be reported as success

1. Upload `flyttad.txt` to a **normal** directory (outside any vault).
2. Move it into the vault directory with **Move** (not **Migrate**).
3. Open the file.

**Expect:** `needs_vault_migration` is set. The bytes are still plaintext —
step 4 of this section proves it.

4. Read the stored object as in section 4.

**Expect:** it is plaintext. The move changed the directory and nothing else.

5. Run **Migrate** on the file (or the migration wizard on a selection).

**Expect:**
- `needs_vault_migration` is cleared.
- The stored object is now ciphertext.
- The file still reads back as the original text.
- The `checksum` is unchanged from before the migration.

6. If the file has versions, check each version's snapshot the same way.

**Expect:** every snapshot is ciphertext. A snapshot written before the file
entered the vault is plaintext too, and the migration must have re-written it.

## 8. An infected file never reaches storage

This requires `dms_clamav` with a reachable clamd.

1. Upload the EICAR test string as `eicar.txt` into the vault directory.

**Expect:** the upload is rejected. No `dms.file` row and no `ir.attachment`
row exists for it — the scan runs before the attachment is created, so the
bytes never reach the vault.

## 9. The dump test

This is the whole point of the module.

1. Take a database dump and a copy of the storage, **without** `odoo.conf`:

```bash
pg_dump -d <db> > /tmp/dump.sql
tar czf /tmp/store.tgz <the storage directory>
```

2. On another machine, restore the dump and the storage, and try to read
   `hemligt.txt` from the restored filestore.

**Expect:** the object is ciphertext and the content key in the dump is
wrapped under a master key you do not have. There is no path from the dump to
the plaintext.

3. Now copy `odoo.conf` over as well and repeat.

**Expect:** it is readable. That is the threat model — the vault separates the
dump from the key, and an attacker who has both has everything.

## Cleanup

Delete the test files, revoke the test members, and remove the test directory.
Do not leave a vault directory with a master key in a test `odoo.conf` on a
shared machine.
