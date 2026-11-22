# odoo-document — gren 19.0

Dokument-/DMS-modulerna för Odoo 19.

Modulerna är porterade från 20.0 som versionsagnostisk källkod (`.p.py` /
`.p.xml`). Samma p-filer finns på alla utgåvegrenar; utgåveskillnader uttrycks
med `# #if VERSION` inuti filen.

**Porterad är inte samma sak som installerbar.** Varje modul i det här repot
beror på `dms` (OCA), och `dms` har ingen 19.0-gren med innehåll. Tabellen
nedan säger vilken blockerare som gäller per modul.

## Porteringsstatus — Odoo 19.0

Den här grenen är Odoo 19.0. Tabellen beskriver bara 19.0.

Genererad av `scripts/porting-status.py` — handredigera inte.

| Modul | Beskrivning | Porteringsstatus |
|---|---|---|
| `dms_account_asset` | A document directory for every fixed asset. | blocked by dms (OCA) |
| `dms_account_move` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_ai` | OKF-indexering av dms.file och dms.directory + förlage-markering | blocked by dms (OCA) |
| `dms_calendar_event` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_clamav` | Scan every DMS file write with ClamAV before it is stored | blocked by dms (OCA) |
| `dms_collabora` | Open DMS office documents in Collabora Online | blocked by disabled: no reason in manifest |
| `dms_contract` | A document directory for every contract. | blocked by dms (OCA) |
| `dms_crm_lead` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_crm_team` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_document_markdown` | Read .md files from DMS as documents, not as source | blocked by dms (OCA) |
| `dms_document_office` | Create Word, Excel and PowerPoint documents from DMS | blocked by dms (OCA) |
| `dms_event` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_excalidraw` | Open DMS whiteboards in an Excalidraw service | blocked by dms (OCA) |
| `dms_extract` | Extract text from dms.file content into the OKF body | ok |
| `dms_fleet_vehicle` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_helpdesk_team` | Short summary of the modules purpose.s purpose. | blocked by helpdesk_mgmt (OCA); dms (OCA) |
| `dms_helpdesk_ticket` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA); helpdesk_mgmt (OCA) |
| `dms_hr_employee` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_hr_expense` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_hr_job_recruitment` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_mobile` | Photograph a document straight into a DMS directory | blocked by disabled: no reason in manifest |
| `dms_oca_fixes` | Three OCA/dms fixes as overrides instead of source patches | blocked by disabled: no reason in manifest |
| `dms_partner` | DMS Partner =========== DMS Partner. Features: - UI Integration: Extends 1 … | blocked by dms (OCA) |
| `dms_product_template` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_project` | Creates the Link between Project/Task and DMS | blocked by dms (OCA) |
| `dms_property_mgmt` | DMS Property. | blocked by property_mgmt (Vertel); dms (OCA) |
| `dms_purchase` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_record` | Shared primitive: one DMS directory per record. | blocked by dms (OCA) |
| `dms_repair_order` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_sale_order` | Short (1 phrase/line) summary of the modules purpose, used as subtitle on … | blocked by dms (OCA) |
| `dms_sftp` | Access OCA DMS documents via SFTP | blocked by dms (OCA) |
| `dms_slide` | A document directory for every course and every lesson. | blocked by dms (OCA) |
| `dms_sync_rclone` | Syncs documents with an rclone remote. | blocked by fs_storage_s3 (OCA); dms (OCA) |
| `dms_trash` | Soft delete with a per-directory retention delay | blocked by dms (OCA) |
| `dms_vault` | Encrypt the bytes of a DMS directory before they reach storage | blocked by dms (OCA) |
| `dms_version` | Keep a version history of every DMS file write | blocked by dms (OCA) |
| `dms_webdav` | Access OCA DMS documents via WebDAV | blocked by dms (OCA) |
| `document_sftp` | Access your documents via SFTP. | ok |
| `office_download_collabora` | Download links for the Collabora Office desktop suite | blocked by dms (OCA) |
| `office_download_euro_office` | Download links for the Euro-Office desktop suite | blocked by dms (OCA) |
