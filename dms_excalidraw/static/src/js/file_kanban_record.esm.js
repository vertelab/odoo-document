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
 * open the editor that owns the format. Everything this module does not claim
 * falls through to `super`, so images, PDFs and video keep their behaviour.
 *
 * WHY A CAPABILITY TABLE AND NOT A ROUTE TABLE
 * ============================================
 * This file used to hold a table of URLs, including
 * `/dms_euro_office/open/<id>` for the office formats. That URL was a guess:
 * the module that owns the office editor decides where its editor lives, and
 * when it moves, a URL written here is simply wrong — which is exactly what
 * happened (a click on a created `.docx` opened a dead route).
 *
 * A capability field is declared by the owning module on `dms.file`
 * (`can_open_in_euro_office`, `can_open_in_excalidraw`, …). Reading it and
 * asking the record for its action means the route lives in one place — the
 * module that serves it — and this file cannot drift.
 */

import {FileKanbanRecord} from "@dms/js/views/file_kanban_record.esm";
import {patch} from "@web/core/utils/patch";

/**
 * Format → `{field, method}` on `dms.file`.
 *
 * `field` is the computed boolean the owning module declares; when the module
 * is not installed the field does not exist and the format is not offered.
 * `method` returns the action that opens the file (an `ir.actions.act_url`
 * for both current owners).
 *
 * Only formats whose editor is a separate page belong here. Images, PDFs,
 * video and audio are DMS's own preview and must keep falling through.
 */
const EDITOR_CAPABILITIES = {
    excalidraw: {
        field: "can_open_in_excalidraw",
        method: "open_in_excalidraw_action",
    },
    docx: {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
    docxf: {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
    xlsx: {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
    pptx: {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
    odt: {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
    ods: {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
    odp: {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
};

/**
 * Return the extension of a file name, lower-case, without the dot.
 */
function extensionOf(name) {
    const value = name || "";
    return value.includes(".") ? value.split(".").pop().toLowerCase() : "";
}

patch(FileKanbanRecord.prototype, {
    /**
     * @override
     *
     * Route a click on the icon to the format's own editor. Anything this
     * module does not claim — including a format whose editor module is not
     * installed — is left to DMS's preview.
     */
    async onGlobalClick(ev) {
        if (!ev.target.closest(".o_kanban_dms_file_preview")) {
            return super.onGlobalClick(ev);
        }

        const capability = EDITOR_CAPABILITIES[extensionOf(this.props.record.data.name)];
        if (!capability) {
            return super.onGlobalClick(ev);
        }

        // The click is claimed BEFORE the await: `super` must not also run
        // while the capability read is in flight, or the preview would open
        // underneath the editor.
        ev.preventDefault();
        ev.stopPropagation();

        const canOpen = await this._canOpenWith(capability);
        if (!canOpen) {
            // The editor module is not installed (the field does not exist)
            // or the format is not editable. Fall back to the preview rather
            // than sending the user to a route nobody serves.
            return super.onGlobalClick(ev);
        }

        const action = await this.env.services.orm.call(
            "dms.file",
            capability.method,
            [[this.props.record.data.id]]
        );
        if (!action) {
            return super.onGlobalClick(ev);
        }
        return this.env.services.action.doAction(action);
    },

    /**
     * Return whether the record can be opened by the capability's editor.
     *
     * The field is read on demand rather than added to the kanban view's
     * field list: the kanban is shared with every other DMS view, and a
     * capability field that only this module needs should not be fetched for
     * every record in every list. One read per click is cheaper than one
     * field per card.
     */
    async _canOpenWith(capability) {
        const fields = await this.env.services.orm.read(
            "dms.file",
            [this.props.record.data.id],
            [capability.field]
        );
        return Boolean(fields && fields[0] && fields[0][capability.field]);
    },
});
