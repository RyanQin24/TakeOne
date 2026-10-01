import copy
import math
import os
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from takeone.adapters.lerobot_arm import LeRobotArm
from takeone.cart.runtime import Timing
from takeone.config import provenance
from takeone.contracts import JOINTS, ArmObservation
from takeone.execution import RobotRunner
from takeone.motion.arm import ArmRunner
from takeone.motion.devices import DeviceFactory
from takeone.motion.limits import ArmTiming, preflight
from takeone.motion.plan import FRAMES, ROLES, digest, load_plan, prepare_shot
from takeone.motion.service import check_plan, execute_plan
from takeone.planning.curve import JointCurve, dispatch_times, quintic

from tests.support.coordination_clock import run_coordinated
from tests.support.devices import SimulatedArm, VirtualClock, software_limits
from tests.test_contracts import mapping, missing_originals_config


def small_plan(duration=0.4, travel=0.06):
    zeros = (0.0,) * 10
    end = (travel, 0, 0, 0, 0, 0, -travel, 0, 0, 0)
    curve = JointCurve((0.0, duration), (quintic(zeros, zeros, zeros, end, zeros, zeros, duration),))
    samples = [
        dict(time_s=t, arms=dict(phone=curve.at(t)[:5], light=curve.at(t)[5:]))
        for t in dispatch_times(duration, 0.04)
    ]
    body = dict(
        schema="takeone.robot-plan.v2",
        provenance=provenance(),
        roles=list(ROLES),
        frames=FRAMES,
        joint_order=list(JOINTS),
        joint_curve=curve.to_dict(),
        arm_period_s=0.04,
        interpolation="local_seconds_polynomial_ascending_powers",
        hardware_ready=False,
        duration_s=duration,
        samples=samples,
        cart_schedule=[
            dict(time_s=0, commands=[0.04, 0.04], wire="0.04,0.04\n"),
            dict(time_s=duration, commands=[0, 0], wire="0.00,0.00\n"),
        ],
    )
    return load_plan(body | {"plan_id": digest(body)})


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from takeone.planning.compiler import compile_shot

        cls.shot = compile_shot()
        cls.plan = prepare_shot(cls.shot)

    def test_every_preview_joint_and_timestamp_survives_preparation(self):
        plan, shot = self.plan, self.shot
        for frame in shot["frames"]:
            # Preview frames are the union of render and motor-dispatch samples,
            # not a uniformly spaced list. Preserve each frame's explicit time.
            t = frame["time_s"]
            for actual, expected in zip(plan.arm_at("phone", t), frame["q"][3:8]):
                self.assertAlmostEqual(actual, expected, places=12)
            for actual, expected in zip(plan.arm_at("light", t), frame["q"][8:13]):
                self.assertAlmostEqual(actual, expected, places=12)
        self.assertEqual(
            [s["wire"] for s in plan.to_dict()["cart_schedule"]], [s["wire"] for s in shot["motorCommands"]]
        )

    def test_joint_interpolation_is_not_a_new_ik_solution(self):
        plan = small_plan()
        self.assertAlmostEqual(
            plan.arm_at("phone", 0.1)[0], 0.06 * (10 * 0.25**3 - 15 * 0.25**4 + 6 * 0.25**5)
        )
        self.assertAlmostEqual(
            plan.arm_at("light", 0.3)[1], -0.06 * (10 * 0.75**3 - 15 * 0.75**4 + 6 * 0.75**5)
        )
        self.assertEqual(plan.arm_at("phone", -1), plan.phone[0])
        self.assertEqual(plan.arm_at("phone", 99), plan.phone[-1])

    def test_edit_stale_hash_and_missing_role_are_rejected(self):
        for change in ("target", "provenance", "role", "time", "nan"):
            document = small_plan().to_dict()
            if change == "target":
                document["samples"][1]["arms"]["phone"][0] += 1
            elif change == "provenance":
                document["provenance"] = {}
            elif change == "role":
                document["samples"][0]["arms"].pop("light")
            elif change == "time":
                document["samples"][1]["time_s"] = 0
            else:
                document["samples"][0]["arms"]["phone"][0] = math.nan
            if change != "target" and change != "nan":
                document["plan_id"] = digest({k: v for k, v in document.items() if k != "plan_id"})
            with self.assertRaises(ValueError):
                load_plan(document)

    def test_external_export_cannot_change_joint_solution(self):
        shot = copy.deepcopy(self.shot)
        shot["frames"][15]["q"][4] += 0.1
        with self.assertRaisesRegex(ValueError, "differs"):
            prepare_shot(shot)

    def test_live_preflight_reports_missing_calibration_and_limits_without_connection(self):
        def unmeasured(role):
            raise ValueError(f"{role}: loaded limits unverified (test fixture)")

        with (
            patch("takeone.calibration.read_json", side_effect=missing_originals_config),
            patch("takeone.motion.limits.measured_limits", side_effect=unmeasured),
            patch.object(DeviceFactory, "open") as opening,
        ):
            result = preflight(self.plan)
            opening.assert_not_called()
        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["serial_ports_opened"])
        for role in ROLES:
            self.assertTrue(any(role in b and "original calibration" in b for b in result["blockers"]))
            self.assertTrue(any(role in b and "limits" in b for b in result["blockers"]))

    def test_live_cannot_open_devices_when_qualification_is_missing(self):
        with (
            TemporaryDirectory() as checked_folder,
            patch("takeone.motion.checked.DATA", Path(checked_folder)),
            patch.object(DeviceFactory, "open") as opening,
            patch("takeone.motion.service.preflight", return_value={"blockers": ["qualification missing"]}),
        ):
            check_plan(self.plan)
            with self.assertRaisesRegex(ValueError, "blocked"):
                execute_plan(self.plan, mode="live", confirm_plan=self.plan.plan_id, operator_ready=True)
            opening.assert_not_called()

    def test_offline_check_only_reports_mathematics_and_never_opens_a_device(self):
        with (
            TemporaryDirectory() as checked_folder,
            patch("takeone.motion.checked.DATA", Path(checked_folder)),
            patch.object(DeviceFactory, "open") as opening,
        ):
            result = check_plan(self.plan)
            opening.assert_not_called()
        self.assertNotIn("completed", result)
        self.assertFalse(result["physical_commands_sent"])
        self.assertEqual(result["shot_fidelity_passed"], self.plan.to_dict()["shot_fidelity_passed"])
        self.assertIn("jerk_rad_s3", result["analytic_extrema"])


class ArmControlTests(unittest.TestCase):
    def setUp(self):
        self.clock = VirtualClock()
        self.plan = small_plan()
        self.timing = ArmTiming.load()
        self.limits = software_limits()
        self.arm = SimulatedArm(self.plan.phone[0], self.clock.now)
        self.runner = ArmRunner(
            self.arm,
            "phone",
            self.plan,
            self.limits,
            self.timing,
            clock=self.clock.now,
            sleep=self.clock.sleep,
        )

    def test_wrong_initial_pose_never_dispatches(self):
        self.arm.q = self.arm.goal = (1, 0, 0, 0, 0)
        with self.assertRaisesRegex(ValueError, "starting pose"):
            self.runner.ready()
        self.assertFalse(any(e["phase"] == "command" for e in self.runner.events))

    def test_injected_feedback_enforces_endpoint_dwell_and_single_use(self):
        self.runner.ready()
        self.runner.run(100.2)
        self.assertTrue(self.runner.report()["settled"])
        commands = [e for e in self.runner.events if e["phase"] == "command"]
        self.assertEqual(commands[-1]["q_rad"], self.plan.phone[-1])
        for event in commands:
            self.assertAlmostEqual(event["write_start_s"], event["deadline_s"])
            for actual, expected in zip(
                event["q_rad"], self.plan.arm_at("phone", event["deadline_s"] - 100.2)
            ):
                self.assertAlmostEqual(actual, expected, places=12)
        with self.assertRaisesRegex(RuntimeError, "single-use"):
            self.runner.run(102)

    def test_stuck_encoder_aborts_instead_of_silently_following_commands(self):
        self.runner.limits = replace(self.limits, tracking_tolerance_rad=(0.025,) * 5)
        self.arm.command = lambda q: {"source": "simulated"}
        with self.assertRaisesRegex(RuntimeError, "tracking error"):
            self.runner.run(100.2)
        self.assertFalse(self.runner.settled)
        self.assertLess(self.clock.now(), 100.6)

    def test_slow_read_never_dispatches_an_overdue_target(self):
        original = self.arm.read

        def slow():
            observation = original()
            self.clock.sleep(0.08)
            return observation

        self.arm.read = slow
        with self.assertRaisesRegex(RuntimeError, "encoder read took.*budget"):
            self.runner.run(100.2)
        self.assertFalse(any(e["phase"] == "command" for e in self.runner.events))

    def test_stale_future_repeated_and_mislabeled_feedback_are_rejected(self):
        for offset, source in ((-0.1, "simulated"), (0.1, "simulated"), (0, "measured")):
            self.arm.read = lambda: ArmObservation((0,) * 5, self.clock.now() + offset, source)
            with self.assertRaises(ValueError):
                self.runner.observe()
        fixed = ArmObservation((0,) * 5, self.clock.now(), "simulated")
        self.arm.read = lambda: fixed
        self.runner.observe()
        with self.assertRaisesRegex(ValueError, "repeated"):
            self.runner.observe()

    def test_failure_hold_never_reuses_stale_position(self):
        self.runner.ready()
        self.clock.sleep(0.1)
        with patch.object(self.arm, "hold") as hold:
            self.runner.hold_on_fault()
            hold.assert_not_called()
        self.assertIn("unconfirmed", self.runner.events[-1]["source"])

    def test_endpoint_must_settle_for_a_stable_window(self):
        self.runner.limits = replace(self.limits, final_tolerance_rad=(0.000001,) * 5)
        self.arm.response_s = 100
        with self.assertRaisesRegex(RuntimeError, "did not settle"):
            self.runner.run(100.2)

    def test_velocity_acceleration_and_step_limits_are_enforced_before_io(self):
        for field, cap in (("velocity_rad_s", 0.01), ("acceleration_rad_s2", 0.01), ("step_rad", 0.0001)):
            limits = replace(self.limits, **{field: (cap,) * 5})
            with self.assertRaises(ValueError):
                limits.validate_plan(self.plan, "phone", self.timing)


@dataclass
class CalibrationDouble:
    id: int
    range_min: int
    range_max: int
    homing_offset: int
    drive_mode: int


class BusDouble:
    """Packet-level injection only. No test in this class establishes hardware motion."""

    def __init__(self, calibration):
        self.is_connected = False
        self.port = "INJECTED-PORT"
        self.port_handler = object()
        self.packet_handler = SimpleNamespace(readTxRx=self.read_block)
        self.calibration = {n: CalibrationDouble(**c) for n, c in calibration.raw_calibration.items()}
        self.motors = {
            n: SimpleNamespace(id=c.id, norm_mode=SimpleNamespace(value="degrees"))
            for n, c in self.calibration.items()
        }
        self.writes, self.closed = [], []
        self.registers = {
            "Operating_Mode": 0,
            "Torque_Enable": 0,
            "Phase": 0,
            "Min_Voltage_Limit": 40,
            "Max_Voltage_Limit": 80,
            "Max_Temperature_Limit": 70,
            "Max_Torque_Limit": 1000,
            "P_Coefficient": 16,
            "Present_Voltage": 60,
            "Present_Temperature": 25,
            "Torque_Limit": 1000,
            "Status": 0,
            "Present_Load": 0,
            "Present_Current": 0,
            "Present_Position": 2047,
            "Goal_Position": 2047,
        }
        self.overrides = {}
        self.packet_error = 0

    def connect(self):
        self.is_connected = True

    def read_calibration(self):
        return self.calibration.copy()

    def read(self, register, name, **kwargs):
        return self.overrides.get((register, name), self.registers[register])

    def write(self, register, name, value, **kwargs):
        self.writes.append((register, name, value, kwargs))
        self.overrides[register, name] = value

    def read_block(self, port, motor_id, address, length):
        from takeone.adapters.lerobot_arm import RAM_FIELDS

        name = next(n for n, m in self.motors.items() if m.id == motor_id)
        data = bytearray(length)
        for register, (addr, size) in RAM_FIELDS.items():
            data[addr - address : addr - address + size] = self.read(register, name).to_bytes(size, "little")
        return list(data), 0, self.packet_error

    def disconnect(self, disable_torque):
        self.closed.append(disable_torque)
        self.is_connected = False


class DriverTests(unittest.TestCase):
    def test_injected_packets_preserve_ids_raw_conversion_and_fixed_activation_order(self):
        for wrist in (6, 5):
            alignment = mapping(wrist)
            bus = BusDouble(alignment)
            arm = LeRobotArm(bus, alignment, {n: c.id for n, c in bus.calibration.items()})
            arm.connect()
            observation = arm.read()
            arm.activate(observation, (0.02,) * 5)
            self.assertEqual(
                [w[0] for w in bus.writes],
                ["Goal_Position"] * 5 + ["Torque_Enable"] * 5 + ["Goal_Position"] * 5,
            )
            self.assertEqual([w[2] for w in bus.writes[:5]], [2047] * 5)
            self.assertEqual([w[2] for w in bus.writes[10:15]], [2047] * 5)
            receipt = arm.command((0.1, 0.2, 0, 0, 0))
            self.assertEqual(receipt["encoded_raw"], alignment.to_raw((0.1, 0.2, 0, 0, 0)))
            self.assertTrue(all(w[3] == dict(normalize=False, num_retry=0) for w in bus.writes))
            self.assertLessEqual(observation.acquisition_start_s, observation.captured_monotonic_s)
            arm.release_supported()
            self.assertTrue(arm.lifecycle["torque_disabled_confirmed"])
            arm.disconnect()
            self.assertEqual(bus.closed, [False])

    def test_injected_error_byte_is_not_swallowed_by_a_group_reader(self):
        alignment = mapping()
        bus = BusDouble(alignment)
        arm = LeRobotArm(bus, alignment, {n: c.id for n, c in bus.calibration.items()})
        arm.connect()
        bus.packet_error = 4
        with self.assertRaisesRegex(ConnectionError, "error=4"):
            arm.read()
        self.assertEqual(bus.writes, [])

    def test_wrong_wrist_id_is_rejected_before_open(self):
        alignment = mapping()
        bus = BusDouble(alignment)
        bus.motors["wrist_roll"].id = 5
        arm = LeRobotArm(bus, alignment, {n: c.id for n, c in bus.calibration.items()})
        with self.assertRaisesRegex(ValueError, "identity"):
            arm.connect()
        self.assertFalse(bus.is_connected)

    def test_live_calibration_mismatch_and_wrong_mode_do_not_write_configuration(self):
        for mismatch in ("calibration", "Operating_Mode", "Torque_Enable", "Phase"):
            alignment = mapping()
            bus = BusDouble(alignment)
            if mismatch == "calibration":
                values = copy.deepcopy(bus.calibration)
                values["wrist_roll"].homing_offset += 1
                bus.read_calibration = lambda: values
            else:
                bus.registers[mismatch] = {"Operating_Mode": 1, "Torque_Enable": 1, "Phase": 16}[mismatch]
            arm = LeRobotArm(bus, alignment, {n: c.id for n, c in bus.calibration.items()})
            with self.assertRaises(ValueError):
                arm.connect()
            self.assertEqual(bus.writes, [])
            self.assertEqual(bus.closed, [False])


class CoordinationTests(unittest.TestCase):
    def test_physical_coordinator_rejects_injected_device_factory_before_open(self):
        factory = SimpleNamespace(simulated=True)
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "physical-only"):
                RobotRunner(small_plan(), factory, {r: software_limits() for r in ROLES}).run(Path(folder))

    def run_plan(self, plan, scenario="healthy"):
        with TemporaryDirectory() as folder:
            result, evidence = run_coordinated(
                plan, {r: software_limits() for r in ROLES}, Path(folder), scenario
            )
        self.assertEqual(result["terminated_workers"], [])
        pids = [entry["pid"] for entry in evidence.values()]
        self.assertEqual(len(set(pids)), 3)
        self.assertNotIn(os.getpid(), pids)
        for entry in evidence.values():
            self.assertEqual(entry["epoch"], result["epoch_monotonic_s"] or -1)
        return result, evidence

    def assert_zero_shutdown(self, result):
        writes = [e for e in result["roles"]["cart"]["events"] if "wire" in e]
        shutdown = [e for e in writes if e["phase"] == "shutdown_zero"]
        self.assertGreater(len(shutdown), 1)
        self.assertGreaterEqual(
            shutdown[-1]["write_start_s"] - shutdown[0]["write_start_s"],
            Timing.load().zero_duration_s - 1e-9,
        )
        self.assertTrue(all(e["wire"] == "0.00,0.00\n" for e in writes[writes.index(shutdown[0]) :]))
        self.assertFalse(result["physical_stop_confirmed"])
        return writes, shutdown

    def test_three_workers_share_epoch_and_finish_both_arms(self):
        plan = small_plan()
        result, evidence = self.run_plan(plan)
        self.assertTrue(result["completed"], {r: v.get("worker_error") for r, v in result["roles"].items()})
        epoch = result["epoch_monotonic_s"]
        for role in ROLES:
            report = result["roles"][role]
            self.assertTrue(report["settled"])
            first = next(e for e in report["events"] if e["phase"] == "command")
            self.assertEqual(first["deadline_s"], epoch)
            commands = [e for e in report["events"] if e["phase"] == "command"]
            self.assertTrue(any(any(e["q_rad"]) for e in commands))
            self.assertEqual(commands[-1]["q_rad"], list(plan.arm_at(role, plan.duration_s)))
        cart_first = next(e for e in result["roles"]["cart"]["events"] if e["phase"] == "motion")
        self.assertEqual(cart_first["deadline_s"], epoch)
        self.assertNotEqual(cart_first["wire"], "0.00,0.00\n")
        self.assertTrue(all(not entry["cancelled"] for entry in evidence.values()))
        self.assert_zero_shutdown(result)

    def test_blocked_arm_does_not_block_cart_writer_or_resume_motion(self):
        plan = small_plan(duration=1)
        result, evidence = self.run_plan(plan, "blocked_phone")
        self.assertFalse(result["completed"])
        blocked, released = evidence["phone"]["events"]
        self.assertEqual(blocked["event"], "read_blocked")
        self.assertEqual(released["event"], "read_released")
        self.assertAlmostEqual(released["at"] - blocked["at"], 0.4)
        phone_commands = [e for e in result["roles"]["phone"]["events"] if e["phase"] == "command"]
        self.assertTrue(any(any(e["q_rad"]) and e["write_end_s"] < blocked["at"] for e in phone_commands))
        self.assertTrue(all(e["write_end_s"] < blocked["at"] for e in phone_commands))
        for role in ROLES:
            first = next(e for e in result["roles"][role]["events"] if e["phase"] == "command")
            self.assertEqual(first["deadline_s"], result["epoch_monotonic_s"])
        writes, shutdown = self.assert_zero_shutdown(result)
        nonzero = [i for i, e in enumerate(writes) if e["wire"] != "0.00,0.00\n"]
        self.assertTrue(nonzero, {r: v.get("worker_error") for r, v in result["roles"].items()})
        self.assertEqual(writes[nonzero[0]]["deadline_s"], result["epoch_monotonic_s"])
        self.assertLess(writes[nonzero[0]]["write_end_s"], blocked["at"])
        self.assertTrue(any(blocked["at"] < writes[i]["write_start_s"] < released["at"] for i in nonzero))
        self.assertTrue(all(e["wire"] == "0.00,0.00\n" for e in writes[nonzero[-1] + 1 :]))
        self.assertLess(writes[nonzero[-1]]["write_start_s"] - result["epoch_monotonic_s"], 0.5)
        self.assertLess(shutdown[-1]["write_end_s"], released["at"])
        self.assertTrue(all(entry["cancelled"] for entry in evidence.values()))
        self.assertIn("encoder read took", result["roles"]["phone"]["worker_error"])
        errors = str(result["error"]) + str({r: v["worker_error"] for r, v in result["roles"].items()})
        self.assertTrue("lease expired" in errors or "stopped reporting fresh device work" in errors, errors)
        self.assertLessEqual(
            shutdown[0]["write_start_s"] - phone_commands[-1]["write_end_s"],
            ArmTiming.load().peer_lease_s + Timing.load().period_s,
        )

    def test_shared_clock_preserves_genuine_cart_deadline_rejection(self):
        result, evidence = self.run_plan(small_plan(duration=1), "late_cart")
        self.assertFalse(result["completed"])
        self.assertEqual(evidence["cart"]["events"][0]["event"], "dispatch_stall")
        report = result["roles"]["cart"]
        self.assertIn("Cart dispatch deadline missed", report["worker_error"])
        rejected = [e for e in report["events"] if e.get("dispatch_rejected")]
        self.assertEqual(len(rejected), 1)
        self.assertGreater(rejected[0]["lateness_s"], Timing.load().lateness_limit_s)
        writes, _ = self.assert_zero_shutdown(result)
        self.assertTrue(any(e["wire"] != "0.00,0.00\n" for e in writes))
        self.assertTrue(
            all(e["wire"] == "0.00,0.00\n" for e in writes if e["write_start_s"] >= rejected[0]["observed_s"])
        )

    def test_shared_clock_preserves_write_timeout_before_any_motion(self):
        result, evidence = self.run_plan(small_plan(), "slow_write")
        self.assertFalse(result["completed"])
        self.assertIsNone(result["epoch_monotonic_s"])
        self.assertEqual(evidence["cart"]["events"][0]["event"], "write_stall")
        self.assertIn("Cart write exceeded its deadline", result["roles"]["cart"]["worker_error"])
        writes, _ = self.assert_zero_shutdown(result)
        self.assertGreater(writes[0]["write_duration_s"], Timing.load().write_timeout_s)
        self.assertTrue(all(e["wire"] == "0.00,0.00\n" for e in writes))

    def test_timing_configuration_retains_cart_watchdog_margin(self):
        timing = Timing.load()
        self.assertEqual(timing.period_s, 0.02)
        self.assertEqual(timing.lateness_limit_s, 0.01)
        self.assertEqual(timing.write_timeout_s, 0.005)
        self.assertEqual(timing.host_gap_limit_s, 0.04)
        self.assertEqual(timing.watchdog_s, 0.06)
        self.assertEqual(ArmTiming.load().peer_lease_s, 0.1)
        self.assertLess(
            timing.period_s + timing.lateness_limit_s + timing.write_timeout_s, timing.host_gap_limit_s
        )


if __name__ == "__main__":
    unittest.main()
