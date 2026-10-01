"""AI world-design planning job applies semantic output through the local solver."""

import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from takeone.director.contracts import ProductionBrief, Session
from takeone.director.planning import CreativePlanning
from takeone.director.provider import ProviderResult, ResponsesPlanner
from takeone.director.repository import SessionRepository
from takeone.director.service import COMMAND_TTL_NS, DirectorService
from takeone.director.skills import sample_project


class Clock:
    value = 1_000_000_000_000_000_000

    def __call__(self):
        return self.value


class ProductionDesignPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = SessionRepository(Path(self.temp.name) / "director.sqlite3")
        self.clock = Clock()
        self.owner = DirectorService(self.repo, clock=self.clock)
        base = ResponsesPlanner(api_key="").config
        self.provider = ResponsesPlanner({**base, "enabled": True}, api_key="offline-fixture")
        self.planner = CreativePlanning(self.owner, self.provider)
        self.planner._dispatch = lambda job_id: None
        self.sample = sample_project("dialogue")
        self.session = Session.parse(
            self.owner.create(
                str(uuid4()),
                self.owner.epoch,
                self.clock() + COMMAND_TTL_NS,
                ProductionBrief.parse(self.sample["brief"]),
            )["session"]
        )

    def submit(self, action, payload):
        body = {
            "schema_version": 1,
            "operation_id": str(uuid4()),
            "runtime_epoch": self.owner.epoch,
            "expires_monotonic_ns": str(self.clock() + COMMAND_TTL_NS),
            "scope": asdict(self.session.scope()),
            "action": action,
            "payload": payload,
        }
        result = self.planner.submit(body, int(body["expires_monotonic_ns"]))
        if result.get("session"):
            self.session = Session.parse(result["session"])
        return result

    def test_ai_semantics_are_solved_locally_and_saved_as_scene_geometry(self):
        loaded = self.submit("load_sample", {"skill_id": "dialogue"})
        self.assertTrue(loaded["ok"])
        semantic = {
            "intent": {
                "environment": "late night workshop",
                "mood": "focused and warm",
                "story_functions": ["conversation"],
                "visual_needs": ["work surface", "practical", "foreground depth"],
                "camera_needs": ["foreground_reveal"],
                "actor_needs": ["clear dialogue area"],
                "mode": "pure_previs",
            },
            "requirements": [
                {
                    "role_id": "surface",
                    "query": "desk",
                    "purpose": "Shared dialogue work surface",
                    "categories": ["surface"],
                    "required": True,
                    "max_width_m": None,
                    "max_depth_m": None,
                    "max_height_m": None,
                },
                {
                    "role_id": "practical",
                    "query": "floor lamp",
                    "purpose": "Motivated practical light",
                    "categories": ["lighting"],
                    "required": True,
                    "max_width_m": None,
                    "max_depth_m": None,
                    "max_height_m": None,
                },
                {
                    "role_id": "foreground",
                    "query": "small plant",
                    "purpose": "Foreground depth",
                    "categories": ["vegetation"],
                    "required": False,
                    "max_width_m": 1.0,
                    "max_depth_m": None,
                    "max_height_m": None,
                },
            ],
            "relations": [
                {
                    "kind": "near",
                    "source": "practical",
                    "target": "surface",
                    "minimum_m": None,
                    "maximum_m": 1.8,
                    "weight": 1.0,
                },
                {
                    "kind": "foreground_of",
                    "source": "foreground",
                    "target": "surface",
                    "minimum_m": 0.8,
                    "maximum_m": None,
                    "weight": 1.0,
                },
            ],
            "routes": [],
            "bounds_m": [8.0, 8.0],
            "seed": 19,
        }
        started = self.submit(
            "request_world",
            {
                "scene_id": "scene-1",
                "instruction": "Give the dialogue real depth and motivated lighting.",
                "mode": "pure_previs",
                "seed": 19,
                "budget_consent": True,
            },
        )
        self.assertTrue(started["ok"], started)
        job_id = started["job_id"]
        self.planner._finish(
            job_id,
            ProviderResult(
                semantic,
                {
                    "source": "model_proposal",
                    "provider": "offline_fixture",
                    "model": self.provider.config["model"],
                    "input_digest": "fixture",
                },
            ),
        )
        detail = self.repo.inspect(self.session.session_id)
        creative = detail["creative"]
        scene = creative["document"]["scenes"][0]
        self.assertGreaterEqual(len(scene["objects"]), 2)
        self.assertTrue(all("production_role" in item for item in scene["objects"]))
        self.assertIn("Production design:", scene["location_notes"])
        self.assertEqual(creative["provenance"]["last_change"], "ai_production_design")
        self.assertEqual(creative["provenance"]["world_design"]["scene_id"], "scene-1")
        job = next(item for item in detail["jobs"] if item["job_id"] == job_id)
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["result"]["code"], "world_designed")


if __name__ == "__main__":
    unittest.main()
