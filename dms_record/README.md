# dms_record

Shared primitive for the `dms_*` bridge modules: **one DMS directory per
record**.

A bridge module inherits `dms.record.mixin`, declares which storage it uses and
which access mode it wants, and ships the storage as data. The mixin then
creates the per-record directory when the record is created and keeps it
reachable as `dms_directory_id`.

## The contract

| What | How |
|---|---|
| **One directory per record** | created on `create()`, adopted by `res_model`/`res_id` if it already exists — never duplicated |
| **The link is `res_model`/`res_id`** | never the directory name; `dms.file.res_model`/`res_id` are `related` fields reading from `directory_id`, so a file inherits its link to the business record from its directory |
| **`doc_count`** | files under the record's directory, `child_of` — one meaning instead of eighteen |
| **`action_open_dms_files`** | one shared action for every bridge, domain on `res_model`/`res_id`, so a file in a subdirectory is still found |
| **Access mode** | `inherit` / `team` / `owner`, validated against the storage's `save_type` at directory creation |

The mixin is **never** `auto_install`. It reaches a database only as a declared
dependency of a bridge.

## Why the directory is the whole point

`dms.file.res_model` and `dms.file.res_id` are `related` fields reading from
`directory_id`. Every write path — WebDAV, SFTP, the API — only has to set
`directory_id`. Get the directory right and all of them are right.

A name lookup instead of `res_model`/`res_id` orphans the directory on rename,
collides for two records with the same name, and raises `Expected singleton`
when it matches more than one.

## The three access modes

| Mode | Storage must be | Access comes from |
|---|---|---|
| `inherit` | `save_type='attachment'` **and** `inherit_access_from_parent_record=True` | the record's own `ir.rule` |
| `team` | any | a `dms.access.group` from `_dms_access_group()` |
| `owner` | **not** `attachment` | an access group scoped to `_dms_owner_field()` |

## Editions

Version-agnostic source (`.p.py`) expanded for 18.0, 19.0 and 20.0. No edition
condition is currently needed — expansion is byte-identical for all three.

See `readme/USAGE.md` for how to declare a bridge, and
`tests/bridge_case.py` for the contract every bridge is tested against.
