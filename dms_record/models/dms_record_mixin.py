# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2022- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

ACCESS_MODES = [
    ("inherit", "Inherit from record"),
    ("team", "Access group"),
    ("owner", "Owner only"),
]


class DmsRecordMixin(models.AbstractModel):
    """One DMS directory per record.

    A bridge module inherits this model and declares

        _dms_storage_xmlid = "my_module.my_storage"
        _dms_access_mode = "inherit" | "team" | "owner"

    and ships a ``data/*.xml`` with the ``dms.storage`` and its root
    ``dms.directory``. The mixin then creates the per-record directory on
    ``create()`` and keeps it reachable as ``dms_directory_id``.

    The identity of the link is ``res_model``/``res_id``, never the name.
    """

    _name = "dms.record.mixin"
    _description = "DMS Record Mixin"

    # Declared by the bridge. No default: a bridge that forgets to choose an
    # access mode must fail loudly rather than inherit one by accident.
    _dms_storage_xmlid = False
    _dms_access_mode = False

    dms_directory_id = fields.Many2one(
        comodel_name="dms.directory",
        string="DMS Directory",
        compute="_compute_dms_directory_id",
        store=True,
        index=True,
        ondelete="set null",
    )
    doc_count = fields.Integer(
        string="Number of documents",
        compute="_compute_doc_count",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("display_name")
    def _compute_dms_directory_id(self):
        for record in self:
            record.dms_directory_id = record._dms_find_directory()

    def _compute_doc_count(self):
        for record in self:
            directory = record.dms_directory_id.sudo()
            if not directory:
                record.doc_count = 0
                continue
            record.doc_count = (
                self.env["dms.file"]
                .sudo()
                .search_count([("directory_id", "child_of", directory.ids)])
            )

    # ------------------------------------------------------------------
    # Hooks a bridge may override
    # ------------------------------------------------------------------
    def _dms_directory_name(self):
        """Name of the per-record directory.

        Cosmetic only. The link to the record is ``res_model``/``res_id``.

        Sibling directories must have unique names, and two records can share
        a ``display_name`` (``project.project`` allows it, and the demo data
        does). Appending the id keeps the name readable while guaranteeing
        uniqueness, so the second record's directory can be created instead of
        failing on the sibling-name constraint.
        """
        self.ensure_one()
        base = self.display_name or str(self.id)
        if self._dms_name_needs_disambiguation(base):
            return f"{base} ({self.id})"
        return base

    def _dms_name_needs_disambiguation(self, base):
        """Whether another record already claims ``base`` as a sibling name.

        Looks at the other records of this model that share the display name,
        not at directories: the directory of the other record may not exist
        yet, and the constraint is on the name the two would end up with.

        The lookup goes through ``_rec_name`` rather than ``display_name``:
        ``display_name`` is computed and not stored on most models, so it
        cannot be used in a domain.
        """
        self.ensure_one()
        if not base or base == str(self.id):
            return False
        rec_name = self._rec_name
        if not rec_name or rec_name not in self._fields:
            return False
        siblings = self.sudo().search(
            [("id", "!=", self.id), (rec_name, "=", self[rec_name])],
            limit=1,
        )
        return bool(siblings)

    def _dms_access_group(self):
        """``dms.access.group`` used in ``team`` mode.

        Bridges using ``team`` mode must override this.
        """
        self.ensure_one()
        return self.env["dms.access.group"]

    def _dms_owner_field(self):
        """Field naming the owner in ``owner`` mode.

        Bridges using ``owner`` mode must override this. The mixin does not
        guess: for ``hr.expense`` the owner is the employee, for
        ``sale.order`` it is the salesperson, and neither is obviously "the
        owner of the document".
        """
        self.ensure_one()
        return False

    # ------------------------------------------------------------------
    # Storage resolution
    # ------------------------------------------------------------------
    def _dms_get_storage(self):
        """Resolve ``_dms_storage_xmlid`` to a ``dms.storage``.

        Never creates a storage: the storage is a data decision made in the
        bridge's ``data/*.xml``, and a bridge that forgot it must fail here.
        """
        self.ensure_one()
        xmlid = self._dms_storage_xmlid
        if not xmlid:
            raise UserError(
                _(
                    "Model %(model)s inherits dms.record.mixin but does not "
                    "declare _dms_storage_xmlid. Add the attribute and a "
                    "dms.storage record in the module's data files.",
                    model=self._name,
                )
            )
        try:
            storage = self.env.ref(xmlid)
        except ValueError:
            storage = None
        if not storage or storage._name != "dms.storage":
            raise UserError(
                _(
                    "Model %(model)s declares _dms_storage_xmlid=%(xmlid)s, "
                    "which does not resolve to a dms.storage record.",
                    model=self._name,
                    xmlid=xmlid,
                )
            )
        return storage.sudo()

    def _dms_get_root_directory(self, storage):
        """Return the storage's root directory.

        A per-record directory needs a parent; ``_check_directory_parent``
        rejects a directory with neither a parent nor ``is_root_directory``.
        """
        self.ensure_one()
        root = storage.root_directory_ids.filtered("is_root_directory")[:1]
        if not root:
            raise UserError(
                _(
                    "Storage %(storage)s has no root directory. Every storage "
                    "used by dms.record.mixin needs one dms.directory with "
                    "is_root_directory=True.",
                    storage=storage.display_name,
                )
            )
        return root

    def _dms_validate_access_mode(self, storage):
        """Check that the declared access mode fits the declared storage.

        ``inherit`` needs ``save_type='attachment'``: the ACL domain in
        ``dms.security.mixin._get_domain_by_inheritance`` hardcodes both
        ``storage_id_save_type = 'attachment'`` and
        ``storage_id_inherit_access_from_parent_record = True``. A filestore
        or database storage never inherits.

        ``owner`` needs the opposite: an owner-scoped ``dms.access.group`` is
        what grants access, and attachment storage would bypass it by
        inheriting the record's rights instead.
        """
        self.ensure_one()
        mode = self._dms_access_mode
        if mode not in dict(ACCESS_MODES):
            raise UserError(
                _(
                    "Model %(model)s must declare _dms_access_mode as one of "
                    "%(modes)s; got %(mode)r.",
                    model=self._name,
                    modes=", ".join(dict(ACCESS_MODES)),
                    mode=mode,
                )
            )
        save_type = storage.save_type
        if mode == "inherit":
            if save_type != "attachment":
                raise UserError(
                    _(
                        "Model %(model)s uses access mode 'inherit', but "
                        "storage %(storage)s has save_type=%(save_type)s. "
                        "ACL inheritance requires save_type='attachment' and "
                        "inherit_access_from_parent_record=True.",
                        model=self._name,
                        storage=storage.display_name,
                        save_type=save_type,
                    )
                )
            if not storage.inherit_access_from_parent_record:
                raise UserError(
                    _(
                        "Model %(model)s uses access mode 'inherit', but "
                        "storage %(storage)s has "
                        "inherit_access_from_parent_record=False, so the "
                        "directory would inherit nothing.",
                        model=self._name,
                        storage=storage.display_name,
                    )
                )
        elif mode == "owner":
            if save_type == "attachment":
                raise UserError(
                    _(
                        "Model %(model)s uses access mode 'owner', but storage "
                        "%(storage)s has save_type='attachment'. An "
                        "owner-scoped access group cannot be combined with "
                        "attachment storage, because attachment storage "
                        "inherits the record's rights and ignores the group.",
                        model=self._name,
                        storage=storage.display_name,
                    )
                )
            if not self._dms_owner_field():
                raise UserError(
                    _(
                        "Model %(model)s uses access mode 'owner' but does not "
                        "override _dms_owner_field().",
                        model=self._name,
                    )
                )
        elif mode == "team":
            if not self._dms_access_group():
                raise UserError(
                    _(
                        "Model %(model)s uses access mode 'team' but "
                        "_dms_access_group() returned no group.",
                        model=self._name,
                    )
                )
        return True

    # ------------------------------------------------------------------
    # Directory lookup and creation
    # ------------------------------------------------------------------
    def _dms_find_directory(self):
        """Find this record's directory by ``res_model``/``res_id``.

        Never by name: a name lookup orphans the directory on rename,
        collides for two records with the same name, and raises
        ``Expected singleton`` on a multi-record hit.
        """
        self.ensure_one()
        return (
            self.env["dms.directory"]
            .sudo()
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("is_root_directory", "=", False),
                ],
                limit=1,
            )
        )

    def _dms_directory_vals(self):
        """Values for the per-record directory."""
        self.ensure_one()
        storage = self._dms_get_storage()
        self._dms_validate_access_mode(storage)
        root = self._dms_get_root_directory(storage)
        vals = {
            "name": self._dms_directory_name(),
            "parent_id": root.id,
            "storage_id": storage.id,
            "is_root_directory": False,
            "res_model": self._name,
            "res_id": self.id,
        }
        if self._dms_access_mode == "team":
            vals.update(
                {
                    "group_ids": [(6, 0, self._dms_access_group().ids)],
                    "inherit_group_ids": False,
                }
            )
        return vals

    def _dms_ensure_directory(self):
        """Return this record's directory, creating it if missing.

        Idempotent: adopts an existing directory rather than duplicating it.
        """
        self.ensure_one()
        directory = self._dms_find_directory()
        if directory:
            return directory
        vals = self._dms_directory_vals()
        directory = self.env["dms.directory"].sudo().create(vals)
        _logger.info(
            "Created DMS directory %s for %s,%s",
            directory.id,
            self._name,
            self.id,
        )
        return directory
    # ------------------------------------------------------------------
    # ORM hooks
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get("skip_dms_record_mixin"):
            return records
        for record in records:
            try:
                record._dms_ensure_directory()
            except (UserError, ValidationError):
                # A bridge that has not finished its configuration must not
                # block record creation; the bridge's test fails instead.
                _logger.exception(
                    "Could not create DMS directory for %s,%s",
                    record._name,
                    record.id,
                )
        # The compute ran during create(), before the directory existed, and
        # stored False. Recompute now that it is there.
        records.invalidate_recordset(["dms_directory_id", "doc_count"])
        records._compute_dms_directory_id()
        return records

    def write(self, vals):
        # ``display_name`` is usually computed from another field (``name`` on
        # project.project), so it is rarely in ``vals``. Capture the previous
        # name unconditionally and compare afterwards.
        previous = {
            record.id: (record.dms_directory_id, record._dms_directory_name())
            for record in self
            if record.dms_directory_id
        }
        result = super().write(vals)
        for record in self:
            directory, old_name = previous.get(record.id, (None, None))
            if not directory:
                continue
            new_name = record._dms_directory_name()
            if new_name == old_name:
                continue
            if directory.sudo().name != old_name:
                # The name was edited by hand; leave it alone.
                continue
            try:
                directory.sudo().write({"name": new_name})
            except Exception:
                _logger.warning(
                    "Could not rename DMS directory %s to %r",
                    directory.id,
                    new_name,
                    exc_info=True,
                )
        return result
