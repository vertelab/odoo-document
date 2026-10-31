# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsHrJob(DmsBridgeCase):
    model = "hr.job"
    access_mode = "inherit"
    storage_xmlid = "dms_hr_job_recruitment.hr_job_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test jobb"}

    def _create_record(self):
        return self.env["hr.job"].create(self._create_record_vals())


@tagged("post_install", "-at_install")
class TestDmsHrApplicant(DmsBridgeCase):
    model = "hr.applicant"
    access_mode = "owner"
    storage_xmlid = "dms_hr_job_recruitment.hr_applicant_dms_storage"

    def _create_record_vals(self):
        candidate = self.env["hr.candidate"].create(
            {"partner_name": "Test kandidat"}
        )
        return {
            "candidate_id": candidate.id,
            "job_id": self.env["hr.job"].create({"name": "Jobb"}).id,
        }

    def _create_record(self):
        return self.env["hr.applicant"].create(self._create_record_vals())
