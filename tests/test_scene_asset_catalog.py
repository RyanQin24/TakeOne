"""Director asset contracts. No network, model request, device or paid service."""

import copy
import unittest
from unittest.mock import patch

from takeone.asset_library.catalog import AssetCatalog
from takeone.director import scene_assets


def record(index, name="Chair"):
    return {
        "asset_id": f"lib:test:chair-{index}:0123456789abcdef",
        "name": name,
        "pack_id": "test-furniture",
        "tags": ["interior"],
        "kind": "prop",
        "dimensions_m": None,
        "sha256": str(index),
    }


class SceneAssetCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = AssetCatalog({"schema_version": 1, "assets": [record(i) for i in range(80)]})
        self.patch = patch.object(scene_assets, "installed_catalog", return_value=self.catalog)
        self.open = self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_editor_preserves_procedural_and_installed_choices(self):
        result = scene_assets.catalog_choices({"table": ("Work table", [1.6, 0.8, 0.75])})
        self.assertEqual(result[0]["id"], "table")
        self.assertEqual(len(result), 81)

    def test_legacy_scene_does_not_depend_on_the_optional_installation(self):
        scene_assets.validate_assets({"scenes": [{"objects": [{"asset_id": "table"}]}]}, {"table": ()})
        self.open.assert_not_called()

    def test_installed_ids_are_accepted_without_an_enum_patch(self):
        scene_assets.validate_assets({"scenes": [{"objects": [{"asset_id": record(7)["asset_id"]}]}]}, {})

    def test_unknown_ids_are_not_silently_rendered_as_boxes(self):
        for asset_id in ["new-chair", "lib:invented:chair"]:
            with self.subTest(asset_id=asset_id), self.assertRaises(ValueError):
                scene_assets.validate_assets({"scenes": [{"objects": [{"asset_id": asset_id}]}]}, {})

    def test_catalog_records_are_copies(self):
        values = self.catalog.all()
        values[0]["name"] = "Changed"
        self.assertNotEqual(self.catalog.get(values[0]["asset_id"])["name"], "Changed")

    def test_provider_shortlist_is_bounded_and_does_not_mutate_ui_catalog(self):
        payload = {
            "brief": {"title": "An interior chair scene", "objective": "Two performers"},
            "movement_catalog": {
                "scene_catalog": {"objects": scene_assets.catalog_choices({"table": ("Table", [1, 1, 1])})}
            },
        }
        original = copy.deepcopy(payload)
        result = scene_assets.provider_payload(payload, "creative_plan")
        self.assertEqual(payload, original)
        self.assertEqual(len(result["movement_catalog"]["scene_catalog"]["objects"]), 33)
        self.assertEqual(result["movement_catalog"]["scene_catalog"]["installed_count"], 80)

    def test_unmatched_brief_gets_only_a_small_starter_selection(self):
        payload = {"brief": {"title": "xyz"}, "movement_catalog": {"scene_catalog": {"objects": []}}}
        result = scene_assets.provider_payload(payload, "creative_plan")
        self.assertEqual(len(result["movement_catalog"]["scene_catalog"]["objects"]), 16)

    def test_line_assistance_is_not_rewritten_as_scene_generation(self):
        payload = {"brief": {"title": "chair"}}
        self.assertIs(scene_assets.provider_payload(payload, "creative_lines"), payload)
        self.open.assert_not_called()

    def test_model_context_has_no_filesystem_or_dependency_inventory(self):
        choice = scene_assets.asset_choice(record(1))
        self.assertNotIn("uri", choice)
        self.assertNotIn("dependencies", choice)
        self.assertIn("dimensions", choice["provenance"])

    def test_unknown_source_dimensions_are_not_called_measured(self):
        self.assertIn("confirm physical availability", scene_assets.asset_choice(record(1))["provenance"])

    def test_generation_skill_uses_the_real_beat_contract(self):
        guidance = scene_assets.director_guidance()
        self.assertIn("design.beats", guidance)
        self.assertNotIn("design.performance_beats", guidance)
        self.assertIn("not an available actor", guidance)

    def test_new_model_records_need_no_new_renderer_branch(self):
        self.catalog = AssetCatalog({"schema_version": 1, "assets": [record(100, "Desk Plant")]})
        self.open.return_value = self.catalog
        self.assertEqual(scene_assets.catalog_choices({})[0]["id"], record(100)["asset_id"])
