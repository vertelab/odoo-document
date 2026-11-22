# DMS Antivirus (ClamAV)

Scans every write to `dms.file.content` with ClamAV before the bytes are
stored. An infected file is rejected and never reaches the storage backend.

## Where the hook sits

`dms_clamav` inherits `dms.file.write()` and `dms.file.create()` and scans
**before** `super()`. That placement is the whole design:

```
write(vals)                 ← dms_clamav scans here
  └── super().write()       ← dms_version snapshots the old content here
        └── _inverse_content()  ← the bytes are persisted here
```

Scanning before `super()` means the content is still in memory (no read-back
from storage), and it means an infected file becomes **neither a file nor a
version** — a version is a stored copy, and the point of scanning first is
that the infected bytes never enter the system at all.

`create()` is scanned too. A new file is a write path like any other, and
every protocol (form, WebDAV, SFTP, JSON API, PWA capture) ends up in the
same two methods.

## Fail-open — a documented choice

If `clamd` is missing, unreachable or times out, the file is **stored** and a
warning is logged. This is deliberate:

- A ClamAV restart would otherwise take the whole DMS down — every upload,
  from every protocol, failing at once.
- The alternative, fail-closed, protects against a threat that is already
  covered by the storage layer (files are not executed) at the cost of an
  availability failure that is certain to happen.

The trade-off is written down here so it is a decision, not an accident. An
environment that wants fail-closed has to change the code, not a setting.

Every rejection is logged at `error` level with the user login, the uid, the
file name and the ClamAV signature, so a rejection can be traced to a person
and a file after the fact.

## Requirements

| Requirement | Detail |
|---|---|
| `clamd` daemon | Listening on a TCP socket (default `localhost:3310`) |
| `clamd` Python package | `pip install clamd` — imported lazily, so the module installs without it |
| `clamav-freshclam` | Keeps the signature database current; without it the scan runs against stale signatures |

The module declares `external_dependencies: {"python": ["clamd"]}`, so Odoo
refuses to install it where the package is absent. The lazy import inside
`_clamav_scan()` is what keeps a *running* installation working if the
package later disappears — it warns and fails open rather than crashing.

## Settings

**Documents → Configuration → Settings → Antivirus**

| Setting | Config parameter | Default |
|---|---|---|
| Scan Uploads | `dms_clamav.enabled` | `True` |
| clamd Host | `dms_clamav.host` | `localhost` |
| clamd Port | `dms_clamav.port` | `3310` |

Turning *Scan Uploads* off skips the scan entirely — useful when debugging a
suspected false positive, and the reason the flag exists rather than a code
change.

## Interaction with `dms_vault`

A file already in a vault directory is **ciphertext**, and ClamAV cannot read
ciphertext. Re-scanning a vaulted file is not possible without decrypting it
first, which would mean running the scan with the master key in hand. That is
not built.

The protection that remains is the one that matters: the scan happens on write,
before `dms_vault`'s encryption runs, so a file is scanned in plaintext exactly
once — on the way in.

## Tests

`tests/test_dms_clamav.py` — eight tests, all `post_install`:

| Test | What it pins |
|---|---|
| `test_clean_file_is_stored` | A clean file passes |
| `test_infected_file_is_rejected` | An infected file raises and does not exist afterwards |
| `test_infected_overwrite_is_rejected` | A rejected overwrite leaves the original bytes untouched |
| `test_infected_file_creates_no_version` | A rejected write creates no `dms.file.version` (skipped when `dms_version` is absent) |
| `test_fail_open_when_clamd_unavailable` | Nothing listening on the port → file stored |
| `test_disabled_skips_scan` | The setting actually skips the scan |

Run them:

```bash
sudo checkmodule -d <db> -m dms_clamav -t -l test
```

`post_install` tests only run when the module is **updated**, not when it is
installed — bump `version` in the manifest to force the update.
