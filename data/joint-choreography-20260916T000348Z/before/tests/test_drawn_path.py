"""Shared path commands, geometry and actual preview parity; no devices."""

import json
import math
import unittest
from unittest.mock import patch

import numpy as np
from takeone.cart.response import CartResponse
from takeone.config import rig_config
from takeone.motion.studio_plan import prepare, validate
from takeone.previs.path import FOOT_M, compile_path, predict_route, validate_settings
from takeone.simulation.drive import cart_from_axle, integrate
from takeone.simulation.robot import load_model, pose_frame

from tests import test_orbit_http, test_studio_robot


class DrawnPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = validate_settings({"points_m": [[0, 2], [-0.8, 2], [-1.5, 1.5], [-2, 0.8]]})
        cls.result = compile_path(cls.settings)

    def test_feet_and_straight_line_distance(self):
        self.assertEqual(FOOT_M, 0.3048)
        route = predict_route(validate_settings({"points_m": [[1, 2], [1 + 10 * FOOT_M, 2]]}))
        self.assertLess(abs(route["poses"][-1][0] - (1 + 10 * FOOT_M)), 0.04)
        self.assertTrue(all(abs(p[1] - 2) < 1e-10 and abs(p[2]) < 1e-10 for p in route["poses"]))

    def test_packet_prediction_and_fk_match_every_preview_frame(self):
        plan, preview = self.result["plan"], self.result["preview"]
        self.assertEqual(validate(plan), plan)
        self.assertEqual(prepare(self.settings)["plan_id"], preview["plan_id"])
        cfg = rig_config()["cart"]
        response = CartResponse.load(cfg["minimum_speed_m_s"])
        start = preview["frames"][0]
        axle = np.array([*start["axle_m"], start["q"][2]])
        poses = [axle.copy()]
        for row in plan["cart_schedule"][:-1]:
            speeds = response.speeds_for(row["commands"])
            axle = integrate(axle, speeds[0] * 0.02, speeds[1] * 0.02, cfg["track_width_m"])
            poses.append(axle.copy())
        model = load_model()
        import mujoco

        data = mujoco.MjData(model)
        for frame in preview["frames"]:
            i = round(frame["time_s"] / 0.02)
            self.assertTrue(np.allclose(frame["q"][:3], cart_from_axle(poses[i]), atol=1e-10))
            sample = plan["samples"][round(frame["time_s"] / 0.04)]
            self.assertEqual(frame["raw_by_role"], sample["raw_by_role"])
            q = [*frame["q"][:3], *sample["arms"]["phone"], *sample["arms"]["light"]]
            actual = pose_frame(model, data, q, frame["time_s"], frame["drive"])
            self.assertTrue(np.allclose(actual["camera"]["pos"], frame["camera"]["pos"]))
        self.assertFalse(plan["summary"]["physical_path_verified"])

    def test_forward_commands_hold_and_calibrated_start_changes_to_tracking(self):
        plan = self.result["plan"]
        start = round(plan["orbit_start_s"] / 0.02)
        rows = plan["cart_schedule"][start:-1]
        for i, row in enumerate(rows):
            self.assertEqual(row["commands"], rows[i - i % 10]["commands"])
            self.assertTrue(all(c == 0 or 0.04 <= c <= 0.15 for c in row["commands"]))
        self.assertGreater(
            len(
                {
                    tuple(s["raw_by_role"]["phone"].values())
                    for s in plan["samples"]
                    if s["time_s"] > plan["orbit_start_s"]
                }
            ),
            4,
        )
        self.assertEqual(plan["samples"][0]["raw_by_role"], plan["initial_raw"])
        for a, b in zip(plan["samples"], plan["samples"][1:]):
            if a["time_s"] >= plan["orbit_start_s"]:
                for role in ("phone", "light"):
                    self.assertLessEqual(
                        max(abs(b["raw_by_role"][role][n] - v) for n, v in a["raw_by_role"][role].items()), 11
                    )

    def test_both_circle_directions_are_front_led_and_return_near_start(self):
        for direction in (1, -1):
            points = [
                [2 * math.cos(direction * i * math.tau / 48), 2 * math.sin(direction * i * math.tau / 48)]
                for i in range(49)
            ]
            route = predict_route(validate_settings({"points_m": points}))
            yaw = route["poses"][-1][2] - route["poses"][0][2]
            self.assertAlmostEqual(yaw, direction * math.tau, delta=0.3)
            self.assertLess(route["endpoint_error_m"], 0.08)
            self.assertTrue(all(min(r["commands"]) >= 0 for r in route["rows"]))

    def test_invalid_and_duplicate_points(self):
        for v in (
            None,
            [],
            {"points_m": [[0, 0]]},
            {"points_m": [[0, 0], [float("nan"), 2]]},
            {"speed_m_s": True},
            {"points_m": [[0, 0], [1, 1, 1]]},
            {"points_m": [[0, 0]] * 513},
            {"points_m": [[0, 0], [0, 0]]},
        ):
            with self.subTest(v=v), self.assertRaises(ValueError):
                validate_settings(v)
        settings = validate_settings({"points_m": [[0, 0], [0, 0], [1, 0]]})
        self.assertEqual(settings["points_m"], [[0.0, 0.0], [1.0, 0.0]])

    def test_saved_settings_roundtrip_and_cached_results_are_independent(self):
        copied = compile_path(json.loads(json.dumps(self.settings)))
        self.assertEqual(copied["plan"]["plan_id"], self.result["plan"]["plan_id"])
        copied["plan"]["samples"][0]["raw_by_role"]["phone"]["wrist_roll"] = 0
        self.assertNotEqual(copied["plan"], compile_path(self.settings)["plan"])


class PathHTTPTests(unittest.TestCase):
    setUpClass = classmethod(test_orbit_http.OrbitHTTPTests.setUpClass.__func__)
    tearDownClass = classmethod(test_orbit_http.OrbitHTTPTests.tearDownClass.__func__)
    request = test_orbit_http.OrbitHTTPTests.request

    def test_path_endpoint_and_payload_larger_than_old_limit(self):
        points = [[i / 1000, 2.0] for i in range(250)]
        body = json.dumps({"mode": "path", "points_m": points}, indent=2).encode()
        self.assertGreater(len(body), 4096)
        status, content = self.request("/api/previs/path", body)
        self.assertEqual(status, 200, content[:200])
        result = json.loads(content)
        self.assertEqual(result["kind"], "takeone_path_previs")
        self.assertEqual(result["grid_spacing_m"], FOOT_M)
        self.assertEqual(self.request("/api/previs/path", b'{"points_m":[[0,0]]}')[0], 400)
        self.assertEqual(self.request("/api/previs/path", body, "https://example.com")[0], 403)

    def test_full_path_player_with_fake_cart_and_arms(self):
        # Reuse the fake-device contract to exercise the real player with a path
        # artifact, including changing raw goals and intentionally stale feedback.
        plan = prepare({"mode": "path", "points_m": [[0, 2.5], [-0.3, 2.48]]})
        self.assertNotEqual(
            plan["samples"][-1]["raw_by_role"],
            plan["samples"][round(plan["orbit_start_s"] / 0.04)]["raw_by_role"],
        )
        with patch.object(test_studio_robot, "prepare", return_value=plan):
            test_studio_robot.ControlTests.test_complete_playback_with_fake_devices_retains_arms_and_synchronizes_cart(
                self
            )
