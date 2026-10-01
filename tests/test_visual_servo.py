"""Fast local image-space servo intent, independent of Gemini latency."""

import unittest

from takeone.embodied import FilmingGoal, VisualServoController
from takeone.perception import PerceptionState, TrackedPerson


def person(track_id="person-0001", box=(0.35, 0.2, 0.65, 0.8), confidence=0.9):
    return TrackedPerson(track_id, box, confidence, (0.0, 0.0), 1_000_000_000)


def state(*people, age=20):
    return PerceptionState(1_000_000_000, age, tuple(people))


def goal(track_ids=("person-0001",), relation="follow", **kwargs):
    return FilmingGoal(
        subject_track_ids=track_ids,
        subject_relation="one_person" if len(track_ids) == 1 else "group",
        camera_relation=relation,
        framing="medium",
        **kwargs,
    )


class VisualServoTests(unittest.TestCase):
    def setUp(self):
        self.servo = VisualServoController()

    def test_centered_correct_size_is_settled(self):
        intent = self.servo.intent(goal(), state(person()))
        self.assertEqual(intent.range_action, "hold")
        self.assertAlmostEqual(intent.aim_error_uv[0], 0.0)
        self.assertAlmostEqual(intent.aim_error_uv[1], 0.0)
        self.assertTrue(intent.settled)

    def test_small_subject_requests_approach(self):
        tiny = person(box=(0.45, 0.42, 0.55, 0.58))
        intent = self.servo.intent(goal(relation="follow"), state(tiny))
        self.assertEqual(intent.range_action, "approach")
        self.assertGreater(intent.range_strength, 0)
        self.assertFalse(intent.settled)

    def test_large_subject_requests_retreat(self):
        large = person(box=(0.1, 0.02, 0.9, 0.98))
        intent = self.servo.intent(goal(relation="follow"), state(large))
        self.assertEqual(intent.range_action, "retreat")
        self.assertGreater(intent.range_strength, 0)

    def test_approach_goal_never_silently_reverses(self):
        large = person(box=(0.1, 0.02, 0.9, 0.98))
        intent = self.servo.intent(goal(relation="approach"), state(large))
        self.assertEqual(intent.range_action, "hold")
        self.assertEqual(intent.range_strength, 0)

    def test_hold_goal_only_reframes_not_range(self):
        tiny = person(box=(0.05, 0.1, 0.2, 0.3))
        intent = self.servo.intent(goal(relation="hold"), state(tiny))
        self.assertEqual(intent.range_action, "hold")
        self.assertGreater(abs(intent.aim_error_uv[0]), self.servo.aim_deadband)
        self.assertFalse(intent.settled)

    def test_group_uses_union_box_and_shared_center(self):
        left = person("person-0001", (0.15, 0.2, 0.35, 0.75), 0.9)
        right = person("person-0002", (0.65, 0.25, 0.85, 0.8), 0.8)
        intent = self.servo.intent(
            goal(("person-0001", "person-0002"), relation="follow"), state(left, right)
        )
        self.assertAlmostEqual(intent.aim_error_uv[0], 0.0)
        self.assertAlmostEqual(intent.observed_subject_height, 0.6)
        self.assertEqual(intent.confidence, 0.8)

    def test_low_confidence_never_reports_settled(self):
        weak = person(confidence=0.2)
        intent = self.servo.intent(goal(), state(weak))
        self.assertFalse(intent.settled)
        self.assertEqual(intent.confidence, 0.2)

    def test_missing_selected_track_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not fully visible"):
            self.servo.intent(goal(("person-0002",)), state(person("person-0001")))


if __name__ == "__main__":
    unittest.main()
