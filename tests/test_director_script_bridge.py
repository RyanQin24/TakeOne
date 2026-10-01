"""The film skill, model request and saved script use the same simulator contract."""

import copy
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from takeone.director.api import DirectorAPI
from takeone.director.contracts import ProductionBrief, Session
from takeone.director.creative import all_shots, plan_schema, validate, validate_plan
from takeone.director.planning import CreativePlanning
from takeone.director.provider import ProviderResult, ResponsesPlanner
from takeone.director.repository import SessionRepository
from takeone.director.service import COMMAND_TTL_NS, DirectorService
from takeone.director.skills import sample_project
from takeone.director.studio import movement_catalog, rehearsal_manifest, shot_settings


class DirectorScriptBridgeTests(unittest.TestCase):
    def test_cinematic_example_has_actual_movement_for_every_shot(self):
        sample = sample_project("cinematic")
        doc = validate_plan(sample["document"], ProductionBrief.parse(sample["brief"]), sample["context"])
        validate(doc, plan_schema())
        settings = [shot_settings(s)[0] for s in all_shots(doc)]
        self.assertEqual([s["template_id"] for s in settings], ["hero_orbit", "side_track", "dolly_zoom_out"])
        self.assertLess(settings[0]["height_start_m"], settings[0]["height_end_m"])
        self.assertEqual(settings[1]["subject_motion"], "walk")
        self.assertEqual(settings[1]["actor_distance_m"], settings[1]["distance_m"])

    def test_luna_max_request_uses_live_catalog_and_strict_schema_without_tools(self):
        provider = ResponsesPlanner(api_key="")
        sample = sample_project("cinematic")
        raw, cost = provider.request(
            {"brief": sample["brief"], "context": sample["context"], "movement_catalog": movement_catalog()},
            "creative_plan",
        )
        body = json.loads(raw)
        self.assertEqual(body["model"], "gpt-5.6-luna")
        self.assertEqual(body["reasoning"], {"effort": "max"})
        self.assertNotIn("tools", body)
        self.assertLess(cost, provider.config["request_budget_microusd"])
        schema = body["text"]["format"]["schema"]

        def strict(node):
            if node["type"] == "object":
                self.assertEqual(set(node["required"]), set(node["properties"]))
                self.assertFalse(node["additionalProperties"])
                for child in node["properties"].values():
                    strict(child)
            elif node["type"] == "array":
                strict(node["items"])

        strict(schema)
        validate(sample["document"], schema)

    def test_model_result_saved_then_translated_and_old_revision_refused(self):
        sample = sample_project("cinematic")
        with tempfile.TemporaryDirectory() as directory:
            repo = SessionRepository(Path(directory) / "director.sqlite3")
            owner = DirectorService(repo)
            provider = ResponsesPlanner(api_key="offline-test-only")
            planner = CreativePlanning(owner, provider)
            planner._dispatch = lambda job_id: None
            session = Session.parse(
                owner.create(
                    str(uuid4()),
                    owner.epoch,
                    owner.clock() + COMMAND_TTL_NS,
                    ProductionBrief.parse(sample["brief"]),
                )["session"]
            )
            expiry = owner.clock() + COMMAND_TTL_NS
            request = dict(
                schema_version=1,
                operation_id=str(uuid4()),
                runtime_epoch=owner.epoch,
                expires_monotonic_ns=str(expiry),
                scope=asdict(session.scope()),
                action="request_plan",
                payload=dict(context=sample["context"], budget_consent=True),
            )
            receipt = planner.submit(request, expiry)
            self.assertTrue(receipt["ok"], receipt)
            planner._finish(
                receipt["job_id"],
                ProviderResult(
                    copy.deepcopy(sample["document"]),
                    {"source": "fixture", "provider": "offline_acceptance", "model": "gpt-5.6-luna"},
                ),
            )
            detail = repo.inspect(session.session_id)
            digest = detail["creative"]["digest"]
            manifest = DirectorAPI(owner).get(f"/api/director/studio/{session.session_id}/{digest}")
            self.assertEqual(
                [s["settings"]["template_id"] for s in manifest["shots"]],
                ["hero_orbit", "side_track", "dolly_zoom_out"],
            )
            self.assertEqual(manifest, rehearsal_manifest(detail, digest))
            with self.assertRaisesRegex(ValueError, "script changed"):
                rehearsal_manifest(detail, "0" * 64)


if __name__ == "__main__":
    unittest.main()
