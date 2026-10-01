"""Movement semantics and exact motor/FK/lens parity. No device IO."""

import copy
import json
import math
import unittest

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from takeone.calibration import ArmMapping
from takeone.cart.response import CartResponse
from takeone.config import rig_config
from takeone.motion.studio_plan import validate
from takeone.previs.templates import PRESETS, catalog, compile_template, validate_settings
from takeone.simulation.drive import cart_from_axle, integrate
from takeone.simulation.robot import load_model, pose_frame


class MovementLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {p["id"]: compile_template({"template_id": p["id"]}) for p in PRESETS}

    def filming(self, id):
        p = self.results[id]["preview"]
        return [f for f in p["frames"] if f["time_s"] >= p["orbit_start_s"]]

    def test_catalog_exposes_38_implemented_presets_and_editable_defaults(self):
        data = catalog()
        self.assertEqual(len(data["templates"]), 38)
        self.assertEqual(len({t["family"] for t in data["templates"]}), 8)
        for t in data["templates"]:
            with self.subTest(id=t["id"]):
                self.assertEqual(t["status"], "implemented")
                self.assertEqual(validate_settings(t["defaults"]), t["defaults"])
                self.assertTrue(set(t["parameters"]) <= set(data["fields"]))
        data["templates"][0]["defaults"]["radius_m"] = 999
        self.assertNotEqual(catalog()["templates"][0]["defaults"]["radius_m"], 999)

    def test_every_default_has_a_complete_calibrated_motor_clock_and_aim(self):
        for id, result in self.results.items():
            with self.subTest(id=id):
                plan = validate(result["plan"])
                self.assertEqual(plan["samples"][0]["raw_by_role"], plan["initial_raw"])
                self.assertEqual(plan["plan_id"], result["preview"]["plan_id"])
                self.assertLess(result["preview"]["summary"]["max_aim_error_deg"], 3.0)
                self.assertEqual(plan["cart_schedule"][-1]["commands"], [0, 0])
                self.assertTrue(all(min(row["commands"]) >= 0 for row in plan["cart_schedule"]))
                self.assertTrue(all(cue["source"] == "simulated_lens_cue" for cue in plan["camera_cues"]))

    def test_all_cart_packets_and_displayed_camera_poses_match_independent_integration_and_fk(self):
        model = load_model()
        data = mujoco.MjData(model)
        cfg = rig_config()["cart"]
        response = CartResponse.load(cfg["minimum_speed_m_s"])
        for id, result in self.results.items():
            with self.subTest(id=id):
                plan, preview = result["plan"], result["preview"]
                first = preview["frames"][0]
                axle = np.array([*first["axle_m"], first["q"][2]])
                poses = [axle.copy()]
                for row in plan["cart_schedule"][:-1]:
                    velocities = response.speeds_for(row["commands"])
                    axle = integrate(axle, velocities[0] * 0.02, velocities[1] * 0.02, cfg["track_width_m"])
                    poses.append(axle.copy())
                for frame in preview["frames"]:
                    sample = plan["samples"][round(frame["time_s"] / 0.04)]
                    self.assertEqual(frame["raw_by_role"], sample["raw_by_role"])
                    q = [
                        *cart_from_axle(poses[round(frame["time_s"] / 0.02)]),
                        *sample["arms"]["phone"],
                        *sample["arms"]["light"],
                    ]
                    self.assertTrue(np.allclose(q, frame["q"], atol=1e-10))
                    actual = pose_frame(model, data, q, frame["time_s"], frame["drive"])
                    for role in ("camera", "light"):
                        self.assertTrue(np.allclose(actual[role]["pos"], frame[role]["pos"], atol=1e-10))
                        self.assertTrue(np.allclose(actual[role]["quat"], frame[role]["quat"], atol=1e-10))

    def test_every_preset_starts_filming_with_the_physical_phone_in_landscape(self):
        model, mappings = (
            load_model(),
            {r: ArmMapping.load(r, require_motion=False) for r in ("phone", "light")},
        )
        data = mujoco.MjData(model)
        handset = model.geom("cam_payload").id
        long_axis = int(np.argmax(model.geom_size[handset]))
        for id, result in self.results.items():
            with self.subTest(id=id):
                preview, plan = result["preview"], result["plan"]
                opening = self.filming(id)[0]
                sample = plan["samples"][round(preview["orbit_start_s"] / 0.04)]
                # Decode the actual player goals, not a corrected camera_view.
                data.qpos[:3] = opening["q"][:3]
                for j, role in enumerate(("phone", "light")):
                    data.qpos[3 + 5 * j : 8 + 5 * j] = mappings[role].from_raw(sample["raw_by_role"][role])
                mujoco.mj_forward(model, data)
                long_edge = data.geom_xmat[handset].reshape(3, 3)[:, long_axis]
                self.assertLess(abs(long_edge[2]), math.sin(math.radians(2)))
                self.assertEqual(opening["raw_by_role"], sample["raw_by_role"])
                self.assertEqual(plan["samples"][0]["raw_by_role"], plan["initial_raw"])
                self.assertTrue(
                    all(
                        row["commands"] == [0.0, 0.0]
                        for row in plan["cart_schedule"]
                        if row["time_s"] < preview["orbit_start_s"]
                    )
                )

    def test_static_and_zoom_keep_the_camera_and_cart_fixed(self):
        for id in ("static", "zoom_in", "zoom_out"):
            frames = self.filming(id)
            self.assertTrue(all(f["raw_by_role"] == frames[0]["raw_by_role"] for f in frames))
            self.assertEqual(self.results[id]["preview"]["summary"]["distance_m"], 0)
        self.assertGreater(self.filming("zoom_in")[-1]["focal_mm"], self.filming("zoom_in")[0]["focal_mm"])
        self.assertLess(self.filming("zoom_out")[-1]["focal_mm"], self.filming("zoom_out")[0]["focal_mm"])

    def test_every_default_keeps_cart_and_actor_separate_including_initial_setup(self):
        for id, result in self.results.items():
            with self.subTest(id=id):
                for frame in result["preview"]["frames"]:
                    # Ground-centre separation, including the calibrated first
                    # frame, catches an unpositioned/default cart at the actor.
                    separation = math.dist(frame["q"][:2], frame["actor"]["position_m"][:2])
                    self.assertGreater(separation, 1.0)

    def test_locked_camera_stays_put_when_the_actor_walks_across_frame(self):
        preview = compile_template({"template_id": "static", "subject_motion": "walk"})["preview"]
        frames = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"]]
        self.assertTrue(all(f["raw_by_role"]["phone"] == frames[0]["raw_by_role"]["phone"] for f in frames))
        self.assertGreater(math.dist(frames[0]["face"], frames[-1]["face"]), 1.4)

    def test_lens_holds_its_starting_value_during_calibrated_arm_setup(self):
        for id in ("dolly_zoom_in", "dolly_zoom_out", "zoom_in", "zoom_out"):
            preview = self.results[id]["preview"]
            setup = [f for f in preview["frames"] if f["time_s"] <= preview["orbit_start_s"]]
            self.assertTrue(all(f["focal_mm"] == preview["settings"]["focal_mm"] for f in setup))

    def test_pan_and_tilt_change_optical_direction_in_the_named_direction(self):
        for id, sign in (("pan_left", 1), ("pan_right", -1), ("whip_pan", 1)):
            frames = self.filming(id)
            forward = [
                Rotation.from_quat(f["camera"]["quat"]).apply([0, 0, 1]) for f in (frames[0], frames[-1])
            ]
            yaw = math.atan2(np.cross(forward[0], forward[1])[2], np.dot(forward[0], forward[1]))
            self.assertGreater(sign * math.degrees(yaw), 23)
        for id, sign in (("tilt_up", 1), ("tilt_down", -1)):
            f = self.filming(id)
            self.assertGreater(sign * (f[-1]["camera_pitch_deg"] - f[0]["camera_pitch_deg"]), 25)

    def test_dolly_zooms_preserve_projected_scale_and_change_focal_length_in_opposite_directions(self):
        for id, sign in (("dolly_zoom_in", -1), ("dolly_zoom_out", 1)):
            frames = self.filming(id)
            scales = [f["focal_mm"] / f["optical_depth_m"] for f in frames]
            self.assertLess(max(scales) - min(scales), 1e-10)
            self.assertGreater(sign * (frames[-1]["focal_mm"] - frames[0]["focal_mm"]), 10)
            self.assertGreater(self.results[id]["preview"]["summary"]["distance_m"], 1.4)

    def test_roll_is_achieved_by_wrist_motor_6_and_optical_horizon(self):
        for id, sign in (("roll_left", 1), ("roll_right", -1)):
            frames = self.filming(id)
            self.assertGreater(
                abs(
                    frames[-1]["raw_by_role"]["phone"]["wrist_roll"]
                    - frames[0]["raw_by_role"]["phone"]["wrist_roll"]
                ),
                250,
            )
            r = Rotation.from_quat(frames[-1]["camera"]["quat"]).as_matrix()
            forward, right = r[:, 2], r[:, 0]
            level = np.cross(forward, [0, 0, 1])
            level /= np.linalg.norm(level)
            roll = math.degrees(math.atan2(np.dot(right, np.cross(forward, level)), np.dot(right, level)))
            self.assertAlmostEqual(roll, sign * 25, delta=0.5)

    def test_vertical_moves_translate_the_optical_origin_and_both_hero_arms_move(self):
        for id, sign in (("boom_up", 1), ("boom_down", -1), ("crane_reveal", 1), ("hero_orbit", 1)):
            frames = self.filming(id)
            self.assertGreater(sign * (frames[-1]["camera"]["pos"][2] - frames[0]["camera"]["pos"][2]), 0.30)
        hero = self.filming("hero_orbit")
        for role in ("phone", "light"):
            values = [f["raw_by_role"][role]["shoulder_lift"] for f in hero]
            self.assertGreater(max(values) - min(values), 200)

    def test_walk_face_target_matches_displayed_actor_body_and_stride(self):
        for id in ("track_follow", "track_lead", "side_track"):
            frames = self.filming(id)
            settings = self.results[id]["preview"]["settings"]
            self.assertGreater(
                math.dist(frames[0]["actor"]["position_m"], frames[-1]["actor"]["position_m"]), 1.4
            )
            self.assertGreater(max(f["actor"]["gait_weight"] for f in frames), 0.99)
            phases = [f["actor"]["phase_rad"] for f in frames]
            self.assertEqual(phases, sorted(phases))
            for f in frames:
                actor, face = f["actor"], f["face"]
                self.assertEqual(actor["position_m"][:2], face[:2])
                self.assertAlmostEqual(face[2], settings["subject_height_m"] * 0.925 + actor["position_m"][2])

    def test_handheld_is_repeatable_and_is_not_a_static_pose(self):
        frames = self.filming("handheld")
        values = [f["raw_by_role"]["phone"]["shoulder_pan"] for f in frames]
        self.assertGreater(max(values) - min(values), 15)
        self.assertEqual(frames[0]["raw_by_role"], frames[-1]["raw_by_role"])
        again = compile_template({"template_id": "handheld"})
        self.assertEqual(again["plan"]["plan_id"], self.results["handheld"]["plan"]["plan_id"])

    def test_saved_settings_roundtrip_and_lens_cues_are_part_of_plan_identity(self):
        result = self.results["dolly_zoom_in"]
        saved = json.loads(json.dumps(result["preview"]["settings"]))
        self.assertEqual(compile_template(saved)["plan"]["plan_id"], result["plan"]["plan_id"])
        altered = copy.deepcopy(result["plan"])
        altered["camera_cues"][-1]["focal_mm"] += 1
        with self.assertRaises(ValueError):
            validate(altered)

    def test_invalid_parameters_do_not_fall_back_to_another_movement(self):
        for settings in (
            {"template_id": "missing"},
            {"template_id": []},
            {"focal_end_mm": float("nan")},
            {"subject_motion": "teleport"},
            {"angle_rad": True},
            {"rise_start": 0.9, "rise_end": 0.2},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate_settings(settings)
