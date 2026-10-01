"""Verify the requested shot clock, zoom delay, and fixed-arm doorway take."""

import importlib.util
import json
import math
import unittest
from pathlib import Path

from takeone.director.creative import digest
from takeone.director.studio import rehearsal_manifest
from takeone.previs.cache import compile_preview
from takeone.previs.templates import compile_template


class HackathonFinalDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts/hackathon_final_demo.py"
        spec = importlib.util.spec_from_file_location("hackathon_demo", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.candidate = module.author()
        doc = cls.candidate["document"]
        detail = dict(
            session=dict(session_id="test", revision=0, brief=cls.candidate["brief"]),
            creative=dict(document=doc, digest=digest(doc), context=cls.candidate["context"]),
        )
        cls.manifest = rehearsal_manifest(detail, digest(doc))
        cls.previews = [compile_preview(s["settings"]) for s in cls.manifest["shots"]]

    def test_three_exact_source_durations(self):
        self.assertEqual(len(self.manifest["shots"]), 3)
        self.assertEqual([p["orbit_duration_s"] for p in self.previews], [5, 5, 11])
        self.assertEqual(self.candidate["brief"]["duration_ms"], 21000)

    def test_five_degree_lower_aim_for_every_take(self):
        for shot in self.manifest["shots"]:
            for key in shot["settings"]["channels"]["tilt_rad"]:
                self.assertAlmostEqual(key["value"], -math.radians(5))

    def test_each_scene_fits_existing_preview_request_limit(self):
        for shot in self.manifest["shots"]:
            body = json.dumps(shot["settings"], separators=(",", ":")).encode()
            self.assertLessEqual(len(body), 4096)

    def test_zoom_does_not_start_before_two_seconds(self):
        preview = self.previews[1]
        for frame in preview["frames"]:
            t = frame["time_s"] - preview["orbit_start_s"]
            if 0 <= t <= 2 + 1e-8:
                self.assertAlmostEqual(frame["focal_mm"], 24)
        self.assertAlmostEqual(preview["frames"][-1]["focal_mm"], 180)
        self.assertFalse(preview["summary"]["route_adapted"])

    def test_doorway_arm_goals_remain_constant_during_recording(self):
        preview = self.previews[2]
        frames = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8]
        for role in ("phone", "light"):
            first = frames[0]["raw_by_role"][role]
            for frame in frames:
                self.assertEqual(frame["raw_by_role"][role], first)

    def test_doorway_cart_moves_only_from_three_to_five_seconds(self):
        result = compile_template(self.manifest["shots"][2]["settings"])
        preview = result["preview"]
        frames = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8]
        start = frames[0]["axle_m"]
        end = frames[-1]["axle_m"]
        moved = []
        for a, b in zip(frames, frames[1:]):
            t = a["time_s"] - preview["orbit_start_s"]
            if math.dist(a["axle_m"], b["axle_m"]) > 1e-8:
                moved.append(t)
            if t < 3 - 1e-8:
                self.assertLess(math.dist(a["axle_m"], start), 1e-8)
            if t >= 5 - 1e-8:
                self.assertLess(math.dist(a["axle_m"], end), 1e-8)
        # Preview frames sample interval endpoints. The command schedule is
        # authoritative for the exact start and stop times.
        scheduled = [
            row["time_s"] - preview["orbit_start_s"]
            for row in result["plan"]["cart_schedule"]
            if any(row["commands"])
        ]
        self.assertAlmostEqual(min(scheduled), 3)
        self.assertAlmostEqual(max(scheduled) + 0.02, 5)
        self.assertGreater(math.dist(start, end), 0.3)


if __name__ == "__main__":
    unittest.main()
