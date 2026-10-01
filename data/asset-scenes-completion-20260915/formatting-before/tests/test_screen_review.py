"""Adversarial authored screen requirements against achieved optical samples."""

import copy
import math
import unittest

from scipy.spatial.transform import Rotation

from takeone.previs.screen_review import review_screen


def contract(**changes):
    return dict(kind="actor", target_id="visitor", region="face", start_at=0, end_at=1,
                center_uv=[.5, .5], tolerance_uv=[1, 1], height_range=[0, 1],
                min_visible_s=0, allow_occlusion=False, allow_crop=False,
                allowed_foreground_actor_ids=[]) | changes


def fixture():
    shot = dict(actor_id="visitor", shot_id="s", start_ms=0, end_ms=4000,
                design=dict(screen_targets=[contract()]))
    camera = dict(pos=[0, -3, 1.59], quat=Rotation.from_euler("x", -math.pi/2).as_quat().tolist())
    frames = [dict(time_s=t, camera=copy.deepcopy(camera), focal_mm=24,
                   actor=dict(position_m=[0, 0, 0], heading_rad=-math.pi/2)) for t in (2, 3, 4, 5, 6)]
    preview = dict(orbit_start_s=2, orbit_duration_s=4, frames=frames)
    return shot, dict(subject_height_m=1.72), dict(space_id="room", objects=[], cast=[]), dict(position_m=[0, 0]), preview


def codes(report):
    return {i["code"] for i in report["issues"]}


def wall():
    return dict(object_id="wall", asset_id="wall", position_m=[0, -1.5, 1.5],
                size_m=[.6, .1, 1], yaw_rad=0)


class ScreenReviewTests(unittest.TestCase):
    def test_body_is_contained_but_too_small(self):
        values = fixture()
        values[0]["design"]["screen_targets"] = [contract(region="body", height_range=[.85, 1])]
        for frame in values[4]["frames"]:
            frame["camera"]["pos"][2] = .86
        result = review_screen(*values)
        self.assertIn("screen_subject_too_small", codes(result))
        self.assertNotIn("screen_region_cropped", codes(result))

    def test_face_hidden_behind_scene_object(self):
        values = fixture()
        values[2]["objects"] = [wall()]
        result = review_screen(*values)
        self.assertIn("screen_target_occluded", codes(result))
        self.assertNotIn("screen_region_cropped", codes(result))

    def test_reveal_at_final_instant_does_not_supply_dwell(self):
        values = fixture()
        values[2]["objects"] = [wall()]
        values[0]["design"]["screen_targets"] = [contract(allow_occlusion=True, min_visible_s=1)]
        values[4]["frames"][-1]["actor"]["position_m"][0] = 1.5
        result = review_screen(*values)
        self.assertIn("reveal_dwell_too_short", codes(result))
        self.assertEqual(result["checks"][0]["longest_sampled_visible_s"], 0)

    def test_unwanted_third_person_at_edge_is_distinct_from_occlusion(self):
        values = fixture()
        values[2]["cast"] = [dict(actor_id="third", offset_m=[1.8, 0, 0], facing_rad=0, motion="hold")]
        self.assertIn("unwanted_actor_intrusion", codes(review_screen(*values)))
        values[0]["design"]["screen_targets"][0]["allowed_foreground_actor_ids"] = ["third"]
        self.assertNotIn("unwanted_actor_intrusion", codes(review_screen(*values)))

    def test_intentional_occlusion_exception_remains_allowed(self):
        values = fixture()
        values[2]["objects"] = [wall()]
        values[0]["design"]["screen_targets"][0]["allow_occlusion"] = True
        self.assertEqual(codes(review_screen(*values)), set())

    def test_open_doorway_does_not_use_a_solid_box_across_its_aperture(self):
        values = fixture()
        values[2]["objects"] = [dict(object_id="door", asset_id="doorway", position_m=[0,-1.5,1.5],
                                    size_m=[2, .2, 3], yaw_rad=0)]
        self.assertNotIn("screen_target_occluded", codes(review_screen(*values)))

    def test_source_tail_does_not_supply_missing_edit_dwell(self):
        values = fixture()
        values[0]["end_ms"] = 2000
        values[0]["design"]["screen_targets"][0]["min_visible_s"] = 3
        result = review_screen(*values)
        self.assertIn("reveal_dwell_too_short", codes(result))
        self.assertEqual(result["checks"][0]["longest_sampled_visible_s"], 2)

    def test_authored_center_and_size_are_checked_without_lens_changes(self):
        values = fixture()
        values[0]["design"]["screen_targets"][0].update(center_uv=[.2, .5], tolerance_uv=[.02, 1])
        original = copy.deepcopy(values)
        self.assertIn("screen_position_mismatch", codes(review_screen(*values)))
        self.assertEqual(values, original)

    def test_missing_authored_interval_reports_no_evidence(self):
        values = fixture()
        values[0]["end_ms"] = 1000
        values[0]["design"]["screen_targets"][0].update(start_at=.75, end_at=1)
        self.assertIn("screen_evidence_missing", codes(review_screen(*values)))

    def test_no_explicit_contract_preserves_legacy_review(self):
        values = fixture()
        values[0]["design"] = {}
        self.assertIsNone(review_screen(*values))
