"""Attention targets must agree with the head direction used by the renderer."""

import copy
import math
import unittest

from takeone.director.performers import validate_links
from takeone.previs.performers import HEAD_RATIO

from tests.test_performers import fixture, poses


def point_key(at, position):
    return dict(at=at, ease="linear", kind="point", target_id="", point_m=position)


def point_track(first, last):
    value = fixture()
    track = value["document"]["scenes"][0]["shots"][0]["performers"][0]
    track["body_heading_rad"] = [dict(at=t, value=0, ease="linear") for t in (0, 1)]
    track["look_at"] = [point_key(0, first), point_key(1, last)]
    return value, track["actor_id"]


class AttentionGeometryTests(unittest.TestCase):
    def test_transition_aims_at_the_reported_interpolated_target(self):
        head = HEAD_RATIO * 1.72
        value, actor = point_track([0.1, 1, head + 0.2], [3, 0.2, head + 1.5])
        state = poses(value)[actor]
        target = state["look_target_m"]
        self.assertAlmostEqual(state["gaze_yaw_rad"], math.atan2(target[1], target[0]))
        self.assertAlmostEqual(state["gaze_pitch_rad"],
                               math.atan2(target[2] - head, math.hypot(*target[:2])))
        self.assertLess(state["attention_error_rad"], 1e-7)

    def test_coincident_target_is_unverified_not_a_fabricated_look(self):
        target = [0, 0, HEAD_RATIO * 1.72]
        value, actor = point_track(target, target)
        state = poses(value)[actor]
        self.assertIn("coincides", state["attention_unavailable"])
        self.assertNotIn("attention_error_rad", state)

    def test_range_error_is_the_angle_between_desired_and_actual_head_vectors(self):
        head = HEAD_RATIO * 1.72
        value, actor = point_track([-1, 1, head + 2], [-1, 1, head + 2])
        state = poses(value)[actor]
        yaw, pitch = state["gaze_yaw_rad"], state["gaze_pitch_rad"]
        actual = [math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)]
        target = [-1, 1, 2]
        dot = sum(a * b for a, b in zip(actual, target)) / math.sqrt(6)
        self.assertAlmostEqual(state["attention_error_rad"], math.acos(dot))

    def test_shared_capture_cannot_add_or_remove_tracks_between_clips(self):
        for empty_index in (0, 1):
            value = fixture()
            scene = value["document"]["scenes"][0]
            first = scene["shots"][0]
            second = copy.deepcopy(first)
            second.update(shot_id="second", start_ms=6000, end_ms=12000)
            first["capture"] = dict(take_id="continuous", in_s=0)
            second["capture"] = dict(take_id="continuous", in_s=6)
            scene["shots"].append(second)
            scene["shots"][empty_index]["performers"] = []
            with self.subTest(empty_index=empty_index):
                with self.assertRaisesRegex(ValueError, "Shared-take"):
                    validate_links(value["document"])

    def test_object_target_uses_its_scene_position_not_the_unused_point_field(self):
        value = fixture()
        scene = value["document"]["scenes"][0]
        scene["objects"] = [dict(object_id="detail", position_m=[2.5, -2.8, 1.2])]
        value["document"]["marks"][0]["position_m"] = [2, -3]
        track = scene["shots"][0]["performers"][0]
        track["look_at"] = [dict(at=t, ease="linear", kind="object", target_id="detail",
                                point_m=[99, 99, 99]) for t in (0, 1)]
        state = poses(value)[track["actor_id"]]
        for actual, expected in zip(state["look_target_m"], [0.5, 0.2, 1.2]):
            self.assertAlmostEqual(actual, expected)

    def test_attention_sampling_does_not_change_authored_data(self):
        value = fixture()
        original = copy.deepcopy(value)
        poses(value)
        self.assertEqual(value, original)


if __name__ == "__main__":
    unittest.main()
