# odoo-document — gren 19.0

> **Denna gren är avsiktligt tom.** Modulerna är INTE portade till Odoo 19.
> Grenen finns så att dev-miljöer (`hansolo19`) kan klona den utan att falla,
> men den påstår ingenting om att koden är portad.

## Baseline

| | |
|---|---|
| Källa | `20.0` |
| Moduler | **29** |
| Grenar i repot | `14.0`, `18.0`, `20.0`, `IMPROVED-SFTP-FLOW`, `cherry-18.0`, `dms_glue`, `feat/dms-excalidraw`, `feat/dms-versioning`, `main`, `odoo-document-sftp-sync`, `sftp_sales_team_dev`, `wip/dms-webdav-preview-chunked-put` |

## Moduler

- `dms_account_analytic_account`
- `dms_account_move`
- `dms_ai`
- `dms_calendar_event`
- `dms_crm_lead`
- `dms_crm_team`
- `dms_duplicate_filenames`
- `dms_event`
- `dms_fleet_vehicle`
- `dms_helpdesk_team`
- `dms_helpdesk_ticket`
- `dms_hierarchy`
- `dms_hr_employee`
- `dms_hr_expense`
- `dms_hr_job_recruitment`
- `dms_partner`
- `dms_product_template`
- `dms_project`
- `dms_property_mgmt`
- `dms_purchase`
- `dms_repair_order`
- `dms_sale_order`
- `dms_sftp`
- `dms_sync_rclone`
- `dms_webdav`
- `dms_webpage`
- `document_onboarding`
- `document_sftp`
- `document_version`

## Blockerare

**4 externa beroenden saknas** i Odoo 19-kärnan och OCA 19.0:

| Beroende | Behövs av |
|---|---|
| `dms_storage` | `dms_webpage` |
| `fs_storage` | `dms_webpage` |
| `fs_storage_s3` | `dms_sync_rclone` |
| `storage_backend` | `dms_webpage` |

### Prioritering

Ett beroende som blockerar många moduler ger mest nytta att lösa först:

- `dms_storage` — frisläpper **1** modul(er)
- `fs_storage` — frisläpper **1** modul(er)
- `fs_storage_s3` — frisläpper **1** modul(er)
- `storage_backend` — frisläpper **1** modul(er)

## Nästa steg

Portering sker på `*-pfile`-maskin med versionsagnostisk kod
(`.p.py` / `.p.xml`). Se `/skill:odoo-pfiles`.
