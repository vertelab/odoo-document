// /** ********************************************************************************
//     Copyright 2026 Vertel Sverige AB (https://vertel.se).
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/

/**
 * Clicking a file's icon in the kanban view opens the right editor.
 *
 * WHY PATCH AND NOT A SUBCLASS
 * ============================
 * `js_class="file_kanban"` points at a VIEW, and DMS builds that view from
 * `FileKanbanRenderer`, which sets `KanbanRecord: FileKanbanRecord` as a
 * STATIC property. Registering a new record class in the registry does
 * nothing — the renderer never looks it up.
 *
 * So the record is patched in place. That is also what DMS itself does to
 * `FileKanbanRenderer.prototype` for the drop zone (see
 * `file_kanban_view.esm.js`), so this follows the module's own convention.
 *
 * WHY THIS IS NEEDED AT ALL
 * =========================
 * DMS opens its built-in preview when the icon is clicked. That preview
 * handles images, PDF, video and audio — and nothing else. For a
 * `.excalidraw` it shows a JSON dump; for `.docx` it shows nothing useful;
 * for `.md` it shows raw source.
 *
 * The icon is the obvious thing to click, so it should do the obvious thing:
 * open the editor that owns the format. Everything not in OPEN_ROUTES falls
 * through to `super`, so images, PDFs and video keep their behaviour.
 */

import {FileKanbanRecord} from "@dms/js/views/file_kanban_record.esm";
import {patch} from "@web/core/utils/patch";
import {registry} from "@web/core/registry";

/**
 * Formats this module knows how to open, and where to send them.
 *
 * `from` carries the directory the user is browsing, so the target page's
 * back button returns there instead of to the file's record form. It is a
 * hint, not a permission: the server validates it against the file's own
 * directory before using it.
 */
const OPEN_ROUTES = {
    excalidraw: (id, from) => `/dms_excalidraw/whiteboard/${id}${from}`,
    md: (id, from) => `/dms_excalidraw/markdown/${id}${from}`,
    markdown: (id, from) => `/dms_excalidraw/markdown/${id}${from}`,
    docx: (id, from) => `/dms_euro_office/open/${id}${from}`,
    docxf: (id, from) => `/dms_euro_office/open/${id}${from}`,
    xlsx: (id, from) => `/dms_euro_office/open/${id}${from}`,
    pptx: (id, from) => `/dms_euro_office/open/${id}${from}`,
    odt: (id, from) => `/dms_euro_office/open/${id}${from}`,
    ods: (id, from) => `/dms_euro_office/open/${id}${from}`,
    odp: (id, from) => `/dms_euro_office/open/${id}${from}`,
};

patch(FileKanbanRecord.prototype, {
    /**
     * @override
     *
     * Route a click on the icon to the format's own editor. Anything not in
     * OPEN_ROUTES is left to DMS's preview.
     */
    onGlobalClick(ev) {
        if (ev.target.closest(".o_kanban_dms_file_preview")) {
            const name = this.props.record.data.name || "";
            const extension = name.includes(".")
                ? name.split(".").pop().toLowerCase()
                : "";
            const route = OPEN_ROUTES[extension];

            if (route) {
                ev.preventDefault();
                ev.stopPropagation();
                const directoryId = this.props.record.data.directory_id;
                const from = directoryId ? `?from=${directoryId}` : "";
                window.open(
                    route(this.props.record.data.id, from),
                    "_blank",
                    "noopener"
                );
                return;
            }
        }
        return super.onGlobalClick(ev);
    },
});
