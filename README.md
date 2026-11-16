# odoo-document

## Porteringsstatus

18.0 är baseline. 19.0/20.0 visar om p-filen har ett villkor för utgåvan
— inte om grenen finns. Blockerare är `depends` som saknas i 20.0
(kärna + alla 20.0-grenar).

| Modul | Beskrivning | Manifest | p-fil | 19.0 | 20.0 | Blockerare |
|---|---|---|---|---|---|---|
| dms_account_analytic_account | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_account_move | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_ai | OKF-indexering av dms.file och dms.directory + förlage-ma... | 1.1.0 | 1 | — | — | `dms` |
| dms_calendar_event | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_crm_lead | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_crm_team | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_duplicate_filenames | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_event | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_fleet_vehicle | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_helpdesk_team | Short summary of the modules purpose.s purpose. | 1.0.0 | 0 | — | — | `helpdesk_mgmt` `dms` |
| dms_helpdesk_ticket | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` `helpdesk_mgmt` |
| dms_hierarchy | DMS Hierarchy. | 1.0.0 | 0 | — | — | `dms` |
| dms_hr_employee | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_hr_expense | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_hr_job_recruitment | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_partner | DMS Partner. | 1.1.0 | 0 | — | — | `dms` |
| dms_product_template | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_project | DMS Project. | 1.0.0 | 0 | — | — | `dms` |
| dms_property_mgmt | DMS Property. | 1.0.0 | 0 | — | — | `property_mgmt` `dms` |
| dms_purchase | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_repair_order | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_sale_order | Short (1 phrase/line) summary of the modules purpose, use... | 1.0.0 | 0 | — | — | `dms` |
| dms_sftp | Access OCA DMS documents via SFTP | 1.0.0 | 0 | — | — | `dms` |
| dms_sync_rclone | Syncs documents with an rclone remote. | 1.0.0 | 0 | — | — | `fs_storage_s3` `dms` |
| dms_webdav | Access OCA DMS documents via WebDAV | 1.0.0 | 0 | — | — | `dms` |
| dms_webpage | DMS WebPage. | 1.1 | 9 | — | — | `dms` `dms_storage` |
| document_onboarding | Onboardingskurs: dokument, DMS och WebDAV | 1.0.0 | 0 | — | — | — |
| document_sftp | Access your documents via SFTP. | 1.2 | 0 | — | — | — |
| document_version | Manage version management on documents. | 1.1.0 | 0 | — | — | `dms` |
