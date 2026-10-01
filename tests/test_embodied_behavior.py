"""Embodied Director owns goals/leases locally; Gemini never owns motor commands."""

import unittest

from takeone.embodied import BehaviorError, BehaviorManager, FilmingGoal
from takeone.perception import PerceptionState, PersonDetection, PersonTracker

PLAN_ID = "a" * 64


class Clock:
    def __init__(self):
        self.value = 1_000_000_000

    def __call__(self):
        return self.value


class FakeActuator:
    def __init__(self):
        self.started = []
        self.holds = 0
        self.stops = 0

    def start(self, plan_id, goal):
        self.started.append((plan_id, goal))
        return True

    def hold(self):
        self.holds += 1

    def stop(self):
        self.stops += 1


class FakeRecorder:
    def __init__(self):
        self.started = []
        self.stopped = []

    def start(self, plan_id, goal, behavior_id):
        take_id = f"take-{len(self.started) + 1}"
        self.started.append((take_id, plan_id, goal, behavior_id))
        return take_id

    def stop(self, take_id, reason):
        self.stopped.append((take_id, reason))


def visible_state(timestamp_ns=1_000_000_000, age_ms=10):
    tracker = PersonTracker()
    person = tracker.update(timestamp_ns, [PersonDetection((0.3, 0.2, 0.6, 0.9), 0.95)])[0]
    return PerceptionState(timestamp_ns, age_ms, (person,), (person.track_id,)), person.track_id


def goal(track_id, **changes):
    values = dict(
        subject_track_ids=(track_id,),
        subject_relation="one_person",
        camera_relation="approach",
        framing="medium",
        screen_target_uv=(0.5, 0.45),
        desired_subject_size_range=(0.25, 0.65),
        recording_policy="after_settle",
        max_duration_s=8,
        lost_target_policy="hold",
    )
    values.update(changes)
    return FilmingGoal(**values)


def compiler(settings):
    return {"plan_id": PLAN_ID, "settings": settings}


class BehaviorTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.actuator = FakeActuator()
        self.recorder = FakeRecorder()
        self.manager = BehaviorManager(
            compiler=compiler,
            actuator=self.actuator,
            recorder=self.recorder,
            clock=self.clock,
            settle_samples=3,
        )
        self.state, self.track_id = visible_state()
        self.manager.update_perception(self.state)

    def test_prepare_is_goal_level_and_does_not_actuate(self):
        result = self.manager.prepare(goal(self.track_id))
        self.assertEqual(result["plan_id"], PLAN_ID)
        self.assertEqual(result["template_id"], "push_in")
        self.assertFalse(result["physical_motion"])
        self.assertEqual(self.actuator.started, [])

    def test_missing_or_stale_perception_fails_closed(self):
        empty = BehaviorManager(compiler=compiler, clock=self.clock)
        with self.assertRaisesRegex(BehaviorError, "Inspect the current scene"):
            empty.prepare(goal(self.track_id))
        stale, track_id = visible_state(age_ms=251)
        empty.update_perception(stale)
        with self.assertRaisesRegex(BehaviorError, "too old"):
            empty.prepare(goal(track_id))

    def test_disarmed_start_never_reaches_actuator(self):
        prepared = self.manager.prepare(goal(self.track_id))
        with self.assertRaises(BehaviorError) as caught:
            self.manager.start(prepared["behavior_id"])
        self.assertEqual(caught.exception.code, "live_director_disarmed")
        self.assertEqual(self.actuator.started, [])

    def test_operator_arm_lease_allows_start_then_expires_fail_closed(self):
        prepared = self.manager.prepare(goal(self.track_id, camera_relation="follow"))
        with self.assertRaises(BehaviorError) as caught:
            self.manager.arm(lease_ms=2_000, operator_confirmed=False)
        self.assertEqual(caught.exception.code, "operator_confirmation_required")
        self.manager.arm(lease_ms=2_000, operator_confirmed=True)
        started = self.manager.start(prepared["behavior_id"])
        self.assertEqual(started["behavior"]["state"], "FOLLOWING")
        self.assertEqual(len(self.actuator.started), 1)
        self.clock.value += 2_000_000_000
        snapshot = self.manager.snapshot()
        self.assertFalse(snapshot["armed"])
        self.assertEqual(snapshot["behavior"]["state"], "HOLDING")
        self.assertEqual(self.actuator.holds, 1)

    def test_target_loss_holds_locally_without_cloud_round_trip(self):
        prepared = self.manager.prepare(goal(self.track_id, camera_relation="follow"))
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        self.manager.start(prepared["behavior_id"])
        lost = PerceptionState(self.clock(), 5, (), ())
        snapshot = self.manager.update_perception(lost)
        self.assertEqual(snapshot["behavior"]["state"], "HOLDING")
        self.assertIn("target_lost", snapshot["behavior"]["termination_reason"])
        self.assertEqual(self.actuator.holds, 1)

    def test_stop_policy_stops_locally_on_target_loss(self):
        prepared = self.manager.prepare(
            goal(self.track_id, camera_relation="follow", lost_target_policy="stop")
        )
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        self.manager.start(prepared["behavior_id"])
        snapshot = self.manager.update_perception(PerceptionState(self.clock(), 5, (), ()))
        self.assertEqual(snapshot["behavior"]["state"], "STOPPING")
        self.assertEqual(self.actuator.stops, 1)

    def test_stale_behavior_id_cannot_start_replacement(self):
        first = self.manager.prepare(goal(self.track_id))
        second = self.manager.prepare(goal(self.track_id, camera_relation="arc"))
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        with self.assertRaises(BehaviorError) as caught:
            self.manager.start(first["behavior_id"])
        self.assertEqual(caught.exception.code, "unknown_behavior")
        self.assertEqual(self.actuator.started, [])
        self.manager.start(second["behavior_id"])
        self.assertEqual(len(self.actuator.started), 1)

    def test_goal_contract_exposes_no_low_level_motor_fields(self):
        fields = set(goal(self.track_id).wire())
        forbidden = {"left_pwm", "right_pwm", "uart", "servo_counts", "joint_angles", "serial_port"}
        self.assertTrue(fields.isdisjoint(forbidden))

    def test_after_settle_recording_starts_only_after_stable_samples(self):
        prepared = self.manager.prepare(goal(self.track_id, recording_policy="after_settle"))
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        self.manager.start(prepared["behavior_id"])
        from takeone.perception import TrackedPerson

        settled_person = TrackedPerson(
            self.track_id, (0.35, 0.20, 0.65, 0.70), 0.95, (0.0, 0.0), self.clock()
        )
        settled = PerceptionState(self.clock(), 10, (settled_person,), (self.track_id,))
        first = self.manager.update_perception(settled)
        second = self.manager.update_perception(settled)
        self.assertIsNone(first["behavior"]["take_id"])
        self.assertIsNone(second["behavior"]["take_id"])
        third = self.manager.update_perception(settled)
        self.assertEqual(third["behavior"]["state"], "RECORDING")
        self.assertEqual(third["behavior"]["take_id"], "take-1")
        self.assertEqual(len(self.recorder.started), 1)

    def test_target_loss_stops_recording_before_hold(self):
        prepared = self.manager.prepare(goal(self.track_id, camera_relation="follow"))
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        self.manager.start(prepared["behavior_id"])
        from takeone.perception import TrackedPerson

        settled_person = TrackedPerson(
            self.track_id, (0.35, 0.20, 0.65, 0.70), 0.95, (0.0, 0.0), self.clock()
        )
        settled = PerceptionState(self.clock(), 10, (settled_person,), (self.track_id,))
        for _ in range(3):
            self.manager.update_perception(settled)
        lost = self.manager.update_perception(PerceptionState(self.clock(), 5, (), ()))
        self.assertEqual(lost["behavior"]["state"], "HOLDING")
        self.assertIsNone(lost["behavior"]["take_id"])
        self.assertEqual(self.recorder.stopped, [("take-1", f"target_lost:{self.track_id}")])

    def test_immediate_recording_requires_recorder_before_actuation(self):
        manager = BehaviorManager(compiler=compiler, actuator=self.actuator, clock=self.clock)
        manager.update_perception(self.state)
        prepared = manager.prepare(goal(self.track_id, recording_policy="immediate"))
        manager.arm(lease_ms=5_000, operator_confirmed=True)
        with self.assertRaises(BehaviorError) as caught:
            manager.start(prepared["behavior_id"])
        self.assertEqual(caught.exception.code, "recorder_unavailable")
        self.assertEqual(self.actuator.started, [])

    def test_immediate_recording_begins_after_motion_acceptance(self):
        prepared = self.manager.prepare(goal(self.track_id, recording_policy="immediate"))
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        started = self.manager.start(prepared["behavior_id"])
        self.assertEqual(started["behavior"]["state"], "RECORDING")
        self.assertEqual(started["behavior"]["take_id"], "take-1")
        self.assertEqual(len(self.actuator.started), 1)
        self.assertEqual(len(self.recorder.started), 1)

    def test_active_behavior_cannot_be_replaced_without_hold_or_stop(self):
        prepared = self.manager.prepare(goal(self.track_id, recording_policy="manual"))
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        self.manager.start(prepared["behavior_id"])
        with self.assertRaises(BehaviorError) as caught:
            self.manager.prepare(goal(self.track_id, camera_relation="arc", recording_policy="manual"))
        self.assertEqual(caught.exception.code, "behavior_active")
        self.manager.hold("operator_hold")
        replacement = self.manager.prepare(
            goal(self.track_id, camera_relation="arc", recording_policy="manual")
        )
        self.assertNotEqual(replacement["behavior_id"], prepared["behavior_id"])

    def test_brief_low_confidence_does_not_hold_but_persistent_loss_does(self):
        from takeone.perception import TrackedPerson

        prepared = self.manager.prepare(
            goal(self.track_id, camera_relation="follow", recording_policy="manual")
        )
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        self.manager.start(prepared["behavior_id"])

        def observed(confidence):
            person = TrackedPerson(
                self.track_id, (0.35, 0.20, 0.65, 0.70), confidence, (0.0, 0.0), self.clock()
            )
            return PerceptionState(self.clock(), 10, (person,), (self.track_id,))

        first = self.manager.update_perception(observed(0.2))
        self.assertEqual(first["behavior"]["state"], "FOLLOWING")
        self.clock.value += 400_000_000
        brief = self.manager.update_perception(observed(0.2))
        self.assertEqual(brief["behavior"]["state"], "FOLLOWING")
        self.clock.value += 101_000_000
        held = self.manager.update_perception(observed(0.2))
        self.assertEqual(held["behavior"]["state"], "HOLDING")
        self.assertEqual(held["behavior"]["termination_reason"], "target_confidence_low")

    def test_confidence_recovery_resets_grace_timer(self):
        from takeone.perception import TrackedPerson

        prepared = self.manager.prepare(
            goal(self.track_id, camera_relation="follow", recording_policy="manual")
        )
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        self.manager.start(prepared["behavior_id"])

        def observed(confidence):
            person = TrackedPerson(
                self.track_id, (0.35, 0.20, 0.65, 0.70), confidence, (0.0, 0.0), self.clock()
            )
            return PerceptionState(self.clock(), 10, (person,), (self.track_id,))

        self.manager.update_perception(observed(0.2))
        self.clock.value += 400_000_000
        self.manager.update_perception(observed(0.9))
        self.clock.value += 400_000_000
        recovered = self.manager.update_perception(observed(0.2))
        self.assertEqual(recovered["behavior"]["state"], "FOLLOWING")


if __name__ == "__main__":
    unittest.main()
