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
