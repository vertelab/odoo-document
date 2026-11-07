# -*- coding: utf-8 -*-
from odoo import models


class Job(models.Model):
    _inherit = ["hr.job", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_hr_job_recruitment.hr_job_dms_storage"
    _dms_access_mode = "inherit"


class Applicant(models.Model):
    _inherit = ["hr.applicant", "dms.record.mixin"]

    _dms_storage_xmlid = "dms_hr_job_recruitment.hr_applicant_dms_storage"
    _dms_access_mode = "owner"

    def _dms_owner_field(self):
        """The recruiter responsible for the candidate.

        ``hr.applicant.user_id`` is the recruitment officer; it is set from the
        job's recruiter when the application arrives.
        """
        self.ensure_one()
        return self.user_id
