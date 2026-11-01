## How versions are created

A version is written **before** the new content replaces the old one, so the
version always holds the content that is about to be lost.

The hook is on `write()`, not on `_inverse_content()`. By the time the inverse
runs, Odoo has already assigned the new value to the record, so reading the old
content there returns the new bytes and the version would keep a copy of
itself. `write()` is the only point where `_origin.content` still holds the
previous value.

`create()` is deliberately not covered: a new file has no previous content, so
there is nothing to keep.

## Content source

The `content_source` field records which path wrote the file:

| Source | Set by |
| --- | --- |
| `form` | default, when no context key is present |
| `webdav` | `dms_webdav` sets `dms_source="webdav"` in the context |
| `sftp` | `dms_sftp` sets `dms_source="sftp"` |
| `api` | external callers set `dms_source="api"` |
| `restore` | `action_restore()` sets it on the write it performs |

A module that writes file content should pass the context key:

```python
file_record.with_context(dms_source="webdav").write({"content": payload})
```

## Retention

Retention is configured per directory, on `dms.directory`:

* `version_retention_count` — keep the N newest versions (default 10, `0` = unlimited)
* `version_retention_days` — drop versions older than N days (default `0` = unlimited)

The two combine: a version is kept only if it satisfies **both** limits. The
newest version is always kept, whatever the policy says, so a file can never
end up with no version at all.

The pruning cron runs daily and logs how many versions it removed.

## Restoring a version

Open a file, click **Versions**, and press **Restore** on the version you want.
The current content is written as a new version first, so a restore is itself
reversible — you can restore the version a restore replaced.

Restoring requires write access to the file; the button checks it with
`check_access("write")` and raises `AccessError` otherwise.
