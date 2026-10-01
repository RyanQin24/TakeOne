import copy
import json
import math
import sys
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from takeone.adapters.identity import identify_port
from takeone.adapters.uart import MotorUART
from takeone.cart.cli import execute
from takeone.cart.plan import cart_from_shot, load_cart_plan, prepare_cart
from takeone.cart.runtime import CartRunner, Timing, check_commissioning, host_timing_priority
from takeone.protocol import uart_pair
from takeone.simulation import drive

from tests.support.devices import SimulatedCart, VirtualClock


class ClockTransport(SimulatedCart):
    def __init__(self, clock, delay=0.0):
        self.clock, self.delay = clock, delay
        self.sent = []

    def set_speed(self, left, right):
        packet = uart_pair(left, right)
        self.sent.append((self.clock.now(), packet))
        self.clock.sleep(self.delay)
        return packet


class CartPlanTests(unittest.TestCase):
    def test_four_second_plan_comes_from_model_and_matches_reference_distance(self):
        plan = prepare_cart({"duration": 4})
        sign = drive.DIRECTION_SIGN
        direction = "forward" if sign == 1 else "reverse"
        self.assertEqual(plan.command_at(0), (sign * 0.04, sign * 0.04))
        self.assertEqual(plan.command_at(4), (0, 0))
        self.assertEqual(plan.command_at(-1), (0, 0))
        self.assertEqual(len(plan.commands), 201)
        document = plan.to_dict()
        self.assertAlmostEqual(document["prediction"]["wheelTravel"][0], sign * 0.55)
        self.assertEqual(document["prediction"]["commandDirection"], direction)
        self.assertEqual(document["prediction"]["commandSign"], sign)
        self.assertEqual(document["schedule"][0]["wire"], uart_pair(sign * 0.04, sign * 0.04))
        self.assertEqual(document["schedule"][-1]["wire"], "0.00,0.00\n")
        self.assertEqual(load_cart_plan(plan.to_dict()).plan_id, plan.plan_id)

    def test_plan_is_bound_to_sources_and_its_entire_schedule(self):
        document = prepare_cart({"duration": 2}).to_dict()
        for field in ("wire", "time_s", "commands"):
            bad = copy.deepcopy(document)
            bad["schedule"][0][field] = "changed"
            with self.assertRaisesRegex(ValueError, "stale"):
                load_cart_plan(bad)
        bad = copy.deepcopy(document)
        bad["provenance"] = {}
        with self.assertRaises(ValueError):
            load_cart_plan(bad)

    def test_invalid_plan_time_is_rejected(self):
        plan = prepare_cart({"duration": 2})
        for stamp in (math.nan, math.inf, True):
            with self.assertRaises(ValueError):
                plan.command_at(stamp)

    def test_export_import_preserves_compiled_motor_timeline(self):
        from takeone.planning.compiler import compile_shot

        shot = compile_shot()
        plan = cart_from_shot(shot)
        self.assertEqual(
            [s["wire"] for s in plan.to_dict()["schedule"]], [s["wire"] for s in shot["motorCommands"]]
        )
        self.assertNotEqual(shot["motorCommands"][0]["wire"], "0.00,0.00\n")
        shot["motorCommands"][0]["wire"] = "0.00,0.00\n"
        with self.assertRaises(ValueError):
            cart_from_shot(shot)

    def test_commissioning_is_separate_from_general_motion_calculation(self):
        envelope = check_commissioning(prepare_cart({"duration": 4}))
        self.assertEqual(envelope["direction"], "forward" if drive.DIRECTION_SIGN == 1 else "reverse")
        self.assertEqual(envelope["max_command_magnitude"], 0.05)
        with self.assertRaises(ValueError):
            check_commissioning(prepare_cart({"duration": 9}))
        # Pick a curve representable by the two-decimal wire speeds (.04, .06).
        duration = math.radians(35) * 0.58 / (0.1375 * 0.06 / 0.04 - 0.1375)
        arc = prepare_cart({"duration": duration, "driveProfile": "constant", "orbit": 35, "radius": 1.45})
        self.assertNotEqual(*arc.commands[0])
        with self.assertRaises(ValueError):
            check_commissioning(arc)

    def test_bad_geometry_profile_is_rejected_before_transport(self):
        with self.assertRaises(ValueError):
            prepare_cart({"duration": 16, "driveProfile": "smooth", "orbit": 35})


class SchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = prepare_cart({"duration": 4})
        cls.timing = Timing.load()

    def test_absolute_deadlines_do_not_accumulate_write_duration(self):
        clock = VirtualClock()
        transport = ClockTransport(clock, delay=0.002)
        runner = CartRunner(transport, self.timing, clock.now, clock.sleep)
        runner.run(self.plan)
        nonzero = [(t, p) for t, p in transport.sent if p != "0.00,0.00\n"]
        self.assertEqual(len(nonzero), 200)
        self.assertAlmostEqual(nonzero[-1][0] - nonzero[0][0], 3.98, places=8)
        zero_after = next(t for t, p in transport.sent if t > nonzero[-1][0] and p == "0.00,0.00\n")
        self.assertAlmostEqual(zero_after - nonzero[0][0], 4.0, places=8)
        self.assertLess(runner.report()["max_host_gap_s"], 0.021)
        self.assertFalse(runner.report()["physical_stop_confirmed"])

    def test_host_stall_aborts_and_never_catches_up_nonzero_commands(self):
        clock = VirtualClock()
        transport = ClockTransport(clock)
        stalled = False

        def sleep(seconds):
            nonlocal stalled
            clock.sleep(seconds)
            if clock.now() > 100.5 and not stalled:
                clock.sleep(0.080)
                stalled = True

        runner = CartRunner(transport, self.timing, clock.now, sleep)
        with self.assertRaisesRegex(RuntimeError, "deadline missed"):
            runner.run(self.plan)
        self.assertGreater(runner.report()["max_lateness_s"], self.timing.lateness_limit_s)
        self.assertEqual(runner.report()["rejected_dispatches"], 1)
        last_motion = max(i for i, (_, p) in enumerate(transport.sent) if p != "0.00,0.00\n")
        self.assertTrue(all(p == "0.00,0.00\n" for _, p in transport.sent[last_motion + 1 :]))
        self.assertLess(last_motion, 50)
        with self.assertRaisesRegex(RuntimeError, "single-use"):
            runner.run(self.plan)

    def test_compiled_boundaries_are_preserved_when_duration_is_not_a_tick_multiple(self):
        plan = prepare_cart({"duration": 4.013})
        clock = VirtualClock()
        transport = ClockTransport(clock, delay=0.002)
        runner = CartRunner(transport, self.timing, clock.now, clock.sleep)
        runner.run(plan)
        events = [e for e in runner.events if e["phase"] == "motion"]
        self.assertEqual(len(events), len(plan.times_s))
        for event, stamp in zip(events, plan.times_s):
            self.assertAlmostEqual(event["write_start_s"] - events[0]["write_start_s"], stamp)

    def test_each_command_change_uses_the_new_segment_without_float_rounding_delay(self):
        plan = replace(
            self.plan,
            times_s=(0.0, 0.03, 0.061),
            commands=((0.04, 0.04), (0.04, 0.06), (0.0, 0.0)),
            duration_s=0.061,
        )
        clock = VirtualClock()
        runner = CartRunner(ClockTransport(clock), self.timing, clock.now, clock.sleep)
        runner.run(plan)
        events = [e for e in runner.events if e["phase"] == "motion"]
        self.assertEqual(
            [e["wire"] for e in events],
            ["0.04,0.04\n", "0.04,0.04\n", "0.04,0.06\n", "0.04,0.06\n", "0.00,0.00\n"],
        )

    def test_long_write_aborts_before_next_motion_packet(self):
        clock = VirtualClock()
        transport = ClockTransport(clock)
        original = transport.set_speed

        def write(left, right):
            result = original(left, right)
            if left or right:
                clock.sleep(0.010)
            return result

        transport.set_speed = write
        runner = CartRunner(transport, self.timing, clock.now, clock.sleep)
        with self.assertRaisesRegex(RuntimeError, "write exceeded"):
            runner.run(self.plan)
        self.assertEqual(sum(p != "0.00,0.00\n" for _, p in transport.sent), 1)

    def test_partial_write_fault_stays_a_fault_after_zero_attempts(self):
        clock = VirtualClock()
        transport = ClockTransport(clock)
        original = transport.set_speed

        def write(left, right):
            if left or right:
                raise IOError("Incomplete packet")
            return original(left, right)

        transport.set_speed = write
        runner = CartRunner(transport, self.timing, clock.now, clock.sleep)
        with self.assertRaises(IOError):
            runner.run(self.plan)
        self.assertIn("Incomplete packet", runner.fault)
        self.assertTrue(all(p == "0.00,0.00\n" for _, p in transport.sent))

    def test_cancellation_attempts_zero_and_does_not_resume(self):
        clock = VirtualClock()
        transport = ClockTransport(clock)
        runner = CartRunner(transport, self.timing, clock.now, clock.sleep, lambda: clock.now() > 100.3)
        with self.assertRaises(InterruptedError):
            runner.run(self.plan)
        self.assertEqual(transport.sent[-1][1], "0.00,0.00\n")

    def test_invalid_watchdog_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.timing, write_timeout_s=0.1)
        with self.assertRaises(ValueError):
            replace(self.timing, watchdog_s=0.03)

    def test_monotonic_clock_regression_is_not_accepted(self):
        clock = VirtualClock()
        runner = CartRunner(ClockTransport(clock), self.timing, clock.now, clock.sleep)
        runner.now()
        clock.value -= 1
        with self.assertRaisesRegex(RuntimeError, "backwards"):
            runner.now()

    def test_no_implicit_live_permission_or_port_discovery(self):
        args = SimpleNamespace(command="live-test", execute=False, operator_ready=False)
        with patch("takeone.cart.cli.identify_port") as identity:
            with self.assertRaises(ValueError):
                execute(args, self.plan)
            identity.assert_not_called()

    def test_uart_write_timeout_is_independent_and_reset_flags_preserved(self):
        from tests.test_contracts import SerialDouble

        serial = SerialDouble()
        uart = MotorUART("TEST", timeout=0.1, write_timeout=0.005, serial_factory=lambda: serial)
        uart.connect()
        self.assertEqual(serial.at_open["write_timeout"], 0.005)
        self.assertFalse(serial.at_open["rts"])
        self.assertFalse(serial.at_open["dtr"])
        uart.close()
        self.assertEqual(serial.sent, [])

    def test_recorded_timing_report_can_be_serialized(self):
        clock = VirtualClock()
        runner = CartRunner(ClockTransport(clock), self.timing, clock.now, clock.sleep)
        runner.run(self.plan)
        json.dumps(runner.report(), allow_nan=False)

    def test_early_sleep_wakeup_does_not_dispatch_before_deadline(self):
        clock = VirtualClock()
        runner = CartRunner(
            ClockTransport(clock), self.timing, clock.now, lambda seconds: clock.sleep(seconds / 2)
        )
        runner.run(self.plan)
        for event in runner.events:
            if "write_start_s" in event:
                self.assertGreaterEqual(event["write_start_s"] + 1e-9, event["deadline_s"])

    def test_wake_guard_absorbs_normal_sleep_overshoot(self):
        clock = VirtualClock()

        def oversleep(seconds):
            clock.sleep(seconds + 0.012)

        runner = CartRunner(ClockTransport(clock), self.timing, clock.now, oversleep)
        runner.run(self.plan)
        self.assertIsNone(runner.report()["fault"])
        self.assertLess(runner.report()["max_lateness_s"], self.timing.lateness_limit_s)

    def test_wake_guard_still_rejects_a_real_host_stall(self):
        clock = VirtualClock()

        def oversleep(seconds):
            clock.sleep(seconds + 0.025)

        runner = CartRunner(ClockTransport(clock), self.timing, clock.now, oversleep)
        with self.assertRaisesRegex(RuntimeError, "deadline missed"):
            runner.run(self.plan)
        self.assertEqual(runner.report()["rejected_dispatches"], 1)

    def test_host_priority_can_be_explicitly_disabled(self):
        with host_timing_priority(enabled=False) as status:
            self.assertFalse(status["requested"])
            self.assertFalse(status["applied"])

    def test_shutdown_failure_cannot_be_reported_as_success(self):
        clock = VirtualClock()
        transport = ClockTransport(clock)
        write = transport.set_speed

        def fail_shutdown(left, right):
            if clock.now() > 104.11:
                raise IOError("USB disconnected during shutdown")
            return write(left, right)

        transport.set_speed = fail_shutdown
        runner = CartRunner(transport, self.timing, clock.now, clock.sleep)
        with self.assertRaisesRegex(IOError, "USB disconnected"):
            runner.run(self.plan)
        self.assertIsNotNone(runner.report()["fault"])
        self.assertFalse(runner.report()["physical_stop_confirmed"])

    def test_usb_identity_requires_exact_serial_and_port_before_connection(self):
        ports = [SimpleNamespace(device="COM5", serial_number="CART123", vid=1, pid=2)]
        fake_tools = SimpleNamespace(list_ports=SimpleNamespace(comports=lambda: ports))
        with patch.dict(sys.modules, {"serial.tools": fake_tools}):
            self.assertEqual(identify_port("com5", "CART123")["usb_serial"], "CART123")
            for port, serial in (("COM8", "CART123"), ("COM5", "WRONG"), ("COM5", "")):
                with self.assertRaises(ValueError):
                    identify_port(port, serial)


if __name__ == "__main__":
    unittest.main()
