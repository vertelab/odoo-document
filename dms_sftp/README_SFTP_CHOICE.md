# SFTP: one server, not two

`document_sftp` and `dms_sftp` both start an SFTP server from Odoo and both
were configured for port 2222 on the `dms` instance:

| Module | `bind` | Result |
|---|---|---|
| `dms_sftp` | `0.0.0.0:2222` | binds first, owns the port |
| `document_sftp` | `localhost:2222` | `OSError: [Errno 98] Address already in use` on every start |

`document_sftp` lost the race on every Odoo restart, logged a traceback and
served nothing. It was installed but dead weight - and the traceback in the
journal made every restart look broken.

## The choice

Keep **`dms_sftp`**:

* It is DMS-aware - it authenticates against `dms.file`/`dms.directory` and
  honours DMS permissions.
* It is the one actually serving on `dms` today.
* `document_sftp` is generic (`document.sftp.root` can point at any model),
  which sounds flexible but means it knows nothing about DMS access rules.

## Action

`document_sftp` is uninstalled on `dms`. Do not install both again: they
compete for the same port and the loser fails silently apart from a
traceback.

If the generic behaviour is needed later, give the two modules **different
ports** (`document_sftp.bind = localhost:2223`) before installing the second
one.
