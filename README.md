# odoo-document

Vertel's document management modules for Odoo 18. Built on the OCA `dms`
module, extended with per-record document directories, WebDAV access,
versioning and AI features.

## The bridge pattern

A "bridge" gives one Odoo model a document directory of its own: every
project, sale order or employee gets a folder, and files uploaded into it
inherit that record's access rights.

The construction is always the same:

```
dms.storage          one per model, declared in data/*.xml
  └── dms.directory  root directory (is_root_directory=True)
        └── dms.directory   one per record, linked by res_model + res_id
              └── dms.file
```

`dms.file.res_model` and `res_id` are `related` from `directory_id`, so a file
never needs to know which project it belongs to — the directory does. That is
what makes WebDAV, SFTP, rclone and the JSON API work without per-domain code:
they all just set `directory_id`.

## `dms_record` — the shared mixin

`dms.record.mixin` is an abstract model that owns the directory lifecycle, so
a bridge only declares three things:

```python
class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_sale_order.sale_order_dms_storage"
    _dms_access_mode = "inherit"
```

The mixin creates the directory on `create()`, keeps its name in sync on
`write()`, counts the files in `doc_count`, and opens them through
`action_open_dms_files()`.

### The three access modes

There is no default: a bridge that does not choose fails its own test rather
than silently getting `inherit`.

| Mode | Storage | Who can read the documents |
|---|---|---|
| `inherit` | `save_type='attachment'` + `inherit_access_from_parent_record=True` | Whoever can read the record, via its own `ir.rule` |
| `team` | any | The `dms.access.group` returned by `_dms_access_group()` |
| `owner` | **not** `attachment` | The user returned by `_dms_owner_field()` |

The mixin validates the pairing and raises `UserError` on a mismatch.

**`inherit` requires `save_type='attachment'`.** `dms.security.mixin`'s
`_get_domain_by_inheritance()` hardcodes both `storage_id_save_type =
'attachment'` and `storage_id_inherit_access_from_parent_record = True`. A
filestore or database storage never inherits, whatever the flag says.

**`owner` requires the opposite.** An owner-scoped access group is what grants
access; attachment storage would bypass it by inheriting the record's rights
instead.

### Where the bytes live is a separate question

`save_type` picks the storage backend; the access mode picks the ACL path.
They are orthogonal:

- `attachment` and `file` both go to external storage (`ir.attachment` →
  `fs_attachment` → S3), so `inherit` gets ACL inheritance **and** S3.
- `database` writes `content_binary` (bytea) and never touches `fs_attachment`.

Storage selection is per **model + field**, not per DMS storage, so moving
`dms.file` to S3 is all-or-nothing. It is a deployment decision; no bridge
declares it.

### `privacy_visibility` — read this before choosing `inherit`

`project.project` defaults to `privacy_visibility='portal'`, and its rule for
internal users is:

```python
['|', ('privacy_visibility', '!=', 'followers'),
     ('message_partner_ids', 'in', [user.partner_id.id])]
```

So with the default, **every internal user sees every project's documents**.
That is fine for a company-wide shelf. For a project that should be genuinely
per-project, set `privacy_visibility='followers'`.

## Modules

| Module | Access mode | Notes |
|---|---|---|
| `dms_record` | — | The shared mixin |
| `dms_project` | `inherit` | Project and task documents |
| `dms_hr_expense` | `inherit` | |
| `dms_calendar_event` | `inherit` | |
| `dms_fleet_vehicle` | `inherit` | |
| `dms_repair_order` | `inherit` | |
| `dms_hr_job_recruitment` | `inherit` (job), `owner` (applicant) | A candidate's CV is not company-wide |
| `dms_partner` | `inherit` | |
| `dms_sale_order` | `inherit` | |
| `dms_crm_lead` | `inherit` | |
| `dms_crm_team` | `team` | Group keyed on `member_ids` |
| `dms_purchase` | `inherit` | |
| `dms_hr_employee` | `owner` | Owner is the employee's `user_id` |
| `dms_product_template` | `inherit` | |
| `dms_helpdesk_ticket` | `inherit` | |
| `dms_helpdesk_team` | `team` | Group keyed on `user_id` |
| `dms_event` | `inherit` | |
| `dms_account_move` | `inherit` | |
| `dms_property_mgmt` | `inherit` | |
| `dms_webdav` | — | WebDAV endpoint at `/webdav/` |
| `dms_version` | — | File versioning |

## Testing a bridge

`dms_record/tests/bridge_case.py` holds the contract test. A bridge test only
declares what it is:

```python
@tagged("post_install", "-at_install")
class TestDmsSaleOrder(DmsBridgeCase):
    model = "sale.order"
    access_mode = "inherit"
    storage_xmlid = "dms_sale_order.sale_order_dms_storage"

    def _create_record_vals(self):
        return {"partner_id": self.env["res.partner"].create({"name": "Kund"}).id}

    def _create_record(self):
        return self.env["sale.order"].create(self._create_record_vals())
```

The base class then checks the directory exists, is linked by
`res_model`/`res_id`, sits under the declared storage's root, that files
inherit the link, that `doc_count` counts them, that the access mode matches
the storage, and that `_dms_ensure_directory()` is idempotent.

Run one bridge:

```bash
sudo checkmodule -d dms_test -m dms_sale_order -t -l test
```

`post_install` tests only run when the module is **updated**, not when it is
installed. Bump `version` in the manifest to force the update.
