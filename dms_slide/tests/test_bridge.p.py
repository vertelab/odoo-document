# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.dms_record.tests.bridge_case import DmsBridgeCase


@tagged("post_install", "-at_install")
class TestDmsSlideChannel(DmsBridgeCase):
    model = "slide.channel"
    access_mode = "inherit"
    storage_xmlid = "dms_slide.slide_channel_dms_storage"

    def _create_record_vals(self):
        return {"name": "Test course"}

    def _create_record(self):
        return self.env["slide.channel"].create(self._create_record_vals())


@tagged("post_install", "-at_install")
class TestDmsSlideSlide(DmsBridgeCase):
    model = "slide.slide"
    access_mode = "inherit"
    storage_xmlid = "dms_slide.slide_slide_dms_storage"

    def _create_record_vals(self):
        return {
            "name": "Test lesson",
            "channel_id": self.env["slide.channel"].create({"name": "Test course"}).id,
        }

    def _create_record(self):
        return self.env["slide.slide"].create(self._create_record_vals())

    def test_directory_sits_under_the_slide_storage_not_the_course(self):
        """A lesson's directory must not be nested under its course's."""
        slide = self._create_record()
        storage = self.env.ref(self.storage_xmlid)
        self.assertEqual(
            slide.dms_directory_id.parent_id,
            storage.root_directory_ids[:1],
            "A lesson's directory must sit under the lesson storage's root, "
            "not under its course's directory — otherwise moving the lesson "
            "to another course would orphan its files.",
        )
