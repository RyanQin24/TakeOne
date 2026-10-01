"""Independent world marks reach the exact motor/FK path; no device IO."""

import json
import math
import unittest
from unittest.mock import patch

import mujoco
import numpy as np
from takeone.calibration import ArmMapping
from takeone.motion.studio_plan import prepare, validate
from takeone.planning.trajectory import sample_times
from takeone.previs.compiler import AimingSolver, compile_orbit, fixture_clearance
from takeone.previs.path import _compile, compile_path
from takeone.previs.placement import place_route, validate_scene
from takeone.previs.templates import compile_template, path_settings
from takeone.simulation.robot import load_model


class PlacementTests(unittest.TestCase):
    def test_placement_rotates_about_start_then_translates_in_metres(self):
        scene = validate_scene(
            dict(cart_start_m=[3, 4], route_rotation_rad=math.pi / 2, actor_position_m=[-1, 2])
        )
        np.testing.assert_allclose(place_route([[0, -2], [1, -2]], scene), [[3, 4], [3, 5]])
        for bad in (
            {"cart_start_m": [float("nan"), 0]},
            {"actor_facing": "guess"},
            {"actor_position_m": [True, 0]},
            {"route_rotation_rad": "90"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_scene(bad)

    def test_actor_and_cart_are_independent_and_arm_goals_change(self):
        base = dict(template_id="static", duration_s=2)
        original = compile_template(base)
        moved = compile_template(base | {"scene": {"actor_position_m": [0.6, 0.3]}})
        a, b = original["preview"], moved["preview"]
        self.assertEqual(a["frames"][0]["axle_m"], b["frames"][0]["axle_m"])
        self.assertEqual(b["frames"][-1]["actor"]["position_m"][:2], [0.6, 0.3])
        self.assertNotEqual(a["aiming_raw"]["phone"], b["aiming_raw"]["phone"])
        placed = compile_template(base | {"scene": {"cart_start_m": [1, -3]}})["preview"]
        self.assertEqual(placed["frames"][0]["axle_m"], [1, -3])
        self.assertEqual(placed["frames"][0]["actor"]["position_m"][:2], [0, 0])

    def test_drawn_world_points_survive_actor_moves_and_roundtrip_into_robot_plan(self):
        settings = dict(
            mode="path",
            points_m=[[-0.6, -2], [0.6, -2]],
            scene=dict(actor_position_m=[0.3, 0.2], actor_facing="fixed", actor_heading_rad=1.2),
        )
        result = compile_path(settings)
        preview, plan = result["preview"], validate(result["plan"])
        self.assertEqual(preview["requested_path_m"], settings["points_m"])
        saved = json.loads(json.dumps(preview["settings"]))
        self.assertEqual(prepare(saved)["plan_id"], plan["plan_id"])
        model, data = load_model(), None
        data = mujoco.MjData(model)
        for frame in preview["frames"][::9]:
            sample = plan["samples"][round(frame["time_s"] / 0.04)]
            self.assertEqual(frame["raw_by_role"], sample["raw_by_role"])
            self.assertEqual(frame["actor"]["heading_rad"], 1.2)
            for role, offset in (("phone", 3), ("light", 8)):
                expected = ArmMapping.load(role, require_motion=False).from_raw(sample["raw_by_role"][role])
                np.testing.assert_array_equal(frame["q"][offset : offset + 5], expected)
            data.qpos[:] = frame["q"]
            mujoco.mj_forward(model, data)
            np.testing.assert_allclose(data.site_xpos[model.site("cam_optical").id], frame["camera"]["pos"])

    def test_actor_holds_facing_during_orbit_unless_follow_is_explicit(self):
        for mode in ("opening", "fixed", "camera"):
            p = compile_template(
                dict(
                    template_id="arc_left",
                    sweep_rad=math.pi / 3,
                    scene=dict(actor_facing=mode, actor_heading_rad=1.2),
                )
            )["preview"]
            headings = [f["actor"]["heading_rad"] for f in p["frames"] if f["time_s"] >= p["orbit_start_s"]]
            if mode == "camera":
                self.assertGreater(max(headings) - min(headings), 0.8)
            else:
                self.assertEqual(len(set(headings)), 1)
            if mode == "fixed":
                self.assertEqual(headings[0], 1.2)

    def test_walking_target_starts_at_actor_mark_in_drawn_path(self):
        p = compile_path(
            dict(
                points_m=[[-0.4, -2], [0.4, -2]],
                scene=dict(
                    actor_position_m=[1, 0],
                    actor_motion="walk",
                    walk_distance_m=0.6,
                    walk_heading_rad=math.pi / 2,
                ),
            )
        )["preview"]
        np.testing.assert_allclose(p["frames"][0]["face"][:2], [1, 0])
        np.testing.assert_allclose(p["frames"][-1]["face"][:2], [1, 0.6])
        self.assertNotEqual(p["aiming_raw"]["phone"], p["frames"][-1]["raw_by_role"]["phone"])

    def test_phone_side_adaptations_are_explicit_and_original_direction_is_available(self):
        for name in ("truck_left", "arc_right"):
            adapted = compile_template(dict(template_id=name))["preview"]
            self.assertTrue(adapted["template"]["route_adapted"])
            self.assertIn("adapted", adapted["notes"][0])
            for f in adapted["frames"]:
                delta = np.array(f["face"][:2]) - f["q"][:2]
                left = np.array([-math.sin(f["q"][2]), math.cos(f["q"][2])])
                self.assertGreater(float(delta @ left), 2)
            a = path_settings(dict(template_id=name))["points_m"]
            b = path_settings(dict(template_id=name, scene=dict(filming_side="direction")))["points_m"]
            self.assertNotEqual(a, b)

    def test_off_centre_orbit_uses_same_commands_in_preview_and_prepare(self):
        settings = dict(
            radius_m=1.8, sweep_rad=math.pi / 4, duration_s=10, scene=dict(actor_position_m=[0.2, 0.1])
        )
        p = compile_orbit(settings)
        plan = prepare(p["settings"])
        self.assertEqual(p["plan_id"], plan["plan_id"])
        self.assertEqual(p["duration_s"], plan["duration_s"])
        self.assertEqual(p["frames"][0]["raw_by_role"], plan["initial_raw"])

    def test_light_uses_each_matching_quantized_phone_pose(self):
        _compile.cache_clear()
        original = AimingSolver.solve
        seen = []

        def observe(solver, q, role, target, height, **options):
            if role == "light":
                point, direction = solver.camera_clearance(q)
                np.testing.assert_allclose(options["clear"], point)
                np.testing.assert_allclose(options["clear_forward"], direction)
                seen.append(point[2])
            return original(solver, q, role, target, height, **options)

        with patch.object(AimingSolver, "solve", observe):
            compile_template(dict(template_id="boom_up", duration_s=4))
        self.assertGreater(max(seen) - min(seen), 0.3)

    def test_light_behind_lens_is_clear_even_when_on_axis(self):
        origin, forward = np.zeros(3), np.array([1.0, 0, 0])
        self.assertGreater(fixture_clearance(np.array([-0.4, 0, 0]), origin, forward), 0.3)
        self.assertLess(fixture_clearance(np.array([0.4, 0, 0]), origin, forward), 0)


class SamplingTests(unittest.TestCase):
    def test_union_has_no_near_duplicates_and_preserves_motor_dispatch_times(self):
        for duration in (9.0, 14.0, 5.153477):
            times = sample_times(duration, 0.04)
            self.assertGreater(float(np.min(np.diff(times))), 1e-10)
            self.assertTrue(set(np.arange(0.0, duration, 0.04)).issubset(times))
            self.assertEqual(times[-1], duration)
            velocity = np.gradient(times * 0.1375, times)
            acceleration = np.gradient(velocity, times)
            self.assertLess(float(np.max(abs(acceleration))), 1e-7)
