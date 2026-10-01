import copy
import io
import json
import math
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from takeone.adapters.simulated import SimulatedCart, VirtualClock
from takeone.cart.cli import main
from takeone.cart.plan import load_cart_plan, prepare_cart, prepare_command_test
from takeone.cart.runtime import CartRunner, Timing, check_commissioning
from takeone.config import read_json, rig_config
from takeone.paths import CONFIGS
from takeone.protocol import uart_pair
from takeone.simulation import drive


class CaptureCart(SimulatedCart):
    def __init__(self):
        self.packets = []

    def set_speed(self, left, right):
        packet = uart_pair(left, right)
        self.packets.append(packet)
        return packet


class ExplicitCartCommandTests(unittest.TestCase):
    def test_explicit_command_preserves_the_existing_speed_calibration_and_default(self):
        default = prepare_cart({"duration": 2})
        plan = prepare_command_test(0.05)
        sign = drive.DIRECTION_SIGN
        self.assertEqual(default.command_at(0), (sign * 0.04, sign * 0.04))
        self.assertEqual(plan.command_at(0), (sign * 0.05, sign * 0.05))
        self.assertEqual(plan.command_at(2), (0, 0))
        self.assertEqual(plan.to_dict()["settings"], default.to_dict()["settings"])
        self.assertAlmostEqual(plan.to_dict()["prediction"]["wheelTravel"][0], sign * 0.34375)
        self.assertFalse(plan.to_dict()["prediction"]["validatedOnHardware"])
        self.assertEqual(load_cart_plan(plan.to_dict()).plan_id, plan.plan_id)

    def test_two_boundary_plan_keeps_fifty_hertz_refresh_and_ends_with_stop(self):
        plan = prepare_command_test(0.05)
        clock, cart = VirtualClock(), CaptureCart()
        runner = CartRunner(cart, Timing.load(), clock.now, clock.sleep)
        runner.run(plan)
        wire = uart_pair(drive.DIRECTION_SIGN * 0.05, drive.DIRECTION_SIGN * 0.05)
        self.assertEqual(cart.packets.count(wire), 100)
        self.assertEqual(cart.packets[-1], "0.00,0.00\n")
        self.assertIsNone(runner.fault)

    def test_increased_command_is_limited_to_two_seconds_and_point_zero_five(self):
        check_commissioning(prepare_command_test(0.05, 2))
        check_commissioning(prepare_command_test(0.04, 4))
        for command, duration in ((0.05, 2.01), (0.05, 4), (0.06, 2), (0.04, 4.01)):
            with self.subTest(command=command, duration=duration):
                with self.assertRaises(ValueError):
                    check_commissioning(prepare_command_test(command, duration))

    def test_direction_and_equal_command_guards_remain_active(self):
        for sign in (-1, 1):
            rig = rig_config()
            rig["cart"]["reverse_enabled"] = sign == -1
            with (
                patch.object(drive, "DIRECTION_SIGN", sign),
                patch("takeone.cart.runtime.rig_config", return_value=rig),
            ):
                plan = prepare_command_test(0.05)
                self.assertEqual(plan.command_at(0), (sign * 0.05, sign * 0.05))
                check_commissioning(plan)
                for commands in (
                    ((-sign * 0.05, -sign * 0.05), (0, 0)),
                    ((sign * 0.04, sign * 0.05), (0, 0)),
                    ((sign * 0.045, sign * 0.045), (0, 0)),
                ):
                    with self.assertRaises(ValueError):
                        check_commissioning(replace(plan, commands=commands))

    def test_configuration_cannot_raise_the_code_ceiling_above_the_authorized_command(self):
        plan = prepare_command_test(0.05)
        config = read_json(CONFIGS / "cart-runtime.json")
        config["commissioning_max_command"] = 0.06
        with patch("takeone.cart.runtime.read_json", return_value=config):
            with self.assertRaisesRegex(ValueError, "authorized"):
                check_commissioning(plan)

    def test_modified_inputs_schedule_prediction_or_provenance_are_rejected(self):
        document = prepare_command_test(0.05).to_dict()
        edits = (
            ("command_test", {"command_magnitude": 0.04, "duration_s": 2}),
            ("provenance", {}),
            ("prediction", {}),
            ("schedule", []),
            ("hardware_ready", True),
        )
        for key, value in edits:
            bad = copy.deepcopy(document)
            bad[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                load_cart_plan(bad)

    def test_invalid_magnitudes_and_durations_are_rejected(self):
        for value in (True, math.nan, math.inf, -0.05, 0, 0.03, 0.049, 0.151):
            with self.subTest(command=value), self.assertRaises(ValueError):
                prepare_command_test(value)
        for value in (True, math.nan, 0, 1.99, 61):
            with self.subTest(duration=value), self.assertRaises(ValueError):
                prepare_command_test(0.05, value)

    def test_cli_prepares_protected_explicit_report_and_rejects_mixed_sources(self):
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path = Path(directory) / "plan.json"
            args = ["prepare", "--command", "0.05", "--duration", "2", "--output", str(path)]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(path.read_text())["command_test"]["command_magnitude"], 0.05)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                main(args)
            self.assertEqual(path.read_bytes(), before)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args + ["--shot", "ignored.json"])
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
