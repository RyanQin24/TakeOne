"""Observe mode: aim evaluation and recording without motion authority.

Recording is not motion. The rig is aimed by a human hand or by the separate,
already-supervised robot playback path; TakeOne only watches the witness camera
and rolls the phone. These tests pin that observing never touches the actuator,
never arms anything, and never reports physical motion.
"""

import unittest

from takeone.embodied import BehaviorError, BehaviorManager, FilmingGoal
from takeone.perception import PerceptionState, PersonDetection, PersonTracker

PLAN_ID = "b" * 64


class Clock:
    def __init__(self):
        self.value = 1_000_000_000

    def __call__(self):
        return self.value


class RecordingActuator:
    """Records every call so a test can prove none happened."""

    def __init__(self):
        self.calls = []

    def start(self, plan_id, goal):
        self.calls.append(("start", plan_id))
        return True

    def update(self, intent):
        self.calls.append(("update", intent))
        return True

    def hold(self):
        self.calls.append(("hold", None))

    def stop(self):
        self.calls.append(("stop", None))


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


def compiler(settings):
    return {"plan_id": PLAN_ID, "settings": settings}


def settled_state(track_id=None, timestamp_ns=1_000_000_000, age_ms=10, tracker=None):
    """A person centred in frame at a height inside the default size range."""
    tracker = tracker or PersonTracker()
    person = tracker.update(timestamp_ns, [PersonDetection((0.35, 0.3, 0.65, 0.7), 0.95)])[0]
    return PerceptionState(timestamp_ns, age_ms, (person,), (person.track_id,)), person.track_id, tracker


def goal(track_id, **changes):
    values = dict(
        subject_track_ids=(track_id,),
        subject_relation="one_person",
        camera_relation="approach",
        framing="medium",
        screen_target_uv=(0.5, 0.5),
        desired_subject_size_range=(0.2, 0.7),
        recording_policy="after_settle",
        max_duration_s=8,
        lost_target_policy="hold",
    )
    values.update(changes)
    return FilmingGoal(**values)


class ObserveTests(unittest.TestCase):
    def test_watchdog_stops_phone_when_browser_frames_disappear(self):
        self.manager.observe(self.prepared["behavior_id"], motion_source="operator_manual")
        for _ in range(3):
            self.manager.update_perception(self.state)
        self.assertEqual(len(self.recorder.started), 1)
        self.clock.value += 300_000_000
        self.manager.tick()
        snapshot = self.manager.snapshot()
        self.assertEqual(snapshot["behavior"]["state"], "HOLDING")
        self.assertEqual(snapshot["behavior"]["termination_reason"], "stale_perception")
        self.assertEqual(len(self.recorder.stopped), 1)
        self.assertNotIn("start", [call[0] for call in self.actuator.calls])

    def test_watchdog_enforces_observation_duration(self):
        self.manager.observe(self.prepared["behavior_id"], motion_source="operator_manual")
        self.clock.value += 8_000_000_000
        self.manager.tick()
        self.assertEqual(self.manager.snapshot()["behavior"]["termination_reason"], "max_duration_reached")

    def setUp(self):
        self.clock = Clock()
        self.actuator = RecordingActuator()
        self.recorder = FakeRecorder()
        self.manager = BehaviorManager(
            compiler=compiler,
            actuator=self.actuator,
            recorder=self.recorder,
            clock=self.clock,
            settle_samples=3,
        )
        self.state, self.track_id, self.tracker = settled_state()
        self.manager.update_perception(self.state)
        self.prepared = self.manager.prepare(goal(self.track_id))

    # 1
    def test_unknown_behavior_is_refused(self):
        with self.assertRaises(BehaviorError) as caught:
            self.manager.observe("not-a-behavior", motion_source="operator_manual")
        self.assertEqual(caught.exception.code, "unknown_behavior")

    # 2
    def test_observing_while_armed_is_a_motion_authority_conflict(self):
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        with self.assertRaises(BehaviorError) as caught:
            self.manager.observe(self.prepared["behavior_id"], motion_source="operator_manual")
        self.assertEqual(caught.exception.code, "motion_authority_conflict")
        self.assertIn("Disarm", str(caught.exception))

    # 3
    def test_unknown_motion_source_names_the_field_and_its_values(self):
        with self.assertRaises(BehaviorError) as caught:
            self.manager.observe(self.prepared["behavior_id"], motion_source="magic")
        self.assertEqual(caught.exception.code, "invalid_motion_source")
        message = str(caught.exception)
        self.assertIn("motion_source", message)
        self.assertIn("operator_manual", message)
        self.assertIn("supervised_robot_path", message)

    # 4
    def test_a_recording_policy_requires_a_recorder(self):
        manager = BehaviorManager(compiler=compiler, actuator=self.actuator, clock=self.clock)
        manager.update_perception(self.state)
        prepared = manager.prepare(goal(self.track_id))
        with self.assertRaises(BehaviorError) as caught:
            manager.observe(prepared["behavior_id"], motion_source="operator_manual")
        self.assertEqual(caught.exception.code, "recorder_unavailable")

    def test_manual_policy_observes_without_a_recorder(self):
        manager = BehaviorManager(compiler=compiler, actuator=self.actuator, clock=self.clock)
        manager.update_perception(self.state)
        prepared = manager.prepare(goal(self.track_id, recording_policy="manual"))
        snapshot = manager.observe(prepared["behavior_id"], motion_source="operator_manual")
        self.assertEqual(snapshot["motion_authority"], "observe")

    # 5
    def test_stale_perception_refuses_the_same_way_start_does(self):
        stale = PerceptionState(self.state.monotonic_timestamp_ns, 251, self.state.people, (self.track_id,))
        self.manager.update_perception(stale)
        with self.assertRaises(BehaviorError) as caught:
            self.manager.observe(self.prepared["behavior_id"], motion_source="operator_manual")
        self.assertEqual(caught.exception.code, "stale_perception")

    # 6
    def test_initial_state_uses_the_same_mapping_as_start(self):
        for relation, expected in (
            ("follow", "FOLLOWING"),
            ("lead", "FOLLOWING"),
            ("hold", "REFRAMING"),
            ("approach", "APPROACHING"),
        ):
            manager = BehaviorManager(
                compiler=compiler, recorder=FakeRecorder(), clock=self.clock, settle_samples=3
            )
            manager.update_perception(self.state)
            prepared = manager.prepare(goal(self.track_id, camera_relation=relation))
            snapshot = manager.observe(prepared["behavior_id"], motion_source="operator_manual")
            self.assertEqual(snapshot["behavior"]["state"], expected, relation)
            self.assertGreater(snapshot["behavior"]["revision"], 1)
            self.assertEqual(snapshot["settle_streak"], 0)

    # 7
    def test_observing_never_commands_the_actuator(self):
        self.manager.observe(self.prepared["behavior_id"], motion_source="operator_manual")
        for step in range(4):
            state, _, _ = settled_state(
                timestamp_ns=1_000_000_000 + (step + 1) * 50_000_000, tracker=self.tracker
            )
            self.manager.update_perception(state)
        self.assertEqual(
            [call for call, _ in self.actuator.calls],
            [],
            "an observing behavior must never start or steer an actuator",
        )
        self.assertEqual(len(self.recorder.started), 1, "settling must still roll the camera")

    def test_hold_and_stop_still_command_the_actuator(self):
        """Commanding a stop on something that is not moving is harmless;
        failing to command a stop on something that is moving is not."""
        self.manager.observe(self.prepared["behavior_id"], motion_source="supervised_robot_path")
        self.manager.hold(reason="operator_hold")
        self.assertIn("hold", [call for call, _ in self.actuator.calls])
        self.manager.observe(self.prepared["behavior_id"], motion_source="supervised_robot_path")
        self.manager.stop(reason="operator_stop")
        self.assertIn("stop", [call for call, _ in self.actuator.calls])

    # 8
    def test_immediate_policy_rolls_on_observe(self):
        manager = BehaviorManager(
            compiler=compiler, recorder=self.recorder, clock=self.clock, settle_samples=3
        )
        manager.update_perception(self.state)
        prepared = manager.prepare(goal(self.track_id, recording_policy="immediate"))
        snapshot = manager.observe(prepared["behavior_id"], motion_source="operator_manual")
        self.assertEqual(snapshot["behavior"]["state"], "RECORDING")
        self.assertEqual(len(self.recorder.started), 1)

    # 9
    def test_snapshot_reports_authority_and_never_physical_motion(self):
        idle = self.manager.snapshot()
        self.assertEqual(idle["motion_authority"], "none")
        self.assertIsNone(idle["motion_source"])
        observing = self.manager.observe(self.prepared["behavior_id"], motion_source="supervised_robot_path")
        self.assertEqual(observing["motion_authority"], "observe")
        self.assertEqual(observing["motion_source"], "supervised_robot_path")
        self.assertFalse(observing["physical_motion"])
        self.assertFalse(observing["armed"])
        self.manager.stop_observing()
        released = self.manager.snapshot()
        self.assertEqual(released["motion_authority"], "none")
        self.assertIsNone(released["motion_source"])
        self.assertFalse(released["physical_motion"])

    def test_arming_is_untouched_by_observing(self):
        self.manager.observe(self.prepared["behavior_id"], motion_source="operator_manual")
        snapshot = self.manager.snapshot()
        self.assertFalse(snapshot["armed"])
        self.assertIsNone(snapshot["arm_expires_monotonic_ns"])

    def test_started_motion_reports_motion_authority(self):
        self.manager.arm(lease_ms=5_000, operator_confirmed=True)
        snapshot = self.manager.start(self.prepared["behavior_id"])
        self.assertEqual(snapshot["motion_authority"], "motion")
        self.assertEqual(snapshot["motion_source"], "live_director")
        self.assertFalse(snapshot["physical_motion"])


if __name__ == "__main__":
    unittest.main()
