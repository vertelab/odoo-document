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
const OFFICE_EXTENSIONS = ["docx", "docxf", "xlsx", "pptx", "odt", "ods", "odp"];

/**
 * Which backend serves the office formats, in order of preference.
 *
 * WHY A LIST AND NOT A SINGLE ENTRY
 * =================================
 * This table used to name `can_open_in_euro_office` directly for every office
 * extension. That is backend-agnostic in SHAPE but not in fact — replacing
 * Euro-Office with Collabora required editing this file, which is the same
 * defect the table was written to remove (a vendor hardcoded on the client).
 *
 * Now the extensions say "office", and the backend is whichever of these is
 * installed. Each entry names a capability field and an action method that
 * the owning module declares; an absent field means that module is not
 * installed, so the next one is tried.
 *
 * Adding a third backend is one line here, and it does not make this module
 * depend on any of them.
 */
const OFFICE_BACKENDS = [
    {field: "can_open_in_collabora", method: "open_in_collabora_action"},
    {field: "can_open_in_euro_office", method: "open_in_euro_office_action"},
];

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

        const extension = extensionOf(this.props.record.data.name);
        const capabilities = this._capabilityFor(extension);
        if (!capabilities.length) {
            return super.onGlobalClick(ev);
        }

        // The click is claimed BEFORE the await: `super` must not also run
        // while the capability read is in flight, or the preview would open
        // underneath the editor.
        ev.preventDefault();
        ev.stopPropagation();

        const capability = await this._resolveCapability(capabilities);
        if (!capability) {
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
     * Return the capabilities to try for `extension`, in preference order.
     *
     * `excalidraw` has exactly one editor; the office formats are resolved
     * from whichever backend module is installed (OFFICE_BACKENDS).
     */
    _capabilityFor(extension) {
        if (extension === "excalidraw") {
            return [
                {
                    field: "can_open_in_excalidraw",
                    method: "open_in_excalidraw_action",
                },
            ];
        }
        if (!OFFICE_EXTENSIONS.includes(extension)) {
            return [];
        }
        return OFFICE_BACKENDS;
    },

    /**
     * Return the first capability whose field the record reports as openable.
     *
     * The field is read on demand rather than added to the kanban view's
     * field list: the kanban is shared with every other DMS view, and a
     * capability field that only this module needs should not be fetched for
     * every record in every list.
     *
     * For office formats this is also how the installed backend is detected:
     * a module that is not installed contributes no field, so its read
     * returns undefined and the next backend is tried.
     */
    async _resolveCapability(capabilities) {
        if (!capabilities.length) {
            return undefined;
        }
        const fields = await this.env.services.orm.read(
            "dms.file",
            [this.props.record.data.id],
            capabilities.map((capability) => capability.field)
        );
        const record = fields && fields[0];
        if (!record) {
            return undefined;
        }
        return capabilities.find((capability) => Boolean(record[capability.field]));
    },
});
