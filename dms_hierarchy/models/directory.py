from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class Directory(models.Model):
    _inherit = "dms.directory"

    @api.constrains("storage_id", "model_id")
    def _check_storage_id_attachment_model_id(self):
        for record in self:
            if record.storage_id.save_type != "attachment":
                continue
            if not record.model_id:
                raise ValidationError(
                    _("A directory has to have model in attachment storage.")
                )
            # if not record.parent_id.is_root_directory and not record.res_id:
            #     raise ValidationError(
            #         _("This directory needs to be associated to a record.")
            #     )

    @api.onchange("parent_id", "model_id")
    def set_res_model(self):
        if not self.parent_id.is_root_directory and self.parent_id and (self.parent_id.model_id == self.model_id):
            self.res_id = self.parent_id.res_id
        elif self.parent_id.is_root_directory and self.env.context.get("special_res_id"):
            self.res_id = self.env.context.get("special_res_id")
        else:
            self.res_id = False

