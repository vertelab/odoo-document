## Declaring a bridge

```python
class MyModel(models.Model):
    _inherit = ["my.model", "dms.record.mixin"]

    _dms_storage_xmlid = "my_module.my_model_dms_storage"
    _dms_access_mode = "inherit"
```

```xml
<odoo>
  <data noupdate="1">
    <record id="my_model_dms_storage" model="dms.storage">
      <field name="name">My model documents</field>
      <field name="save_type">attachment</field>
      <field name="inherit_access_from_parent_record">True</field>
      <field name="model_ids" eval="[(6, 0, [ref('my_module.model_my_model')])]"/>
    </record>
    <record id="my_model_dms_directory" model="dms.directory">
      <field name="name">My model documents</field>
      <field name="is_root_directory">True</field>
      <field name="storage_id" ref="my_model_dms_storage"/>
      <field name="model_id" ref="my_module.model_my_model"/>
    </record>
  </data>
</odoo>
```

## The three access modes

| Mode | Storage must be | Access comes from | Right for |
|---|---|---|---|
| `inherit` | `save_type='attachment'` **and** `inherit_access_from_parent_record=True` | the record's own `ir.rule` | invoices, expenses — the record is the document's owner |
| `team` | any | a `dms.access.group` returned by `_dms_access_group()` | project documents — the team sees them, not the whole company |
| `owner` | **not** `attachment` | an access group scoped to `_dms_owner_field()` | HR, payslips — one person |

`inherit` requires attachment storage because the ACL domain in
`dms.security.mixin._get_domain_by_inheritance()` hardcodes both
`storage_id_save_type = 'attachment'` and
`storage_id_inherit_access_from_parent_record = True`. A filestore or S3
storage never inherits, no matter what the flag says.

`owner` requires the opposite: attachment storage would inherit the record's
rights and ignore the owner group. `dms_field` uses the same split — its
template storage domain excludes `attachment`.

## What `inherit` actually means

It means "whatever the record's `ir.rule` says", which is not always what the
phrase suggests. `project.project` defaults to `privacy_visibility='portal'`,
and its rule for internal users is:

```python
['|', ('privacy_visibility', '!=', 'followers'),
      ('message_partner_ids', 'in', [user.partner_id.id])]
```

So with the default, `inherit` gives **every internal user** access to **every
project's** documents. To make it genuinely per-project, set
`privacy_visibility='followers'` on the project, or use `team` mode.

## Where the bytes live

Independent of the access mode. `save_type='file'` and `'attachment'` both
write `content_file`, which Odoo stores as an `ir.attachment`; whether that
attachment lands on local disk or in S3 is decided by `fs.storage` at
deployment time, not by the bridge. Only `save_type='database'` differs — it
writes a `bytea` column and never reaches `fs_attachment`.

Note that `fs.storage.field_ids` selects by model+field, so moving
`dms.file.content_file` to S3 moves every DMS document at once. There is no
per-DMS-storage placement.

## The directory name is cosmetic

`_dms_directory_name()` defaults to `display_name`. It is recomputed on rename
when the directory's name still equals the previous computed value; a name
someone edited by hand is left alone.

Renaming a record therefore renames its folder in a WebDAV mount. That is
visible and acceptable: the mount is a view, `res_model`/`res_id` is the
identity.

## Skipping creation

Pass `context={'skip_dms_record_mixin': True}` to create records without
directories — for imports and for tests of unrelated behaviour.
