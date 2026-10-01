"""Compact repeated catalog defaults without dropping choices or raising model budgets."""

import copy
import json
import unittest
from unittest.mock import patch

from takeone.director.contracts import encode
from takeone.director.creative import PRIMITIVES
from takeone.director.provider import ResponsesPlanner
from takeone.director.scene_assets import factor_template_defaults, provider_payload
from takeone.director.skills import SKILLS, sample_project
from takeone.director.studio import movement_catalog, skill_text


def request_payload(skill_id):
    sample = sample_project(skill_id)
    return dict(
        brief=sample["brief"],
        context=sample["context"],
        skill=SKILLS[skill_id],
        capabilities=PRIMITIVES,
        movement_catalog=movement_catalog(),
    )


class ProviderCatalogCompactionTests(unittest.TestCase):
    def test_every_template_default_is_byte_equivalent_after_reconstruction(self):
        original = movement_catalog()
        compact = copy.deepcopy(original)
        factor_template_defaults(compact)
        shared = compact["shared_template_defaults"]
        self.assertEqual(len(compact["templates"]), len(original["templates"]))
        for before, after in zip(original["templates"], compact["templates"]):
            resolved = dict(after, defaults=shared | after["defaults"])
            self.assertEqual(encode(resolved), encode(before), before["id"])
        self.assertLess(len(encode(compact)), len(encode(original)))

    def test_factoring_twice_keeps_the_same_resolved_catalog(self):
        catalog = movement_catalog()
        factor_template_defaults(catalog)
        once = copy.deepcopy(catalog)
        factor_template_defaults(catalog)
        self.assertEqual(catalog, once)

    def test_json_types_and_absent_keys_are_not_collapsed(self):
        original = {
            "templates": [
                {"id": "a", "defaults": {"mixed": True, "nested": {"n": 1}, "only_a": 0, "same": []}},
                {"id": "b", "defaults": {"mixed": 1, "nested": {"n": 1.0}, "same": []}},
            ]
        }
        compact = copy.deepcopy(original)
        factor_template_defaults(compact)
        self.assertEqual(compact["shared_template_defaults"], {"same": []})
        for before, after in zip(original["templates"], compact["templates"]):
            self.assertEqual(
                encode(before["defaults"]), encode(compact["shared_template_defaults"] | after["defaults"])
            )

    def test_empty_catalog_and_nonplanning_payloads_are_unchanged(self):
        for catalog in ({}, {"templates": []}):
            before = copy.deepcopy(catalog)
            factor_template_defaults(catalog)
            self.assertEqual(catalog, before)
        value = {"brief": {"title": "Line edit"}}
        self.assertIs(provider_payload(value, "creative_lines"), value)

    def test_provider_copy_does_not_change_the_browser_catalog(self):
        value = request_payload("cinematic")
        before = copy.deepcopy(value)
        compact = provider_payload(value, "creative_plan")
        self.assertEqual(value, before)
        self.assertIn("shared_template_defaults", compact["movement_catalog"])
        self.assertNotIn("shared_template_defaults", value["movement_catalog"])
        self.assertEqual(compact["movement_catalog"]["fields"], value["movement_catalog"]["fields"])

    def test_all_curated_plan_requests_fit_existing_limits_with_current_skills(self):
        planner = ResponsesPlanner(api_key="")
        limits = dict(planner.config)
        with patch("takeone.director.provider.http.client.HTTPSConnection") as network:
            for skill_id in SKILLS:
                with self.subTest(skill=skill_id):
                    raw, reserved = planner.request(request_payload(skill_id), "creative_plan")
                    self.assertLessEqual(len(raw), limits["max_request_bytes"])
                    self.assertLessEqual(reserved, limits["request_budget_microusd"])
                    self.assertIn(skill_text(), json.loads(raw)["instructions"])
            network.assert_not_called()
        self.assertEqual(planner.config, limits)

    def test_cinematic_sample_matches_the_current_generation_schema(self):
        from takeone.director.creative import plan_schema, validate

        validate(sample_project("cinematic")["document"], plan_schema())

    def test_redesign_request_uses_a_single_complete_shot_schema_with_existing_scene(self):
        payload = request_payload("cinematic")
        document = sample_project("cinematic")["document"]
        scene = document["scenes"][0]
        shot = scene["shots"][0]
        payload.update(
            redesign_shot_id=shot["shot_id"],
            shot=shot,
            instruction="Redesign the entrance while keeping the same two people.",
            actors=document["actors"],
            marks=document["marks"],
            visual_style=document["visual_style"],
            scene={k: v for k, v in scene.items() if k != "shots"},
        )
        planner = ResponsesPlanner(api_key="")
        raw, reserved = planner.request(payload, "creative_plan")
        request = json.loads(raw)
        self.assertEqual(set(request["text"]["format"]["schema"]["properties"]), {"shot"})
        self.assertIn("Preserve shot_id, start_ms, end_ms and capture exactly", request["instructions"])
        self.assertLessEqual(len(raw), planner.config["max_request_bytes"])
        self.assertLessEqual(reserved, planner.config["request_budget_microusd"])

    def test_actor_palette_schema_explains_the_renderer_hex_color_contract(self):
        import re

        from takeone.director.performers import appearance_schema, performance_schema

        for color in appearance_schema()["properties"].values():
            self.assertIsNotNone(re.fullmatch(color["pattern"], "#17263c"))
            self.assertIsNone(re.fullmatch(color["pattern"], "Dark-n"))
        for name in ("body_heading_rad", "look_at", "gestures"):
            self.assertIn("first at=0", performance_schema()["items"]["properties"][name]["description"])

    def test_single_shot_context_keeps_only_existing_assets_and_scene_marks(self):
        payload = request_payload("cinematic")
        document = sample_project("cinematic")["document"]
        scene = document["scenes"][0]
        payload.update(
            redesign_shot_id=scene["shots"][0]["shot_id"],
            scene={k: v for k, v in scene.items() if k != "shots"},
            marks=document["marks"] + [dict(mark_id="other-mark", scene_id="other-scene")],
            staged_head_targets={"available": True, "targets": [{"actor_id": "test-head"}]},
        )
        before = copy.deepcopy(payload)
        with patch("takeone.director.scene_assets.installed_catalog") as catalog:
            compact = provider_payload(payload, "creative_plan")
            catalog.assert_not_called()
        self.assertEqual(payload, before)
        self.assertEqual(compact["scene"], payload["scene"])
        self.assertEqual(compact["staged_head_targets"], payload["staged_head_targets"])
        self.assertTrue(all(m["scene_id"] == scene["scene_id"] for m in compact["marks"]))
        allowed = {o["asset_id"] for o in scene["objects"]}
        self.assertEqual({o["id"] for o in compact["movement_catalog"]["scene_catalog"]["objects"]}, allowed)

    def test_full_demo_request_with_installed_asset_matches_fits_request_budget(self):
        payload = request_payload("cinematic")
        payload["brief"]["objective"] = (
            "We are at University of Waterloo. Make a 60-second demo with actual dialogue, "
            "visible camera/cart movement and performer action, a reveal and a payoff. "
            "Use 4-6 purposeful shots and a proposed room layout, not measured venue claims."
        )
        planner = ResponsesPlanner(api_key="")
        raw, reserved = planner.request(payload, "creative_plan")
        self.assertLessEqual(len(raw), planner.config["max_request_bytes"])
        self.assertLessEqual(reserved, planner.config["request_budget_microusd"])
        self.assertEqual(json.loads(raw)["reasoning"]["effort"], "max")

    def test_selected_samples_declare_proxy_appearance_without_invented_attention(self):
        for skill_id in SKILLS:
            document = sample_project(skill_id)["document"]
            for actor in document["actors"]:
                self.assertEqual(set(actor["appearance"]), {"cloth", "pants", "skin", "hair", "shoe"})
            for scene in document["scenes"]:
                for shot in scene["shots"]:
                    self.assertEqual(shot["performers"], [])
                    self.assertEqual(shot["design"]["screen_targets"], [])

    def test_sample_staging_keeps_explicit_appearance_and_performer_tracks(self):
        from takeone.director.skills import stage_sample

        sample = sample_project("reaction")
        actor = sample["document"]["actors"][0]
        actor["appearance"]["cloth"] = "#17263c"
        shot = sample["document"]["scenes"][0]["shots"][0]
        track = dict(actor_id=actor["actor_id"], body_heading_rad=[], look_at=[], gestures=[])
        shot["performers"] = [track]
        stage_sample(sample)
        self.assertEqual(actor["appearance"]["cloth"], "#17263c")
        self.assertEqual(shot["performers"], [track])


if __name__ == "__main__":
    unittest.main()
