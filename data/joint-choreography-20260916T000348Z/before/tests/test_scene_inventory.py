"""Scene inventory is authored data, never evidence of physical qualification."""

import copy
import json
import unittest
from unittest.mock import patch

from takeone.asset_library.catalog import AssetCatalog
from takeone.director import scene_assets
from takeone.director.creative import digest, plan_schema, validate
from takeone.director.provider import ResponsesPlanner
from takeone.director.scenes import scene_properties


class SceneInventoryTests(unittest.TestCase):
    def object(self):
        return dict(
            object_id="chair-1",
            asset_id="chair",
            label="Work chair",
            position_m=[1, 2, 0.45],
            size_m=[0.5, 0.6, 0.9],
            yaw_rad=0,
        )

    def test_legacy_object_validates_without_mutation(self):
        value = self.object()
        before = digest(value)
        validate(value, scene_properties()["objects"]["items"])
        self.assertEqual(before, digest(value))
        self.assertNotIn("availability", value)

    def test_inventory_declarations_are_bounded(self):
        for state in ("unconfirmed", "present", "proposed", "virtual_only"):
            validate(self.object() | dict(availability=state), scene_properties()["objects"]["items"])
        with self.assertRaises(ValueError):
            validate(
                self.object() | dict(availability="hardware_safe"), scene_properties()["objects"]["items"]
            )

    def test_generation_requires_inventory_but_legacy_validation_does_not(self):
        for required in (False, True):
            schema = plan_schema(require_movement=required)
            shape = schema["properties"]["scenes"]["items"]["properties"]["objects"]["items"]
            self.assertEqual("availability" in shape["required"], required)

    def test_instance_id_has_the_existing_40_character_limit(self):
        value = self.object() | dict(object_id="obj-12345678-1234-1234-1234-123456789012")
        validate(value, scene_properties()["objects"]["items"])
        with self.assertRaises(ValueError):
            validate(value | dict(object_id="x" * 41), scene_properties()["objects"]["items"])

    def test_actual_unsent_request_contains_guidance_and_grounded_ids(self):
        asset = dict(
            asset_id="lib:test:chair:0123456789abcdef",
            name="Chair",
            pack_id="test",
            kind="prop",
            tags=["interior"],
            dimensions_m=None,
            sha256="test",
        )
        catalog = AssetCatalog(dict(schema_version=1, assets=[asset]))
        payload = dict(
            brief=dict(title="A chair scene", objective="Quiet dialogue"),
            movement_catalog=dict(scene_catalog=dict(objects=[dict(id="table", name="Table")])),
        )
        original = copy.deepcopy(payload)
        with patch.object(scene_assets, "installed_catalog", return_value=catalog):
            raw, reserved = ResponsesPlanner(api_key="").request(payload, "creative_plan")
        body = json.loads(raw)
        self.assertEqual(original, payload)
        self.assertGreater(reserved, 0)
        self.assertIn(scene_assets.director_guidance(), body["instructions"])
        shape = body["text"]["format"]["schema"]["properties"]["scenes"]["items"]
        self.assertEqual(
            shape["properties"]["objects"]["items"]["properties"]["asset_id"]["enum"],
            ["table", asset["asset_id"]],
        )
