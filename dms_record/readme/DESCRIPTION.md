Shared primitive for the `dms_*` bridge modules: one DMS directory per record.

A bridge module inherits `dms.record.mixin`, declares which storage it uses and
which access mode it wants, and ships the storage as data. The mixin then
creates the per-record directory when the record is created and keeps it
reachable as `dms_directory_id`.

Why the directory is the whole point: `dms.file.res_model` and
`dms.file.res_id` are `related` fields reading from `directory_id`. A file
therefore inherits its link to the business record from its directory, and
every write path — WebDAV, SFTP, the API — only has to set `directory_id`.
Get the directory right and all of them are right.

The identity of the link is `res_model`/`res_id`, never the directory name. A
name lookup orphans the directory on rename, collides for two records with the
same name, and raises `Expected singleton` when it matches more than one.
