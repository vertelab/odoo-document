# dms_vault

Encrypts DMS documents at rest, at the single point where bytes leave Odoo:
`ir.attachment._file_write`.

## Why that point

`_file_write` is the only place the raw bytes are handed to a storage backend.
Overriding it covers every consumer without any of them knowing:

- `dms.file.content_file` (the `attachment=True` field)
- `dms_version`'s snapshots — they create their own `ir.attachment` with
  `res_model='dms.file'` + `res_id`, so the same lookup finds them
- anything else that stores a file through `ir.attachment`

Encrypting at `dms.file` instead would have left `dms_version` writing
**plaintext** copies into `ir.attachment` — the exact leak the vault exists to
prevent.

## The checksum describes the plaintext, deliberately

`_get_datas_related_values` computes `checksum = sha1(bin_data)` before
`_file_write`, so `ir.attachment.checksum` is the hash of the plaintext even
though the stored object is ciphertext. Two consequences, both intended:

1. `ir.attachment.checksum` will not match the hash of the object in the
   bucket. It identifies the document, not its storage encoding.
2. `_get_fs_path()` uses the checksum as the object key, so identical files
   share one object even across vaults. That is deduplication, and it is safe:
   the object is ciphertext under a key the sharing party may not hold.

The read side must therefore decrypt before anything compares bytes to the
checksum — which is what `_storage_file_read` does.

## ⚠️ Coordination with the `fs-storage-20` change

`dms_vault` overrides **`_file_write(self, bin_data, checksum)`** — the 19.0
signature. The `fs-storage-20` change (in the planning repo) rewrites
`fs_attachment` for 20.0's contract:

```
19.0:  _file_write(self, bin_data, checksum)   → fname (str)
20.0:  _file_write(self, fname, bin_value)     → None
```

**This module's signature must follow `fs_attachment`'s**, because
`super()._file_write(...)` is the call it wraps. The two changes must land in
the same order:

1. `fs-storage-20` establishes the 20.0 contract in `fs_attachment`.
2. `dms_vault` adds the matching `# #if VERSION >= "20.0"` branch here, reading
   from the seekable `bin_value` and writing back through the same object.

**Owner of the override:** `dms_vault` (this module). `fs-storage-20` owns the
contract; this module owns the encryption that sits on top of it. Neither may
change the other's method without the other.

Until both are done, `dms_vault` is `installable: True` on 18.0 and 19.0 only —
its `depends` on `fs_attachment` is satisfied there. On 20.0 the dependency
itself is `installable: False` upstream (OCA/storage), so the question does not
arise yet.

## Editions

Version-agnostic source (`.p.py`) expanded for 18.0, 19.0 and 20.0. The
`ir.model.access.csv` → `ir.access.csv` move is expressed in the manifest.
