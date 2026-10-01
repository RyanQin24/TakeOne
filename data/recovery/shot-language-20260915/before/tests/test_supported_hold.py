"""Fault paths for current-position goal seeding and supported torque release."""

import copy
import io
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from takeone.contracts import JOINTS
from takeone.motion.hold import console_observer, console_release_request, main, run_trial, supported_hold

from tests.support.devices import VirtualClock


@dataclass
class Calibration:
    id: int
    drive_mode: int = 0
    homing_offset: int = 400
    range_min: int = 100
    range_max: int = 2100


class HoldBus:
    def __init__(self):
        self.raw = {n: vars(Calibration(i + 1)).copy() for i, n in enumerate(JOINTS)}
        self.state = {
            r: dict.fromkeys(JOINTS, 0) for r in ("Goal_Position", "Torque_Enable", "Phase", "Operating_Mode")
        }
        self.state["Present_Position"] = dict.fromkeys(JOINTS, 1200)
        self.writes = []
        self.enabled = False
        self.calibration_mismatch = False
        self.goal_mismatch = False
        self.move_before_enable = False
        self.drift_after_enable = False
        self.enable_failure = False
        self.interrupt_after_enable = False
        self.release_failure = False

    def read_calibration(self):
        raw = copy.deepcopy(self.raw)
        if self.calibration_mismatch:
            raw[JOINTS[0]]["homing_offset"] += 1
        return {n: Calibration(**v) for n, v in raw.items()}

    def sync_read(self, register, *, normalize, num_retry):
        assert normalize is False and num_retry == 0
        if self.enabled and self.interrupt_after_enable:
            self.interrupt_after_enable = False
            raise KeyboardInterrupt
        if register == "Present_Position":
            if self.enabled and self.drift_after_enable:
                return dict.fromkeys(JOINTS, 1400)
            if self.writes and self.move_before_enable:
                return dict.fromkeys(JOINTS, 1400)
        if register == "Goal_Position" and self.goal_mismatch:
            return dict.fromkeys(JOINTS, 0)
        return self.state[register].copy()

    def sync_write(self, register, values, *, normalize, num_retry):
        assert normalize is False and num_retry == 0
        self.writes.append((register, values.copy()))
        self.state[register] = values.copy()
        if register == "Torque_Enable":
            self.enabled = True
            if self.enable_failure:
                raise ConnectionError("lost acknowledgment after possible torque enable")

    def write(self, register, motor, value, *, normalize, num_retry):
        assert register == "Torque_Enable" and value == 0
        self.writes.append(("release", motor))
        if self.release_failure and motor == JOINTS[0]:
            raise ConnectionError("release failed")
        self.state[register][motor] = value


class SupportedHoldTests(unittest.TestCase):
    def setUp(self):
        self.bus = HoldBus()
        self.clock = VirtualClock()

    def trial(self):
        return run_trial(self.bus, self.bus.raw, 0.2, 1.0, clock=self.clock.now, sleep=self.clock.sleep)

    def assert_released(self, result):
        self.assertTrue(result["torque_disabled_confirmed"])
        self.assertEqual([v for r, v in self.bus.writes if r == "release"], list(JOINTS))

    def test_seeds_measured_goals_before_enable_then_releases_every_motor(self):
        result = self.trial()
        self.assertTrue(result["completed"])
        self.assertEqual(self.bus.writes[0], ("Goal_Position", dict.fromkeys(JOINTS, 1200)))
        self.assertEqual(self.bus.writes[1], ("Torque_Enable", dict.fromkeys(JOINTS, 1)))
        self.assertEqual(result["max_drift_deg"], 0)
        self.assert_released(result)

    def test_unconfirmed_goals_never_enable_torque(self):
        self.bus.goal_mismatch = True
        result = self.trial()
        self.assertFalse(result["completed"])
        self.assertFalse(result["torque_enable_attempted"])
        self.assertEqual(len(self.bus.writes), 1)

    def test_movement_while_preparing_goals_prevents_enable(self):
        self.bus.move_before_enable = True
        result = self.trial()
        self.assertFalse(result["torque_enable_attempted"])
        self.assertIn("moved", result["error"])

    def test_existing_enabled_state_is_not_changed(self):
        self.bus.state["Torque_Enable"][JOINTS[0]] = 1
        result = self.trial()
        self.assertFalse(result["completed"])
        self.assertEqual(self.bus.writes, [])

    def test_calibration_mismatch_causes_no_writes(self):
        self.bus.calibration_mismatch = True
        result = self.trial()
        self.assertFalse(result["completed"])
        self.assertEqual(self.bus.writes, [])

    def test_uncertain_enable_failure_still_releases_all_motors(self):
        self.bus.enable_failure = True
        result = self.trial()
        self.assertFalse(result["completed"])
        self.assert_released(result)

    def test_excess_drift_aborts_and_releases(self):
        self.bus.drift_after_enable = True
        result = self.trial()
        self.assertFalse(result["completed"])
        self.assertGreater(result["max_drift_deg"], 1)
        self.assert_released(result)

    def test_keyboard_interrupt_releases_supported_payload(self):
        self.bus.interrupt_after_enable = True
        result = self.trial()
        self.assertFalse(result["completed"])
        self.assertIn("KeyboardInterrupt", result["error"])
        self.assert_released(result)

    def test_release_failure_does_not_skip_other_motors_or_claim_success(self):
        self.bus.release_failure = True
        result = self.trial()
        self.assertFalse(result["completed"])
        self.assertFalse(result["torque_disabled_confirmed"])
        self.assertTrue(result["manual_motor_power_cut_required"])
        self.assertEqual([v for r, v in self.bus.writes if r == "release"], list(JOINTS))

    def test_readiness_and_duration_checks_precede_any_connection(self):
        factory = Mock()
        for ready, support, duration in ((False, True, 1), (True, False, 1), (True, True, 3)):
            with self.assertRaises(ValueError):
                supported_hold(
                    "phone",
                    "windows",
                    operator_ready=ready,
                    payload_supported=support,
                    duration_s=duration,
                    bus_factory=factory,
                )
        factory.assert_not_called()

    def test_existing_evidence_is_not_overwritten(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "hold.json"
            path.write_text("prior", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                result = main(
                    ["--role", "phone", "--operator-ready", "--payload-supported", "--output", str(path)]
                )
            self.assertEqual(result, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), "prior")


class ObserveBus(HoldBus):
    def __init__(self):
        super().__init__()
        for register, value in {
            "Min_Voltage_Limit": 40,
            "Max_Voltage_Limit": 140,
            "Max_Temperature_Limit": 80,
            "Max_Torque_Limit": 1000,
            "Torque_Limit": 1000,
            "P_Coefficient": 16,
            "Present_Voltage": 125,
            "Present_Temperature": 30,
            "Present_Current": 5,
            "Present_Load": 10,
            "Status": 0,
        }.items():
            self.state[register] = dict.fromkeys(JOINTS, value)
        self.fault_register = None
        self.fault_value = None

    def sync_read(self, register, *, normalize, num_retry):
        if self.enabled and self.fault_register == register:
            return dict.fromkeys(JOINTS, self.fault_value)
        return super().sync_read(register, normalize=normalize, num_retry=num_retry)


class ManualBus(ObserveBus):
    def __init__(self):
        super().__init__()
        self.commands = []
        self.enable_fault_motor = None
        self.read_fault_register = None
        self.holding_drift_counts = 0

    def read(self, register, motor, **kwargs):
        if self.enabled and self.read_fault_register == register:
            raise ConnectionError("feedback lost")
        value = super().sync_read(register, **kwargs)[motor]
        if register == "Present_Position" and self.enabled:
            value -= self.holding_drift_counts
        return value

    def write(self, register, motor, value, **kwargs):
        self.commands.append((register, motor, value))
        self.state[register][motor] = value
        if register == "Torque_Enable" and value == 1:
            self.enabled = True
            if motor == self.enable_fault_motor:
                raise ConnectionError("uncertain individual enable")

    def sync_write(self, *args, **kwargs):
        raise AssertionError("The working-script mode must use acknowledged individual writes")


class ManualHoldTests(unittest.TestCase):
    def trial(self, bus, seconds=2.0, emit=None):
        clock = VirtualClock()
        origin = clock.now()
        return run_trial(
            bus,
            bus.raw,
            None,
            1.0,
            clock=clock.now,
            sleep=clock.sleep,
            release_requested=lambda: clock.now() - origin >= seconds,
            emit=emit,
        )

    def assert_off(self, bus, result):
        self.assertTrue(result["torque_disabled_confirmed"])
        self.assertEqual(bus.commands[-5:], [("Torque_Enable", n, 0) for n in JOINTS])

    def test_fixed_goals_before_and_after_torque_until_operator_release(self):
        bus = ManualBus()
        result = self.trial(bus, seconds=35)
        self.assertTrue(result["completed"])
        self.assertTrue(result["goal_writes_acknowledged"])
        self.assertTrue(result["active_goal_writes_acknowledged"])
        self.assertTrue(result["active_target_confirmed"])
        self.assertGreaterEqual(result["last_sample_elapsed_s"], 35)
        self.assertEqual(result["release_reason"], "operator_enter")
        self.assertEqual(bus.commands[:5], [("Goal_Position", n, 1200) for n in JOINTS])
        self.assertEqual(bus.commands[5:10], [("Torque_Enable", n, 1) for n in JOINTS])
        self.assertEqual(bus.commands[10:15], [("Goal_Position", n, 1200) for n in JOINTS])
        self.assertEqual(len(bus.commands), 20)
        self.assert_off(bus, result)

    def test_reported_thirteen_count_drift_does_not_disable_or_change_target(self):
        bus, output = ManualBus(), io.StringIO()
        bus.holding_drift_counts = 13
        with redirect_stdout(output):
            result = self.trial(bus, emit=console_observer("phone"))
        self.assertTrue(result["completed"])
        self.assertAlmostEqual(result["max_drift_deg"], 13 * 360 / 4095)
        self.assertIn("first_drift_warning", result)
        self.assertNotIn("drift_trip", result)
        self.assertEqual(result["targets_raw"], dict.fromkeys(JOINTS, 1200))
        self.assertEqual(bus.commands[10:15], [("Goal_Position", n, 1200) for n in JOINTS])
        self.assertEqual(len(bus.commands), 20)
        self.assertIn("DRIFT WARNING; TORQUE REMAINS ON", output.getvalue())
        self.assertNotIn("automatic release", output.getvalue())
        self.assert_off(bus, result)

    def test_failed_post_enable_goal_write_releases_every_motor(self):
        bus = ManualBus()
        original_write = bus.write

        def fail_active_goal(register, motor, value, **kwargs):
            if register == "Goal_Position" and bus.enabled and motor == JOINTS[2]:
                raise ConnectionError("post-enable goal was not acknowledged")
            return original_write(register, motor, value, **kwargs)

        bus.write = fail_active_goal
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertFalse(result["active_target_confirmed"])
        self.assertFalse(result["active_goal_writes_acknowledged"])
        self.assertIn("post-enable goal was not acknowledged", result["error"])
        self.assert_off(bus, result)

    def test_enable_transition_cannot_replace_the_captured_targets(self):
        bus = ManualBus()
        original_write = bus.write

        def reset_goal_on_enable(register, motor, value, **kwargs):
            original_write(register, motor, value, **kwargs)
            if register == "Torque_Enable" and value == 1:
                bus.state["Goal_Position"][motor] = 1199

        bus.write = reset_goal_on_enable
        result = self.trial(bus)
        self.assertTrue(result["completed"])
        self.assertTrue(result["active_target_confirmed"])
        self.assertEqual(bus.state["Goal_Position"], dict.fromkeys(JOINTS, 1200))
        self.assertEqual(bus.commands[10:15], bus.commands[:5])
        self.assert_off(bus, result)

    def test_partial_enable_failure_releases_every_motor(self):
        bus = ManualBus()
        bus.enable_fault_motor = JOINTS[2]
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertIn("uncertain individual enable", result["error"])
        self.assert_off(bus, result)

    def test_health_fault_still_releases_in_manual_mode(self):
        bus = ManualBus()
        bus.fault_register, bus.fault_value = "Status", 32
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertEqual(result["release_reason"], "fault")
        self.assert_off(bus, result)

    def test_lost_feedback_still_releases_in_manual_mode(self):
        bus = ManualBus()
        bus.read_fault_register = "Present_Position"
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertIn("feedback lost", result["error"])
        self.assert_off(bus, result)

    def test_ctrl_c_releases_in_manual_mode(self):
        bus = ManualBus()

        def interrupt(event):
            if event["phase"] == "holding":
                raise KeyboardInterrupt

        result = self.trial(bus, emit=interrupt)
        self.assertFalse(result["completed"])
        self.assertEqual(result["release_reason"], "operator_interrupt")
        self.assert_off(bus, result)

    def test_cancel_before_enable_does_not_write(self):
        bus = ManualBus()
        result = self.trial(bus, seconds=0)
        self.assertFalse(result["torque_enable_attempted"])
        self.assertEqual(bus.commands, [])

    def test_manual_mode_requires_console_and_rejects_timer_before_output_or_connect(self):
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            output = Path(temporary) / "hold.json"
            args = [
                "--role",
                "phone",
                "--until-enter",
                "--cart-parked",
                "--operator-ready",
                "--payload-supported",
                "--output",
                str(output),
            ]
            with patch("takeone.motion.hold.sys.stdin.isatty", return_value=False):
                self.assertEqual(main(args), 1)
            self.assertFalse(output.exists())
            with patch("takeone.motion.hold.sys.stdin.isatty", return_value=True):
                self.assertEqual(main([*args, "--duration", "20"]), 1)
            self.assertFalse(output.exists())

    def test_manual_sample_storage_is_bounded_without_a_release_timer(self):
        bus = ManualBus()
        result = self.trial(bus, seconds=60)
        self.assertTrue(result["completed"])
        self.assertEqual(len(result["samples"]), 1200)
        self.assertGreater(result["samples_dropped"], 0)
        self.assertEqual(result["sample_count"], len(result["samples"]) + result["samples_dropped"])
        self.assert_off(bus, result)

    def test_windows_console_enter_releases_and_other_keys_do_not(self):
        keyboard = Mock()
        keyboard.kbhit.side_effect = [True, False, True]
        keyboard.getwch.side_effect = ["x", "\r"]
        with (
            patch("takeone.motion.hold.sys.platform", "win32"),
            patch.dict("sys.modules", {"msvcrt": keyboard}),
        ):
            requested = console_release_request()
            self.assertFalse(requested())
            self.assertTrue(requested())

    def test_windows_console_ctrl_c_is_an_interrupt(self):
        keyboard = Mock()
        keyboard.kbhit.return_value = True
        keyboard.getwch.return_value = "\x03"
        with (
            patch("takeone.motion.hold.sys.platform", "win32"),
            patch.dict("sys.modules", {"msvcrt": keyboard}),
        ):
            with self.assertRaises(KeyboardInterrupt):
                console_release_request()()


class StationaryObservationTests(unittest.TestCase):
    def trial(self, bus, emit=None, duration=20):
        clock = VirtualClock()
        return run_trial(
            bus, bus.raw, duration, 1.0, observe=True, clock=clock.now, sleep=clock.sleep, emit=emit
        )

    def assert_off(self, result, bus):
        self.assertEqual([v for r, v in bus.writes if r == "release"], list(JOINTS))
        self.assertTrue(result["torque_disabled_confirmed"])
        self.assertFalse(any(bus.state["Torque_Enable"].values()))

    def test_twenty_second_observation_reports_on_state_and_finite_release(self):
        bus, events = ObserveBus(), []
        result = self.trial(bus, events.append)
        self.assertTrue(result["completed"])
        self.assertTrue(result["torque_on_confirmed"])
        self.assertTrue(result["active_target_confirmed"])
        self.assertFalse(result["physical_holding_capacity_verified"])
        self.assertGreaterEqual(result["samples"][-1]["elapsed_s"], 20)
        self.assertEqual(result["samples"][0]["torque_enable"], dict.fromkeys(JOINTS, 1))
        self.assertEqual(result["samples"][0]["health_raw"]["Present_Voltage"][JOINTS[0]], 125)
        self.assertEqual(events[0]["phase"], "preparing")
        self.assertTrue(any(e["phase"] == "holding" and e["remaining_s"] <= 5 for e in events))
        self.assertEqual([e["phase"] for e in events[-2:]], ["releasing", "released"])
        self.assert_off(result, bus)

    def test_observation_sends_fixed_goal_after_enable_before_motor_tracking(self):
        class ActivationBus(ObserveBus):
            active_target = False

            def sync_write(self, register, values, **kwargs):
                if register == "Goal_Position" and self.enabled:
                    self.active_target = True
                return super().sync_write(register, values, **kwargs)

            def sync_read(self, register, **kwargs):
                if register == "Present_Position" and self.enabled and not self.active_target:
                    # One count of startup sag is allowed; it must not become
                    # the new target when the active command is sent.
                    return dict.fromkeys(JOINTS, 1199)
                return super().sync_read(register, **kwargs)

        bus = ActivationBus()
        result = self.trial(bus)
        self.assertTrue(result["completed"])
        self.assertTrue(bus.active_target)
        self.assertEqual([r for r, _ in bus.writes[:3]], ["Goal_Position", "Torque_Enable", "Goal_Position"])
        self.assertEqual(bus.writes[0][1], bus.writes[2][1])
        self.assertEqual(bus.writes[2][1], dict.fromkeys(JOINTS, 1200))
        self.assertEqual(sum(r == "Goal_Position" for r, _ in bus.writes), 2)
        self.assert_off(result, bus)

    def test_movement_before_active_command_aborts_without_chasing_the_arm(self):
        bus = ObserveBus()
        bus.drift_after_enable = True
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertFalse(result["active_target_confirmed"])
        self.assertIn("before active command", result["error"])
        self.assertEqual(sum(r == "Goal_Position" for r, _ in bus.writes), 1)
        self.assert_off(result, bus)

    def test_failed_active_write_still_releases_all_motors(self):
        bus = ObserveBus()
        original_write = bus.sync_write

        def fail_active_write(register, values, **kwargs):
            if register == "Goal_Position" and bus.enabled:
                raise ConnectionError("active target write failed")
            return original_write(register, values, **kwargs)

        bus.sync_write = fail_active_write
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertFalse(result["active_target_confirmed"])
        self.assertIn("active target write failed", result["error"])
        self.assert_off(result, bus)

    def test_slow_activation_checks_abort_before_second_goal_write(self):
        bus, clock = ObserveBus(), VirtualClock()
        original_read = bus.sync_read

        def delayed_read(register, **kwargs):
            if bus.enabled:
                clock.sleep(0.04)
            return original_read(register, **kwargs)

        bus.sync_read = delayed_read
        result = run_trial(bus, bus.raw, 20, 1, observe=True, clock=clock.now, sleep=clock.sleep)
        self.assertFalse(result["completed"])
        self.assertIn("100 ms", result["error"])
        self.assertEqual(sum(r == "Goal_Position" for r, _ in bus.writes), 1)
        self.assert_off(result, bus)

    def test_drift_failure_identifies_joint_and_elapsed_time(self):
        bus = ObserveBus()
        original_write = bus.sync_write

        def drift_after_active_command(register, values, **kwargs):
            if register == "Goal_Position" and bus.enabled:
                bus.state["Present_Position"][JOINTS[2]] -= 13
            return original_write(register, values, **kwargs)

        bus.sync_write = drift_after_active_command
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertEqual(result["drift_trip"]["joint"], JOINTS[2])
        self.assertAlmostEqual(result["drift_trip"]["drift_deg"], 13 * 360 / 4095)
        self.assertEqual(result["drift_trip"]["elapsed_s"], result["last_sample_elapsed_s"])
        self.assertIn(JOINTS[2], result["error"])
        self.assert_off(result, bus)

    def test_existing_two_second_mode_does_not_implicitly_allow_long_holds(self):
        bus = ObserveBus()
        with self.assertRaises(ValueError):
            run_trial(bus, bus.raw, 20, 1)
        with self.assertRaises(ValueError):
            self.trial(bus, duration=31)
        self.assertEqual(bus.writes, [])

    def test_unhealthy_state_prevents_goal_writes_and_torque_enable(self):
        failures = {
            "Present_Voltage": 20,
            "Present_Temperature": 80,
            "Status": 32,
            "Torque_Limit": 0,
            "P_Coefficient": 0,
            "Max_Torque_Limit": 0,
            "Max_Voltage_Limit": 30,
        }
        for register, value in failures.items():
            with self.subTest(register=register):
                bus = ObserveBus()
                bus.state[register][JOINTS[1]] = value
                result = self.trial(bus)
                self.assertFalse(result["completed"])
                self.assertFalse(result["torque_enable_attempted"])
                self.assertEqual(bus.writes, [])

    def test_power_status_or_target_fault_during_hold_releases_all_motors(self):
        failures = (
            ("Present_Voltage", 20),
            ("Status", 32),
            ("Goal_Position", 1500),
            ("Torque_Limit", 0),
            ("Present_Temperature", 90),
        )
        for register, value in failures:
            with self.subTest(register=register):
                bus = ObserveBus()
                bus.fault_register, bus.fault_value = register, value
                result = self.trial(bus)
                self.assertFalse(result["completed"])
                self.assert_off(result, bus)

    def test_lost_torque_readback_aborts_without_reenabling(self):
        bus = ObserveBus()
        bus.fault_register, bus.fault_value = "Torque_Enable", 0
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertIn("Torque-enabled", result["error"])
        self.assertEqual(sum(register == "Torque_Enable" for register, _ in bus.writes), 1)
        self.assert_off(result, bus)

    def test_console_failure_during_hold_cannot_skip_release(self):
        bus = ObserveBus()

        def failed_display(event):
            if event["phase"] != "preparing":
                raise BrokenPipeError("operator display lost")

        result = self.trial(bus, failed_display)
        self.assertFalse(result["completed"])
        self.assertIn("BrokenPipeError", result["error"])
        self.assert_off(result, bus)

    def test_keyboard_interrupt_in_health_monitor_still_releases(self):
        bus = ObserveBus()
        bus.interrupt_after_enable = True
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assert_off(result, bus)

    def test_observation_requires_stationary_cart_attestation_before_connect(self):
        factory = Mock()
        with self.assertRaisesRegex(ValueError, "cart-parked"):
            supported_hold(
                "phone",
                "windows",
                operator_ready=True,
                payload_supported=True,
                duration_s=20,
                observe=True,
                bus_factory=factory,
            )
        factory.assert_not_called()
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            path = Path(temporary) / "observe.json"
            self.assertEqual(
                main(
                    [
                        "--role",
                        "phone",
                        "--observe",
                        "--operator-ready",
                        "--payload-supported",
                        "--output",
                        str(path),
                    ]
                ),
                1,
            )
            self.assertFalse(path.exists())

    def test_console_clearly_marks_on_countdown_and_release(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = self.trial(ObserveBus(), console_observer("phone"))
        self.assertTrue(result["completed"])
        text = output.getvalue()
        self.assertIn("TORQUE ON 5/5", text)
        self.assertIn("SUPPORT THE ARM NOW", text)
        self.assertIn("RELEASING TORQUE NOW", text)
        self.assertIn("TORQUE OFF CONFIRMED", text)

    def test_interrupt_during_release_does_not_skip_remaining_motors(self):
        bus = ObserveBus()
        original_write = bus.write

        def interrupted_release(register, motor, value, **kwargs):
            if motor == JOINTS[0]:
                bus.writes.append(("release", motor))
                raise KeyboardInterrupt
            return original_write(register, motor, value, **kwargs)

        bus.write = interrupted_release
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertFalse(result["torque_disabled_confirmed"])
        self.assertTrue(result["manual_motor_power_cut_required"])
        self.assertEqual([v for r, v in bus.writes if r == "release"], list(JOINTS))
        self.assertIn("KeyboardInterrupt", result["release_errors"][0])

    def test_interrupt_during_release_readback_retains_report_and_power_cut_instruction(self):
        bus = ObserveBus()
        original_read = bus.sync_read

        def interrupted_readback(register, **kwargs):
            if register == "Torque_Enable" and any(r == "release" for r, _ in bus.writes):
                raise KeyboardInterrupt
            return original_read(register, **kwargs)

        bus.sync_read = interrupted_readback
        result = self.trial(bus)
        self.assertFalse(result["completed"])
        self.assertFalse(result["torque_disabled_confirmed"])
        self.assertTrue(result["manual_motor_power_cut_required"])
        self.assertEqual([v for r, v in bus.writes if r == "release"], list(JOINTS))
