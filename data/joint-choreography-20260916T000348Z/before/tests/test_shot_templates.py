"""Changing optical height, matching motor goals and bounded cache reuse. No IO."""

import copy
import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from takeone.motion.studio_plan import prepare, validate
from takeone.previs import path
from takeone.previs.choreography import camera_height, validate_choreography
from takeone.previs.templates import DEFAULTS, compile_template, path_settings, validate_settings

from tests import test_drawn_path, test_orbit_http, test_studio_robot


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = compile_template(DEFAULTS)
        cls.settings = DEFAULTS

    def test_lift_reaches_chest_to_eye_level_and_upward_tilt_returns_to_level(self):
        p = self.result["preview"]
        frames = [f for f in p["frames"] if f["time_s"] >= p["orbit_start_s"]]
        first, last = frames[0], frames[-1]
        self.assertAlmostEqual(first["camera"]["pos"][2], 1.25, delta=0.015)
        self.assertAlmostEqual(last["camera"]["pos"][2], 1.59, delta=0.015)
        self.assertGreater(first["camera_pitch_deg"], 8)
        self.assertLess(abs(last["camera_pitch_deg"]), 1)
        self.assertLess(p["summary"]["max_aim_error_deg"], 3)
        for role in ("phone", "light"):
            # Motor 2 and other joints must change during the actual shot, not
            # merely during the initial calibrated-to-filming transition.
            lift = [f["raw_by_role"][role]["shoulder_lift"] for f in frames]
            self.assertGreater(max(lift) - min(lift), 200)
        self.assertEqual(p["frames"][0]["raw_by_role"], p["initial_raw"])

    def test_full_motor_packet_and_fk_parity(self):
        # Independently integrate every wheel packet and reconstruct every
        # displayed camera pose from its actual integer motor sample.
        test_drawn_path.DrawnPathTests.test_packet_prediction_and_fk_match_every_preview_frame(self)

    def test_prepare_and_saved_template_keep_identity_and_changing_arm_goals(self):
        plan = validate(prepare(json.loads(json.dumps(DEFAULTS))))
        self.assertEqual(plan["plan_id"], self.result["preview"]["plan_id"])
        self.assertEqual(plan["settings"]["template_id"], "hero_orbit")
        self.assertNotEqual(
            plan["samples"][-1]["raw_by_role"],
            plan["samples"][round(plan["orbit_start_s"] / 0.04)]["raw_by_role"],
        )
        altered = copy.deepcopy(plan)
        altered["settings"]["height_end_m"] = 1.4
        with self.assertRaises(ValueError):
            validate(altered)

    def test_quintic_hold_intervals_and_reverse_height_direction(self):
        c = path_settings(DEFAULTS)["choreography"]
        self.assertEqual(camera_height(c, 0, 9), c["height_start_m"])
        self.assertEqual(camera_height(c, 1, 9), c["height_end_m"])
        hs = [camera_height(c, u, 9) for u in np.linspace(0, 1, 101)]
        self.assertTrue(all(b >= a for a, b in zip(hs, hs[1:])))
        self.assertLess(abs(camera_height(c, 0.10001, 9) - camera_height(c, 0.1, 9)), 1e-10)
        reverse = c | {"height_start_m": 1.59, "height_end_m": 1.25}
        self.assertGreater(camera_height(reverse, 0.25, 9), camera_height(reverse, 0.75, 9))

    def test_cached_wheel_prediction_survives_height_edits_without_stale_arm_poses(self):
        # A lens/height change must not recompute identical cart decisions.
        path._route.cache_clear()
        path._compile.cache_clear()
        with patch.object(path, "predict_route", wraps=path.predict_route) as route:
            a = compile_template(DEFAULTS)
            b = compile_template(DEFAULTS | {"height_end_m": 1.50})
            self.assertEqual(route.call_count, 1)
        self.assertNotEqual(a["plan"]["plan_id"], b["plan"]["plan_id"])
        self.assertEqual(a["plan"]["cart_schedule"], b["plan"]["cart_schedule"])
        self.assertGreater(
            abs(
                a["preview"]["frames"][-1]["camera"]["pos"][2]
                - b["preview"]["frames"][-1]["camera"]["pos"][2]
            ),
            0.06,
        )
        a["preview"]["frames"][0]["q"][0] = 999
        self.assertNotEqual(compile_template(DEFAULTS)["preview"]["frames"][0]["q"][0], 999)

    def test_changed_source_key_cannot_hit_cached_wheel_geometry(self):
        key = json.dumps({"points_m": [[0, 2], [0.2, 2]], "speed_m_s": 0.17}, sort_keys=True)
        with patch.object(path, "predict_route", return_value={}) as predicted:
            path._route(key, "version-a")
            path._route(key, "version-a")
            path._route(key, "version-b")
            self.assertEqual(predicted.call_count, 2)

    def test_rejects_invalid_shot_parameters_and_rise_intervals(self):
        for value in (
            {"template_id": "dolly_zoom"},
            {"sweep_rad": -math.pi},
            {"speed_m_s": True},
            {"height_start_m": float("nan")},
            {"rise_start": 0.9, "rise_end": 0.5},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_settings(value)
        with self.assertRaises(ValueError):
            validate_choreography({"height_start_m": 1.2})

    def test_changing_goals_reach_actual_player_using_fake_devices(self):
        with patch.object(test_studio_robot, "prepare", return_value=self.result["plan"]):
            test_studio_robot.ControlTests.test_complete_playback_with_fake_devices_retains_arms_and_synchronizes_cart(
                self
            )


class TemplateHTTPTests(unittest.TestCase):
    setUpClass = classmethod(test_orbit_http.OrbitHTTPTests.setUpClass.__func__)
    tearDownClass = classmethod(test_orbit_http.OrbitHTTPTests.tearDownClass.__func__)
    request = test_orbit_http.OrbitHTTPTests.request

    def test_catalog_compile_and_validation(self):
        status, data = self.request("/api/previs/templates")
        self.assertEqual(status, 200)
        defaults = json.loads(data)["defaults"]
        status, data = self.request("/api/previs/templates", json.dumps(defaults).encode())
        self.assertEqual(status, 200, data[:200])
        self.assertEqual(json.loads(data)["kind"], "takeone_template_previs")
        self.assertEqual(self.request("/api/previs/templates", b'{"rise_end":0}')[0], 400)
        self.assertEqual(self.request("/api/previs/templates", b"{}", "https://example.com")[0], 403)
