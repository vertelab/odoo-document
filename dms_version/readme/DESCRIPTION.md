Keep a version history of every DMS file write.

`dms.file.content` is a non-stored binary field: every write goes through
`_inverse_content` and overwrites the previous blob in place. This module
keeps the previous content as a `dms.file.version` record before each
overwrite, so a file can be restored.

* One version per overwrite, whatever the source (form, WebDAV, SFTP, API, PWA)
* Retention policy per directory (count and/or age)
* Restore a previous version (which itself creates a new version)
* Existing files get an initial version on install (idempotent post-init hook)
