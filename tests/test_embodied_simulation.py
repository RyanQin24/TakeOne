"""Closed-loop acceptance fixtures for the embodied AI Director."""

import math
import unittest

from takeone.embodied import (
    BehaviorManager,
    FilmingGoal,
    SimulatedSubject,
    SimulationBehaviorAdapter,
)

PLAN_ID = "b" * 64


def compiler(settings):
    return {"plan_id": PLAN_ID, "settings": settings}


class FakeRecorder:
    def __init__(self):
        self.started = []
        self.stopped = []

    def start(self, plan_id, goal, behavior_id):
        take_id = f"take-{len(self.started) + 1}"
        self.started.append((take_id, plan_id, behavior_id, goal.camera_relation))
        return take_id

    def stop(self, take_id, reason):
        self.stopped.append((take_id, reason))


class Clock:
    def __init__(self):
        self.value = 1_000_000_000

    def __call__(self):
        return self.value

    def step(self, ms=50):
        self.value += ms * 1_000_000


def single_goal(track_id, relation="approach", recording_policy="after_settle"):
    return FilmingGoal(
        subject_track_ids=(track_id,),
        subject_relation="one_person",
        camera_relation=relation,
        framing="medium",
        screen_target_uv=(0.5, 0.5),
        desired_subject_size_range=(0.36, 0.52),
        recording_policy=recording_policy,
        max_duration_s=12,
        lost_target_policy="hold",
    )


def group_goal(track_ids):
    return FilmingGoal(
        subject_track_ids=tuple(track_ids),
        subject_relation="group",
        camera_relation="retreat",
        framing="medium",
        screen_target_uv=(0.5, 0.5),
        desired_subject_size_range=(0.30, 0.50),
        recording_policy="after_settle",
        max_duration_s=12,
        lost_target_policy="hold",
    )


class EmbodiedSimulationTests(unittest.TestCase):
    def run_until_recording(self, manager, simulator, clock, limit=240):
        latest = None
        for _ in range(limit):
            clock.step()
            latest = manager.update_perception(simulator.observe())
            if latest["behavior"]["state"] == "RECORDING":
                return latest
        self.fail(f"behavior did not reach recording; latest={latest}")

    def test_come_closer_converges_and_records(self):
        clock = Clock()
        simulator = SimulationBehaviorAdapter(
            [SimulatedSubject("person-0001", lateral=0.35)], range_m=4.0, clock=clock
        )
        recorder = FakeRecorder()
        manager = BehaviorManager(
            compiler=compiler,
            actuator=simulator,
            recorder=recorder,
            clock=clock,
            settle_samples=3,
        )
        manager.update_perception(simulator.observe())
        prepared = manager.prepare(single_goal("person-0001", "approach"))
        manager.arm(lease_ms=120_000, operator_confirmed=True)
        manager.start(prepared["behavior_id"])
        start_range = simulator.range_m
        finished = self.run_until_recording(manager, simulator, clock)
        self.assertLess(simulator.range_m, start_range - 0.5)
        self.assertEqual(finished["behavior"]["take_id"], "take-1")
        self.assertGreater(simulator.updates, 3)
        self.assertAlmostEqual(finished["servo"]["aim_error_uv"][0], 0.0, delta=0.05)

    def test_get_both_of_us_increases_standoff_and_records_group(self):
        clock = Clock()
        simulator = SimulationBehaviorAdapter(
            [SimulatedSubject("person-0001", lateral=-0.26), SimulatedSubject("person-0002", lateral=0.26)],
            range_m=1.35,
            clock=clock,
        )
        recorder = FakeRecorder()
        manager = BehaviorManager(
            compiler=compiler,
            actuator=simulator,
            recorder=recorder,
            clock=clock,
            settle_samples=3,
        )
        manager.update_perception(simulator.observe())
        manager.select_subject(("person-0001", "person-0002"), "the two people the user called us")
        prepared = manager.prepare(group_goal(("person-0001", "person-0002")))
        manager.arm(lease_ms=120_000, operator_confirmed=True)
        manager.start(prepared["behavior_id"])
        start_range = simulator.range_m
        finished = self.run_until_recording(manager, simulator, clock)
        self.assertGreater(simulator.range_m, start_range + 0.25)
        self.assertEqual(finished["behavior"]["goal"]["subject_relation"], "group")
        self.assertEqual(finished["behavior"]["take_id"], "take-1")

    def test_follow_me_uses_local_reframe_as_subject_moves(self):
        clock = Clock()
        simulator = SimulationBehaviorAdapter(
            [SimulatedSubject("person-0001", lateral=0.0)], range_m=2.2, clock=clock
        )
        recorder = FakeRecorder()
        manager = BehaviorManager(
            compiler=compiler,
            actuator=simulator,
            recorder=recorder,
            clock=clock,
            settle_samples=3,
        )
        manager.update_perception(simulator.observe())
        prepared = manager.prepare(single_goal("person-0001", "follow", recording_policy="manual"))
        manager.arm(lease_ms=120_000, operator_confirmed=True)
        manager.start(prepared["behavior_id"])
        max_error = 0.0
        for step in range(60):
            simulator.move_subject("person-0001", lateral=0.55 * math.sin(step / 12))
            clock.step()
            snapshot = manager.update_perception(simulator.observe())
            max_error = max(max_error, abs(snapshot["servo"]["aim_error_uv"][0]))
        self.assertGreater(simulator.updates, 40)
        self.assertLess(abs(snapshot["servo"]["aim_error_uv"][0]), 0.08)
        self.assertLess(max_error, 0.3)
        self.assertNotAlmostEqual(simulator.aim_uv[0], 0.5, delta=0.02)

    def test_target_loss_stops_local_simulation_and_recording(self):
        clock = Clock()
        simulator = SimulationBehaviorAdapter([SimulatedSubject("person-0001")], range_m=2.0, clock=clock)
        recorder = FakeRecorder()
        manager = BehaviorManager(
            compiler=compiler,
            actuator=simulator,
            recorder=recorder,
            clock=clock,
            settle_samples=1,
        )
        manager.update_perception(simulator.observe())
        prepared = manager.prepare(single_goal("person-0001", "follow", recording_policy="immediate"))
        manager.arm(lease_ms=120_000, operator_confirmed=True)
        started = manager.start(prepared["behavior_id"])
        self.assertEqual(started["behavior"]["state"], "RECORDING")
        simulator.subjects.clear()
        clock.step()
        lost = manager.update_perception(simulator.observe())
        self.assertEqual(lost["behavior"]["state"], "HOLDING")
        self.assertEqual(simulator.holds, 1)
        self.assertEqual(recorder.stopped[0][0], "take-1")


if __name__ == "__main__":
    unittest.main()
