"""General pose programs and real controller contract, entirely injected/no hardware."""

import copy
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.spatial.transform import Rotation
from takeone.motion.arm import ArmRunner
from takeone.motion.arm_snapshot import capture
from takeone.motion.limits import ArmTiming, execution_limits
from takeone.planning.arm_program import ArmProgramPlan, compile_program, rehearsal_pose, target_pose
from takeone.planning.curve import JointCurve
from takeone.voice.arm_program import prepare_program
from takeone.voice.arm_rehearsal import ArmRehearsal
from takeone.voice.live_robot import TOOLS, LiveRobotTools

from tests.support.devices import SimulatedArm, VirtualClock


def segment(translation=(0, 0, -0.02), rotation=(0, 0, 0), frame="world", duration=None, target=None):
    return dict(
        translation_m=list(translation),
        rotation_rad=list(rotation),
        frame=frame,
        duration_s=duration,
        aim_target=target,
    )


def program(*segments, role="phone", questions=None):
    return dict(role=role, segments=list(segments or (segment(),)), questions=questions or [], assumptions=[])


class ProgramContractTests(unittest.TestCase):
    def test_only_vector_tool_is_advertised(self):
        names = [t["name"] for t in TOOLS]
        self.assertIn("prepare_arm_motion", names)
        self.assertNotIn("prepare_arm_adjustment", names)

    def test_continuous_signed_vector_no_action_enumeration(self):
        request = program(segment((0.0317, -0.0186, 0.022), (0.021, 0.016, -0.028)))
        original = copy.deepcopy(request)
        result = prepare_program(request)
        self.assertEqual(result["program"], original)
        self.assertEqual(request, original)
        self.assertFalse(result["executable"])

    def test_malformed_vectors_and_extra_authority_rejected(self):
        for bad in ([0, 0], [0, True, 0], [0, float("nan"), 0], [0, float("inf"), 0], [0, "1", 0]):
            value = program()
            value["segments"][0]["translation_m"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                prepare_program(value)
        value = program()
        value["operator_ready"] = True
        with self.assertRaises(ValueError):
            prepare_program(value)

    def test_ambiguous_role_frame_or_language_never_compiles(self):
        value = program(segment(frame="unspecified"), role="unspecified", questions=["Tilt which way?"])
        with patch("takeone.planning.arm_program.load_model") as loading:
            result = compile_program(value, [0] * 13, pose_source="simulated")
        loading.assert_not_called()
        self.assertEqual(result["code"], "clarification_required")
        self.assertEqual(len(result["program"]["questions"]), 3)

    def test_arbitrary_frames_match_matrix_math(self):
        r = Rotation.from_rotvec([0.3, -0.4, 0.2]).as_matrix()
        p = np.array([0.2, 0.6, 1.2])
        for frame in ("world", "chassis", "optical"):
            basis = (
                np.eye(3)
                if frame == "world"
                else r
                if frame == "optical"
                else Rotation.from_euler("z", 0.7).as_matrix()
            )
            step = segment((0.01, -0.017, 0.023), (0.021, -0.05, 0.011), frame)
            actual_p, actual_r = target_pose(p, r, 0.7, step)
            np.testing.assert_allclose(actual_p, p + basis @ step["translation_m"])
            np.testing.assert_allclose(
                actual_r, Rotation.from_rotvec(basis @ step["rotation_rad"]).as_matrix() @ r
            )

    def test_selected_person_is_never_guessed(self):
        step = segment((0, 0, 0), target="us")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            target_pose(np.zeros(3), np.eye(3), 0, step)
        with self.assertRaises(ValueError):
            target_pose(np.zeros(3), np.eye(3), 0, step, {"us": [0, 0, 0]})
        p, r = target_pose(np.zeros(3), np.eye(3), 0, step, {"us": [0, 1, 0]})
        np.testing.assert_allclose(r[:, 2], [0, 1, 0], atol=1e-9)


class ProgramPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = rehearsal_pose()
        cls.result = compile_program(program(), cls.q, pose_source="simulated")

    def test_encoded_full_path_and_rest_boundaries(self):
        result = self.result
        self.assertTrue(result["ok"], result["faults"])
        self.assertFalse(result["executable"])
        self.assertFalse(result["collision_checked"])
        self.assertGreater(len(result["frames"]), 20)
        curve = JointCurve.from_dict(result["document"]["curve"])
        self.assertTrue(curve.rest_boundaries())
        for frame in result["frames"]:
            np.testing.assert_allclose(frame["qpos"][:3], self.q[:3])
            np.testing.assert_allclose(frame["qpos"][8:], self.q[8:])
        self.assertLess(result["frames"][-1]["position_m"][2], result["frames"][0]["position_m"][2] - 0.015)

    def test_float_duration_never_duplicates_dispatch_endpoint(self):
        from takeone.planning.curve import quintic

        zero = (0.0,) * 10
        for ticks in range(1, 300):
            duration = math.nextafter(ticks * 0.04, math.inf)
            curve = JointCurve((0, duration), (quintic(zero, zero, zero, zero, zero, zero, duration),))
            plan = ArmProgramPlan(curve, 0.04)
            times = plan.dispatch_times()
            self.assertEqual(len(times), ticks + 1)
            self.assertTrue(all(b - a > 1e-9 for a, b in zip(times, times[1:])))

    def test_ordered_compound_solves_each_segment(self):
        result = compile_program(program(segment(), segment((0, 0, 0.01))), self.q, pose_source="simulated")
        self.assertTrue(result["ok"], result["faults"])
        self.assertEqual(len(result["segments"]), 2)
        curve = JointCurve.from_dict(result["document"]["curve"])
        self.assertEqual(len(curve.knots_s), 3)

    def test_explicit_too_fast_timing_is_rejected_not_silently_retimed(self):
        result = compile_program(program(segment(duration=0.04)), self.q, pose_source="simulated")
        self.assertFalse(result["ok"])
        self.assertIn("duration", result["faults"][0]["reason"])

    def test_unreachable_target_reports_failure_no_substitute(self):
        result = compile_program(program(segment((0, 0, 1))), self.q, pose_source="simulated")
        self.assertFalse(result["ok"])
        self.assertFalse(result["hardware_commands_sent"])

    def test_missing_target_rejects_entire_program(self):
        result = compile_program(
            program(segment(), segment((0, 0, 0), target="us")), self.q, pose_source="simulated"
        )
        self.assertFalse(result["ok"])
        self.assertIn("unavailable", result["faults"][-1]["reason"])

    def test_existing_feedback_controller_replays_exact_curve_in_simulation(self):
        plan = ArmProgramPlan(JointCurve.from_dict(self.result["document"]["curve"]), 0.04)
        clock = VirtualClock()
        adapter = SimulatedArm(plan.arm_at("phone", 0), clock.now)
        runner = ArmRunner(
            adapter,
            "phone",
            plan,
            execution_limits("phone", "commissioning"),
            ArmTiming.load(),
            clock=clock.now,
            sleep=clock.sleep,
        )
        runner.ready()
        runner.run(clock.now() + 0.1)
        report = runner.report()
        self.assertTrue(report["settled"])
        self.assertFalse(report["physical_tracking_verified"])
        commands = [e for e in report["events"] if e["phase"] == "command"]
        self.assertEqual(len(commands), len(plan.dispatch_times()))
        for event, t in zip(commands, plan.dispatch_times()):
            self.assertEqual(event["q_rad"], plan.arm_at("phone", t))

    def test_controller_stop_latches_and_retains_goal_without_torque_release(self):
        plan = ArmProgramPlan(JointCurve.from_dict(self.result["document"]["curve"]), 0.04)
        clock = VirtualClock()
        adapter = SimulatedArm(plan.arm_at("phone", 0), clock.now)

        def guard():
            if clock.now() > 100.4:
                raise RuntimeError("operator stop")

        runner = ArmRunner(
            adapter,
            "phone",
            plan,
            execution_limits("phone", "commissioning"),
            ArmTiming.load(),
            clock=clock.now,
            sleep=clock.sleep,
            guard=guard,
        )
        runner.ready()
        with self.assertRaisesRegex(RuntimeError, "operator stop"):
            runner.run(clock.now() + 0.1)
        runner.hold_on_fault()
        self.assertIsNotNone(runner.fault)
        self.assertTrue(adapter.connected)
        self.assertFalse(runner.settled)


class RehearsalServiceTests(unittest.TestCase):
    def test_no_automatic_hardware_capture_or_assumed_start(self):
        with patch("takeone.voice.arm_rehearsal.read_snapshot") as reader:
            service = ArmRehearsal(snapshot_reader=reader)
            result = service.prepare("owner", program())
            self.assertEqual(result["code"], "arm_pose_required")
            reader.assert_not_called()

    def test_session_isolation_expiry_close_and_failed_capture(self):
        now = [0]
        service = ArmRehearsal(
            clock=lambda: now[0], snapshot_reader=lambda: (_ for _ in ()).throw(ValueError("unplugged"))
        )
        service.set_pose("a", "simulated")
        self.assertEqual(service.prepare("b", program())["code"], "arm_pose_required")
        now[0] = 121
        with self.assertRaisesRegex(ValueError, "expired"):
            service.prepare("a", program())
        with self.assertRaisesRegex(ValueError, "unplugged"):
            service.set_pose("a", "measured_snapshot")
        self.assertEqual(service.prepare("a", program())["code"], "arm_pose_required")
        service.set_pose("a", "simulated")
        service.close("a")
        self.assertIsNone(service.review("a")["review"])


class SnapshotTests(unittest.TestCase):
    def report(self, role):
        from takeone.calibration import ArmMapping

        mapping = ArmMapping.load(role, require_motion=False)
        raw = mapping.to_raw(tuple((a + b) / 2 for a, b in mapping.safe_ranges_rad))
        return dict(
            completed=True,
            configured_calibration_matches_hardware=True,
            joints={
                name: dict(
                    registers_raw=dict(Present_Position=value, Operating_Mode=0, Phase=0, Torque_Enable=0)
                )
                for name, value in raw.items()
            },
        )

    def test_snapshot_is_actual_input_not_simulated_fallback(self):
        calls = []

        def inspect(role):
            calls.append(role)
            return self.report(role)

        result = capture(inspect=inspect)
        self.assertEqual(calls, ["phone", "light"])
        self.assertEqual(len(result["qpos"]), 13)
        self.assertEqual(result["source"], "measured_snapshot")
        self.assertFalse(result["motor_register_writes"])
        self.assertFalse(result["physical_pose_verified"])

    def test_snapshot_rejects_failed_read_calibration_or_mode(self):
        for change in ("read", "calibration", "mode"):

            def inspect(role):
                report = self.report(role)
                if role == "phone":
                    if change == "read":
                        report["completed"] = False
                    elif change == "calibration":
                        report["configured_calibration_matches_hardware"] = False
                    else:
                        next(iter(report["joints"].values()))["registers_raw"]["Operating_Mode"] = 1
                return report

            with self.subTest(change=change), self.assertRaises(ValueError):
                capture(inspect=inspect)

    def test_language_cannot_capture_encoders_or_execute(self):
        service = ArmRehearsal(snapshot_reader=lambda: self.fail("No hardware reads from language"))
        tools = LiveRobotTools(arms=service)
        self.assertEqual(
            tools.execute("prepare_arm_motion", program(), owner="a")["code"], "arm_pose_required"
        )
        for name in ("run_arm_motion", "read_arm_encoders", "enable_torque"):
            self.assertFalse(tools.execute(name, {})["ok"])

    def test_correction_clears_previous_trajectory_even_if_invalid(self):
        service = ArmRehearsal()
        service.set_pose("a", "simulated")
        service.prepare("a", program())
        self.assertIsNotNone(service.review("a")["review"])
        service.prepare("a", program(questions=["Which direction?"]))
        self.assertIsNone(service.review("a")["review"])


if __name__ == "__main__":
    unittest.main()
