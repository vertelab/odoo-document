// /** ********************************************************************************
//     Copyright 2026 Vertel Sverige AB (https://vertel.se).
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/

/**
 * The Files view's "New" button opens the "New document" wizard.
 *
 * WHY REPLACE THE DEFAULT
 * =======================
 * Odoo's `KanbanView.Buttons` renders "New" as `onCreate` — a blank
 * `dms.file` form. That form asks for a file to upload, which is not what
 * "new document" means: the user wants a document, not to attach one. The
 * wizard creates a real `.docx`/`.xlsx`/`.pptx`/`.excalidraw` from a blank
 * or a template, and collects the category, tags and access in the same
 * step.
 *
 * Upload is still available: DMS's own "Upload" button sits next to it and
 * is untouched.
 *
 * WHY A VIEW PATCH
 * ================
 * DMS's Files view has `js_class="file_kanban"` and its own
 * `buttonTemplate`. A `<header>` in the XML view is rejected by Odoo's
 * schema, and a server action with `binding_model_id` is never shown because
 * the view does not render the standard Action menu.
 */

import {FileKanbanView} from "@dms/js/views/file_kanban_view.esm";
import {patch} from "@web/core/utils/patch";

patch(FileKanbanView, {
    // The template adds our "New document" button next to Scan/Upload and
    // keeps Odoo's own "New" — see static/src/xml/kanban_buttons.xml.
    buttonTemplate: "dms_excalidraw.KanbanButtons",
});

patch(FileKanbanView.Controller.prototype, {
    /**
     * @override
     *
     * "New" now opens the wizard instead of the blank file form.
     *
     * The button in `web.KanbanView` is
     *   `t-on-click="() => this.createRecord()"`
     * — NOT `onCreate`. Patching `onCreate` (the obvious guess) does nothing;
     * the click goes straight to `/new`. Verified 2026-11-04 by watching the
     * network: the request was `dms.file/onchange`, i.e. the plain form.
     *
     * The directory comes from the domain, the same place DMS's own
     * `uploadDocument` reads it (`["directory_id", "=", id]` or `child_of`).
     * Without one the wizard shows a directory picker rather than refusing.
     */
    async createRecord() {
        const directoryId = this._currentDirectoryId();

        await this.env.services.action.doAction(
            "dms_excalidraw.action_new_document",
            {
                additionalContext: directoryId
                    ? { active_directory_id: directoryId }
                    : {},
            }
        );
    },

    /**
     * Return the directory id from the current domain, or false.
     *
     * Mirrors DMS's own `onChangeFileInput` so a change in how DMS encodes
     * the active folder only has to be made in one place upstream.
     */
    _currentDirectoryId() {
        const domain = this.props?.domain || this.env.searchModel?.domain || [];
        for (const item of domain) {
            if (
                Array.isArray(item) &&
                item.length === 3 &&
                item[0] === "directory_id" &&
                ["=", "child_of"].includes(item[1])
            ) {
                return item[2];
            }
        }
        return false;
    },
});
