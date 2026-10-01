import copy
import math
import time
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from takeone.adapters.lerobot_arm import LeRobotArm
from takeone.adapters.simulated import SimulatedArm, SimulatedCart, VirtualClock
from takeone.cart.runtime import Timing
from takeone.config import provenance
from takeone.contracts import JOINTS, ArmObservation
from takeone.execution import RobotRunner
from takeone.motion.arm import ArmRunner
from takeone.motion.devices import DeviceFactory
from takeone.motion.limits import ArmTiming, preflight, simulated_limits
from takeone.motion.plan import ROLES, digest, load_plan, prepare_shot
from takeone.motion.service import execute_plan, replay

from tests.test_contracts import mapping, missing_originals_config


def small_plan(duration=0.4, travel=0.06):
    samples = []
    for t, fraction in ((0, 0), (duration / 2, 0.5), (duration, 1)):
        samples.append(
            dict(
                time_s=t,
                arms={
                    "phone": [fraction * travel, 0, 0, 0, 0],
                    "light": [0, -fraction * travel, 0, 0, 0],
                },
            )
        )
    body = dict(
        schema="takeone.robot-plan.v1",
        provenance=provenance(),
        joint_order=list(JOINTS),
        coordinate_frame="reference_urdf_rad",
        interpolation="linear_joint_angles",
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
        for i, frame in enumerate(shot["frames"]):
            t = i * shot["settings"]["duration"] / (len(shot["frames"]) - 1)
            self.assertEqual(plan.arm_at("phone", t), tuple(frame["q"][3:8]))
            self.assertEqual(plan.arm_at("light", t), tuple(frame["q"][8:13]))
        self.assertEqual(
            [s["wire"] for s in plan.to_dict()["cart_schedule"]], [s["wire"] for s in shot["motorCommands"]]
        )

    def test_joint_interpolation_is_not_a_new_ik_solution(self):
        plan = small_plan()
        self.assertAlmostEqual(plan.arm_at("phone", 0.1)[0], 0.015)
        self.assertAlmostEqual(plan.arm_at("light", 0.3)[1], -0.045)
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
            patch.object(DeviceFactory, "open") as opening,
            patch("takeone.motion.service.preflight", return_value={"blockers": ["qualification missing"]}),
        ):
            with self.assertRaisesRegex(ValueError, "blocked"):
                execute_plan(self.plan, mode="live", confirm_plan=self.plan.plan_id, operator_ready=True)
            opening.assert_not_called()

    def test_default_preview_replays_both_arms_with_real_feedback_errors(self):
        result = replay(self.plan)
        self.assertTrue(result["completed"])
        for role in ROLES:
            report = result["roles"][role]
            self.assertTrue(report["settled"])
            self.assertGreater(max(report["max_error_rad"]), 0)
            self.assertFalse(report["physical_tracking_verified"])


class ArmControlTests(unittest.TestCase):
    def setUp(self):
        self.clock = VirtualClock()
        self.plan = small_plan()
        self.timing = ArmTiming.load()
        self.limits = simulated_limits()
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

    def test_finite_plan_finishes_at_measured_endpoint_and_cannot_restart(self):
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
        with self.assertRaisesRegex(RuntimeError, "IO budget"):
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
    def __init__(self, calibration):
        self.is_connected = False
        self.calibration = {n: CalibrationDouble(**c) for n, c in calibration.raw_calibration.items()}
        self.motors = {
            n: SimpleNamespace(id=c.id, norm_mode=SimpleNamespace(value="degrees"))
            for n, c in self.calibration.items()
        }
        self.writes, self.closed = [], []
        self.registers = {"Operating_Mode": 0, "Torque_Enable": 1, "Phase": 0}

    def connect(self):
        self.is_connected = True

    def read_calibration(self):
        return self.calibration.copy()

    def sync_read(self, register, **kwargs):
        if register == "Present_Position":
            return {n: 0.0 for n in JOINTS}
        return {n: self.registers[register] for n in JOINTS}

    def sync_write(self, register, values, **kwargs):
        self.writes.append((register, values, kwargs))

    def disconnect(self, disable_torque):
        self.closed.append(disable_torque)
        self.is_connected = False


class DriverTests(unittest.TestCase):
    def test_both_motor_roles_map_once_without_clipping_or_configuration_writes(self):
        for wrist in (6, 5):
            alignment = mapping(wrist)
            bus = BusDouble(alignment)
            arm = LeRobotArm(bus, alignment, {n: c.id for n, c in bus.calibration.items()})
            arm.connect()
            observation = arm.read()
            arm.command((0.1, 0.2, 0, 0, 0))
            arm.disconnect()
            self.assertEqual(observation.source, "measured")
            self.assertEqual(bus.writes[0][0], "Goal_Position")
            self.assertEqual(bus.writes[0][1]["shoulder_lift"], -math.degrees(0.2))
            self.assertEqual(bus.writes[0][2], {"num_retry": 0})
            self.assertEqual(bus.closed, [False])
            self.assertEqual(len(bus.writes), 1)

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
                bus.registers[mismatch] = {"Operating_Mode": 1, "Torque_Enable": 0, "Phase": 16}[mismatch]
            arm = LeRobotArm(bus, alignment, {n: c.id for n, c in bus.calibration.items()})
            with self.assertRaises(ValueError):
                arm.connect()
            self.assertEqual(bus.writes, [])
            self.assertEqual(bus.closed, [False])


class BlockingArm(SimulatedArm):
    def read(self):
        if self.goal != (0, 0, 0, 0, 0):
            time.sleep(0.4)
        return super().read()


@dataclass(frozen=True)
class BlockingFactory:
    simulated: bool = True

    def open(self, role, plan, arm_timing, cart_timing):
        if role == "cart":
            return SimulatedCart()
        kind = BlockingArm if role == "phone" else SimulatedArm
        return kind(plan.arm_at(role, 0))


class CoordinationTests(unittest.TestCase):
    def test_three_workers_share_epoch_and_finish_both_arms(self):
        plan = small_plan()
        with TemporaryDirectory() as folder:
            result = RobotRunner(plan, DeviceFactory(True), {r: simulated_limits() for r in ROLES}).run(
                Path(folder)
            )
        self.assertTrue(result["completed"], {r: v.get("worker_error") for r, v in result["roles"].items()})
        epoch = result["epoch_monotonic_s"]
        for role in ROLES:
            report = result["roles"][role]
            self.assertTrue(report["settled"])
            first = next(e for e in report["events"] if e["phase"] == "command")
            self.assertEqual(first["deadline_s"], epoch)
        cart_first = next(e for e in result["roles"]["cart"]["events"] if e["phase"] == "motion")
        self.assertEqual(cart_first["deadline_s"], epoch)

    def test_blocked_arm_does_not_block_cart_writer_or_resume_motion(self):
        plan = small_plan(duration=1)
        with TemporaryDirectory() as folder:
            result = RobotRunner(plan, BlockingFactory(), {r: simulated_limits() for r in ROLES}).run(
                Path(folder)
            )
        self.assertFalse(result["completed"])
        writes = [e for e in result["roles"]["cart"]["events"] if "wire" in e]
        nonzero = [i for i, e in enumerate(writes) if e["wire"] != "0.00,0.00\n"]
        self.assertTrue(nonzero, {r: v.get("worker_error") for r, v in result["roles"].items()})
        self.assertTrue(all(e["wire"] == "0.00,0.00\n" for e in writes[nonzero[-1] + 1 :]))
        self.assertLess(writes[nonzero[-1]]["write_start_s"] - result["epoch_monotonic_s"], 0.5)
        self.assertFalse(result["physical_stop_confirmed"])

    def test_timing_configuration_retains_cart_watchdog_margin(self):
        timing = Timing.load()
        self.assertEqual(timing.watchdog_s, 0.06)
        self.assertLess(
            timing.period_s + timing.lateness_limit_s + timing.write_timeout_s, timing.host_gap_limit_s
        )


if __name__ == "__main__":
    unittest.main()
