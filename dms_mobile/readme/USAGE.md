## Marking a directory

Open a DMS directory and tick **Mobile target** under the *Mobile* group.
Only directories marked this way appear on the phone page, and only for
users who may create files in them.

The flag is deliberately per-directory rather than per-storage: a phone user
uploads to a handful of places, not to the whole tree.

## On the phone

1. Install the app from `/pwa/install` (or open `/dms/mobile` directly).
2. Pick a directory.
3. Tap **Ta foto / välj fil**. The camera opens.
4. The photo uploads immediately and the page confirms.

The upload goes to `/pwa/upload?app=dms-capture`, which calls
`dms.file.pwa_capture_store(files, directory_id=...)`. That method runs as
the uploading user — the controller does not sudo — so the directory's own
access rules decide whether the write is allowed.

## What ends up in the DMS

A `dms.file` per photo, named after the file the phone produced, with
`capture_source = pwa`. Everything downstream (versioning, WebDAV, search)
treats it like any other document.

## Adding another capture app

A module can register its own `web.pwa.app` row with `capture_enabled`,
`capture_model` and `capture_method`. `web_pwa_push` calls
`model.<capture_method>(files, **kwargs)` and expects a JSON-safe dict back.
It never needs to know what the model does with the files.
