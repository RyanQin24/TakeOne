"""Voice → local perception → goal-level behavior boundary."""

import unittest

from takeone.embodied import BehaviorManager
from takeone.voice.tools import VoiceTools, declarations

from tests.test_session_context import fixture_catalog
from tests.test_voice_tools import Harness, fake_preview


class EmbodiedVoiceTests(Harness):
    def setUp(self):
        super().setUp()
        self.manager = BehaviorManager(compiler=fake_preview, clock=self.voice.clock)
        self.tools = VoiceTools(
            self.voice,
            self.director,
            self.recording,
            compilers={"catalog": fixture_catalog, "compile_preview": fake_preview},
            behavior_manager=self.manager,
            clock=self.voice.clock,
        )

    def perception_body(self, detections, age=20):
        snapshot = self.voice.snapshot(self.token)["snapshot"]
        return {
            "schema_version": 1,
            "voice_session_id": self.session_id,
            "scope": snapshot["scope"],
            "generation": snapshot["generation"],
            "expires_monotonic_ns": str(self.voice.clock() + 10_000_000_000),
            "perception": {"source_frame_age_ms": age, "detections": detections},
        }

    def publish_person(self, left=0.2, right=0.5):
        result = self.tools.update_perception(
            self.perception_body([{"bbox_uv": [left, 0.1, right, 0.9], "confidence": 0.91}]),
            self.token,
        )
        self.assertTrue(result["ok"], result)
        return result["perception"]["people"][0]["track_id"]

    def goal(self, track_id, **overrides):
        value = {
            "subject_track_ids": [track_id],
            "subject_relation": "one_person",
            "camera_relation": "approach",
            "framing": "medium",
            "recording_policy": "after_settle",
            "lost_target_policy": "hold",
        }
        value.update(overrides)
        return value

    def test_perception_assigns_server_owned_track_then_prepares_goal(self):
        track_id = self.publish_person()
        self.assertEqual(track_id, "person-0001")
        result = self.call("prepare_filming_behavior", self.goal(track_id))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["code"], "behavior_prepared")
        self.assertFalse(result["physical_motion"])
        self.assertEqual(result["template_id"], "push_in")

    def test_model_cannot_start_disarmed_or_arm_itself(self):
        track_id = self.publish_person()
        prepared = self.call("prepare_filming_behavior", self.goal(track_id), "prepare-1")
        started = self.call("start_filming_behavior", {"behavior_id": prepared["behavior_id"]}, "start-1")
        self.assertFalse(started["ok"])
        self.assertEqual(started["code"], "live_director_disarmed")
        self.assertNotIn("arm_live_director", [item["name"] for item in declarations()])

    def test_stale_detection_cannot_prepare_motion(self):
        result = self.tools.update_perception(
            self.perception_body([{"bbox_uv": [0.2, 0.1, 0.5, 0.9], "confidence": 0.9}], age=2_000),
            self.token,
        )
        track_id = result["perception"]["people"][0]["track_id"]
        blocked = self.call("prepare_filming_behavior", self.goal(track_id))
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["code"], "stale_perception")

    def test_low_level_motor_vocabulary_is_absent_from_model_tool_fields(self):
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key.lower()
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)

        field_names = set(keys(declarations()))
        for forbidden in ("pwm", "uart", "serial_port", "servo_count", "joint_angle"):
            self.assertNotIn(forbidden, field_names)

    def test_adjustment_changes_only_live_framing_goal(self):
        track_id = self.publish_person()
        prepared = self.call("prepare_filming_behavior", self.goal(track_id))
        adjusted = self.call(
            "adjust_filming_behavior",
            {
                "behavior_id": prepared["behavior_id"],
                "screen_target_uv": [0.33, 0.5],
                "desired_subject_size_range": [0.25, 0.55],
            },
            request_id="adjust-1",
        )
        self.assertTrue(adjusted["ok"], adjusted)
        goal = adjusted["behavior"]["goal"]
        self.assertEqual(tuple(goal["screen_target_uv"]), (0.33, 0.5))
        self.assertEqual(tuple(goal["desired_subject_size_range"]), (0.25, 0.55))
        self.assertEqual(tuple(goal["subject_track_ids"]), (track_id,))

    def test_adjustment_rejects_low_level_or_motion_changes(self):
        track_id = self.publish_person()
        prepared = self.call("prepare_filming_behavior", self.goal(track_id))
        rejected = self.call(
            "adjust_filming_behavior",
            {"behavior_id": prepared["behavior_id"], "left_pwm": 20},
            request_id="adjust-2",
        )
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["code"], "invalid_behavior_adjustment")

    def publish_two_people(self):
        result = self.tools.update_perception(
            self.perception_body(
                [
                    {"bbox_uv": [0.08, 0.1, 0.38, 0.9], "confidence": 0.92},
                    {"bbox_uv": [0.62, 0.1, 0.92, 0.9], "confidence": 0.93},
                ]
            ),
            self.token,
        )
        return [person["track_id"] for person in result["perception"]["people"]]

    def test_multiple_people_require_explicit_semantic_selection(self):
        first, second = self.publish_two_people()
        blocked = self.call("prepare_filming_behavior", self.goal(first), "ambiguous-prepare")
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["code"], "subject_selection_required")
        selected = self.call(
            "select_subject",
            {"track_ids": [second], "semantic_reason": "the person working at the bench"},
            "select-1",
        )
        self.assertTrue(selected["ok"], selected)
        self.assertEqual(selected["selected_subject_track_ids"], [second])
        prepared = self.call("prepare_filming_behavior", self.goal(second), "selected-prepare")
        self.assertTrue(prepared["ok"], prepared)

    def test_selection_cannot_bind_unknown_track(self):
        self.publish_two_people()
        result = self.call(
            "select_subject",
            {"track_ids": ["person-9999"], "semantic_reason": "the worker"},
            "select-missing",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "target_missing")

    def test_unknown_track_is_rejected(self):
        self.publish_person()
        result = self.call("prepare_filming_behavior", self.goal("person-9999"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "target_missing")


if __name__ == "__main__":
    unittest.main()
