"""Adversarial actor/cart/phone overlap checks on known analytic trajectories."""

import copy
import math
import unittest

from scipy.spatial.transform import Rotation
from takeone.director.motion_contract import defaults, validate_links
from takeone.previs.capture import window
from takeone.previs.travel_review import review_travel


def fixture(actor=True, cart=True, arm=True, duration=6):
    frames = []
    for i in range(round((duration + 2) / 0.08) + 1):
        t = i * 0.08
        u = max(0, min(duration, t - 2))
        x = 0.14 * u if cart else 0
        ax = 0.14 * u if actor else 0
        h = 1.45 + 0.02 * u if arm else 1.45
        frames.append(
            dict(
                time_s=t,
                q=[x, -2.3, 0] + [0.02 * u if arm else 0] * 5 + [0] * 5,
                axle_m=[x + 0.27, -2.3],
                camera=dict(pos=[x, -1.9, h], quat=Rotation.from_euler("x", -math.pi / 2).as_quat().tolist()),
                actor=dict(position_m=[ax, 0, 0], heading_rad=0),
                face=[ax, 0, 1.59],
                focal_mm=30,
            )
        )
    preview = dict(
        frames=frames, orbit_start_s=2, orbit_duration_s=duration, duration_s=duration + 2, summary={}
    )
    shot = dict(
        shot_id="joint",
        actor_id="visitor",
        start_ms=0,
        end_ms=duration * 1000,
        motion_requirements=defaults()
        | dict(
            priority="required",
            actor_travel_m=0.5,
            cart_travel_m=0.5,
            arm_translation_m=0.05,
            simultaneous_s=2,
        ),
    )
    return shot, {}, preview


def codes(result):
    return {i["code"] for i in result["issues"]}


class TravelReviewTests(unittest.TestCase):
    def test_joint_tracking_passes_without_screen_drift(self):
        result = review_travel(*fixture())
        self.assertEqual(result["status"], "reviewable")
        self.assertGreaterEqual(result["metrics"]["longest_simultaneous_s"], 5)
        self.assertAlmostEqual(result["metrics"]["cart"]["net_m"], 0.84)

    def test_actor_only_cannot_pass(self):
        result = review_travel(*fixture(cart=False, arm=False))
        self.assertIn("simultaneous_s_unmet", codes(result))

    def test_robot_only_cannot_pass(self):
        result = review_travel(*fixture(actor=False))
        self.assertIn("simultaneous_s_unmet", codes(result))

    def test_walking_in_place_is_not_locomotion(self):
        values = fixture(actor=False)
        for f in values[2]["frames"]:
            f["actor"].update(walking=True, phase_rad=f["time_s"] * 6)
        self.assertIn("actor_travel_unmet", codes(review_travel(*values)))

    def test_nonoverlapping_motion_does_not_pass(self):
        values = fixture()
        for f in values[2]["frames"]:
            u = max(0, f["time_s"] - 2)
            f["actor"]["position_m"][0] = 0.3 * min(3, u)
            f["q"][0] = max(0, u - 3) * 0.3
            f["axle_m"][0] = f["q"][0] + 0.27
            f["camera"]["pos"][0] = f["q"][0]
        self.assertIn("simultaneous_s_unmet", codes(review_travel(*values)))

    def test_setup_motion_does_not_count(self):
        values = fixture(actor=False, cart=False, arm=False)
        for f in values[2]["frames"]:
            if f["time_s"] < 2:
                f["actor"]["position_m"][0] = f["time_s"]
                f["q"][0] = f["time_s"]
                f["axle_m"][0] = f["time_s"]
        result = review_travel(*values)
        self.assertEqual(result["metrics"]["longest_simultaneous_s"], 0)
        self.assertEqual(result["metrics"]["cart"]["path_m"], 0)

    def test_zoom_does_not_supply_camera_translation(self):
        values = fixture(actor=False, cart=False, arm=False)
        values[0]["motion_requirements"] = defaults() | dict(priority="required", camera_travel_m=0.5)
        for f in values[2]["frames"]:
            f["focal_mm"] = 24 + f["time_s"] * 10
        self.assertIn("camera_travel_unmet", codes(review_travel(*values)))

    def test_actor_approach_does_not_supply_camera_push(self):
        values = fixture(cart=False, arm=False)
        values[0]["motion_requirements"] = defaults() | dict(
            priority="required", direction="approach", signed_progress_m=0.5
        )
        self.assertIn("camera_direction_unmet", codes(review_travel(*values)))

    def test_wrong_camera_direction_is_reported(self):
        values = fixture(actor=False, arm=False)
        values[0]["motion_requirements"] = defaults() | dict(
            priority="required", direction="approach", signed_progress_m=0.5
        )
        for f in values[2]["frames"]:
            f["camera"]["pos"][1] = -2 - max(0, f["time_s"] - 2) * 0.15
        self.assertIn("camera_direction_unmet", codes(review_travel(*values)))

    def test_arm_jitter_cannot_supply_required_overlap(self):
        values = fixture(arm=False)
        for f in values[2]["frames"]:
            f["camera"]["pos"][2] += 0.001 * math.sin(f["time_s"] * 70)
        self.assertIn("simultaneous_s_unmet", codes(review_travel(*values)))

    def test_scene_reposition_metadata_does_not_fake_motion(self):
        values = fixture(actor=False, cart=False, arm=False)
        for f in values[2]["frames"]:
            f["world_offset"] = [f["time_s"], 0, 0]
        self.assertEqual(review_travel(*values)["metrics"]["cart"]["path_m"], 0)

    def test_full_circle_has_motion_despite_zero_net_displacement(self):
        values = fixture(actor=False, arm=False)
        values[0]["motion_requirements"] = defaults() | dict(
            priority="required", camera_travel_m=10, direction="orbit_ccw", orbit_rad=6
        )
        for f in values[2]["frames"]:
            a = max(0, f["time_s"] - 2) / 6 * math.tau
            f["camera"]["pos"] = [2 * math.cos(a), 2 * math.sin(a), 1.59]
        result = review_travel(*values)
        self.assertEqual(result["status"], "reviewable")
        self.assertLess(result["metrics"]["optical"]["net_m"], 1e-8)
        self.assertGreater(result["metrics"]["optical"]["path_m"], 12)

    def test_unused_source_tail_cannot_satisfy_edit(self):
        values = fixture()
        values[0]["end_ms"] = 1000
        self.assertIn("simultaneous_s_unmet", codes(review_travel(*values)))

    def test_shared_take_reports_original_source_offsets(self):
        shot, settings, preview = fixture(duration=8)
        shot["end_ms"] = 4000
        preview = window(preview, 4, 4, False)
        result = review_travel(shot, settings, preview)
        self.assertEqual(result["source_interval_s"], [4, 8])
        self.assertGreaterEqual(result["source_overlap_intervals_s"][0][0], 4)

    def test_missing_camera_evidence_is_unverified(self):
        values = fixture()
        del values[2]["frames"][-1]["camera"]
        self.assertEqual(review_travel(*values)["status"], "unverified")

    def test_sparse_evidence_cannot_prove_overlap(self):
        values = fixture()
        values[2]["frames"] = values[2]["frames"][::10]
        self.assertEqual(review_travel(*values)["status"], "unverified")

    def test_preferred_failure_is_advisory_not_silent_repair(self):
        values = fixture(cart=False)
        values[0]["motion_requirements"]["priority"] = "preferred"
        before = copy.deepcopy(values)
        result = review_travel(*values)
        self.assertEqual(result["status"], "preference_notes")
        self.assertEqual(before, values)

    def test_static_camera_may_have_a_moving_actor(self):
        values = fixture(cart=False, arm=False)
        values[0]["motion_requirements"] = defaults() | dict(
            priority="intentionally_static", actor_travel_m=0.5
        )
        validate_links(dict(scenes=[dict(shots=[values[0]])]))
        self.assertEqual(review_travel(*values)["status"], "reviewable")

    def test_static_camera_contract_detects_unwanted_motion(self):
        values = fixture()
        values[0]["motion_requirements"] = defaults() | dict(priority="intentionally_static")
        self.assertIn("intentional_camera_hold_not_realized", codes(review_travel(*values)))

    def test_failed_position_target_does_not_move_achieved_camera(self):
        values = fixture()
        for f in values[2]["frames"]:
            f["requested_camera_position_m"] = [20, 20, 1.5]
        before = copy.deepcopy(values)
        self.assertIn("camera_path_not_achieved", codes(review_travel(*values)))
        self.assertEqual(before, values)


if __name__ == "__main__":
    unittest.main()
