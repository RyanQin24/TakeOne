"""Verify the requested shot clock, zoom delay, and fixed-arm doorway take."""

import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path

from takeone.director.creative import digest
from takeone.director.studio import rehearsal_manifest
from takeone.previs.cache import compile_preview
from takeone.previs.templates import compile_template

from tests import test_orbit_http


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
            self.assertLessEqual(len(body), 131072)

    def test_second_take_places_subject_on_robot_left(self):
        # Drive-forward is derived from axle travel, not render-model axes.
        preview = self.previews[1]
        frames = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8]
        dx = frames[-1]["axle_m"][0] - frames[0]["axle_m"][0]
        dy = frames[-1]["axle_m"][1] - frames[0]["axle_m"][1]
        self.assertGreater(dy, 0)  # Preserve original forward travel direction.
        for f in frames:
            to_actor = [f["face"][i] - f["axle_m"][i] for i in (0, 1)]
            self.assertGreater(dx * to_actor[1] - dy * to_actor[0], 0)
            self.assertGreater(f["camera"]["pos"][0], f["face"][0])

    def test_third_take_requests_faster_cruise_with_accepted_ramp_cap(self):
        settings = self.manifest["shots"][2]["settings"]
        self.assertEqual(settings["speed_m_s"], 0.3)
        self.assertTrue(all(k["value"] == 0.275 for k in settings["channels"]["pace_m_s"]))
        self.assertAlmostEqual(self.previews[2]["summary"]["peak_speed_m_s"], 0.275)

    def test_zoom_does_not_start_before_two_seconds(self):
        preview = self.previews[1]
        for frame in preview["frames"]:
            t = frame["time_s"] - preview["orbit_start_s"]
            if 0 <= t <= 2 + 1e-8:
                self.assertAlmostEqual(frame["focal_mm"], 24)
            if t >= 3 - 1e-8:
                self.assertAlmostEqual(frame["focal_mm"], 180)
        self.assertAlmostEqual(preview["frames"][-1]["focal_mm"], 180)
        self.assertFalse(preview["summary"]["route_adapted"])

    def test_truck_shot_holds_both_arms_without_following_the_presenter(self):
        preview = self.previews[1]
        frames = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8]
        for frame in frames:
            self.assertEqual(frame["raw_by_role"], frames[0]["raw_by_role"])

    def test_all_arm_timelines_are_independent_of_human_height(self):
        for shot, original in zip(self.manifest["shots"], self.previews):
            settings = copy.deepcopy(shot["settings"])
            self.assertIn("camera_target_m", settings["channels"])
            self.assertIn("light_target_m", settings["channels"])
            settings["subject_height_m"] = 1.4
            changed = compile_preview(settings)
            self.assertEqual(
                [f["raw_by_role"] for f in original["frames"]], [f["raw_by_role"] for f in changed["frames"]]
            )

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


class TemplatePreviewBodyTests(unittest.TestCase):
    setUpClass = classmethod(test_orbit_http.OrbitHTTPTests.setUpClass.__func__)
    tearDownClass = classmethod(test_orbit_http.OrbitHTTPTests.tearDownClass.__func__)
    request = test_orbit_http.OrbitHTTPTests.request

    def test_template_preview_accepts_larger_bounded_json(self):
        body = json.dumps(dict(template_id="static", duration_s=0.5)).encode() + b" " * 5000
        status, data = self.request("/api/previs/templates", body)
        self.assertEqual(status, 200, data[:300])
        self.assertEqual(json.loads(data)["kind"], "takeone_template_previs")
        self.assertEqual(self.request("/api/previs/templates", b" " * 131073)[0], 400)


if __name__ == "__main__":
    unittest.main()
