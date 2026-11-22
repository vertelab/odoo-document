Photograph a document straight into a DMS directory.

The DMS is desktop-only in practice: a field technician who photographs
damage, a salesperson who photographs a quote attachment, or a manager
approving receipts on a phone has no way in. They have to get back to a
computer.

This module registers a PWA app with `web_pwa_push` and implements the
callback that receives the files. `web_pwa_push` provides the camera page
and the upload endpoint; it never learns what a document is. This module
knows, and decides where the file lands.

* A directory can be marked as a mobile target
* `/dms/mobile` lists those directories with a camera button each
* Uploads are created as `dms.file` with `capture_source='pwa'`
