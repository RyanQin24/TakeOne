import copy
import csv
import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from takeone.cart.cli import main
from takeone.cart.diagnostics import DriftTrial, analyze_measurements, analyze_trial
from takeone.cart.plan import prepare_cart
from takeone.cart.response import CartResponse, WheelResponse
from takeone.cart.runtime import check_commissioning
from takeone.config import _PROCESS_INPUTS, provenance
from takeone.planning.settings import parameters
from takeone.protocol import uart_pair
from takeone.simulation import drive


def synthetic_table(left_gain=1.0, right_gain=1.0):
    """Explicit synthetic steady response, never written to active configuration."""
    return {
        "schema_version": 1,
        "mode": "measured_table",
        "evidence": "SYNTHETIC test fixture, not hardware measurements",
        "wheels": {
            side: [
                {"command": c, "speed_m_s": c / 0.04 * 0.1375 * gain}
                for c in (-0.15, -0.05, -0.04, 0.04, 0.05, 0.15)
            ]
            for side, gain in (("left", left_gain), ("right", right_gain))
        },
    }


class ResponseTests(unittest.TestCase):
    def test_provisional_profile_is_explicit_and_marks_missing_feedback(self):
        model = CartResponse.load(0.1375)
        self.assertEqual(model.mode, "provisional_symmetric")
        self.assertEqual(model.speeds_for((-0.04, 0.04)), (-0.1375, 0.1375))
        self.assertEqual(model.speeds_for((-0.03, 0.03)), (0, 0))
        self.assertFalse(model.describe()["feedbackAvailable"])
        self.assertFalse(model.describe()["physicalStraightnessVerified"])

    def test_feasible_asymmetry_compensation_reaches_same_axle_path(self):
        model = CartResponse.from_config(synthetic_table(right_gain=0.8), 0.1375)
        with patch.object(CartResponse, "load", return_value=model):
            for direction in (-1, 1):
                with patch.object(drive, "DIRECTION_SIGN", direction):
                    plan = prepare_cart({"duration": 4})
                    self.assertEqual(plan.commands[0], (direction * 0.04, direction * 0.05))
                    self.assertLess(plan.to_dict()["prediction"]["maxPathError"], 1e-12)
                    self.assertLess(plan.to_dict()["prediction"]["maxYawErrorDegrees"], 1e-10)
                    with self.assertRaises(ValueError):
                        check_commissioning(plan)

    def test_two_percent_imbalance_is_not_hidden_when_trim_cannot_be_transmitted(self):
        model = CartResponse.from_config(synthetic_table(right_gain=1.02), 0.1375)
        with patch.object(CartResponse, "load", return_value=model):
            trace = drive.simulate(parameters({"duration": 4}))
            report = drive.summary(trace)
            self.assertEqual(
                trace["records"][0]["wire"],
                uart_pair(drive.DIRECTION_SIGN * 0.04, drive.DIRECTION_SIGN * 0.04),
            )
            expected_yaw = math.degrees((1.02 - 1) * 0.1375 * 4 / 0.58)
            self.assertAlmostEqual(report["maxYawErrorDegrees"], expected_yaw)
            self.assertFalse(report["reproducesRequestedPath"])
            with self.assertRaisesRegex(ValueError, "quantized"):
                prepare_cart({"duration": 4})

    def test_rounding_can_erase_a_small_trim_at_minimum_command(self):
        self.assertEqual(uart_pair(-0.04 * 0.98, -0.04), "-0.04,-0.04\n")
        self.assertEqual(uart_pair(-0.03, -0.04), "-0.03,-0.04\n")
        self.assertEqual(CartResponse.load(0.1375).speeds_for((-0.03, -0.04)), (0, -0.1375))

    def test_missing_direction_does_not_use_other_direction_measurements(self):
        document = synthetic_table()
        for points in document["wheels"].values():
            points[:] = [point for point in points if point["command"] < 0]
        model = CartResponse.from_config(document, 0.1375)
        with self.assertRaisesRegex(ValueError, "no measured response"):
            model.commands_for((0.1375, 0.1375))
        with self.assertRaisesRegex(ValueError, "no measured response"):
            model.speeds_for((0.04, 0.04))

    def test_interpolation_has_no_extrapolation_or_deadband_invention(self):
        wheel = WheelResponse(((0.04, 0.1), (0.06, 0.2)))
        self.assertAlmostEqual(wheel.interpolate(0.05), 0.15)
        self.assertAlmostEqual(wheel.interpolate(0.15, inverse=True), 0.05)
        self.assertEqual(wheel.interpolate(0.01, inverse=True), 0)
        self.assertEqual(wheel.interpolate(0.08, inverse=True), 0.04)
        self.assertEqual(wheel.interpolate(0), 0)
        for value in (0.03, 0.07):
            with self.assertRaisesRegex(ValueError, "no extrapolation"):
                wheel.interpolate(value)

    def test_invalid_table_does_not_fall_back_to_symmetric_model(self):
        invalid = [(), ((0.04, -0.1),), ((0.039, 0.1),), ((0.16, 0.1),), ((0.04, math.nan),)]
        invalid += [((0.04, 0.1), (0.05, 0.09)), ((0.04, 0.1), (0.04, 0.1))]
        for points in invalid:
            with self.subTest(points=points), self.assertRaises(ValueError):
                WheelResponse(points)
        for field, value in (("mode", "unknown"), ("evidence", ""), ("schema_version", True)):
            document = synthetic_table()
            document[field] = value
            with self.assertRaises(ValueError):
                CartResponse.from_config(document, 0.1375)
        document = synthetic_table()
        document["mode"] = "provisional_symmetric"
        with self.assertRaisesRegex(ValueError, "ignored measurements"):
            CartResponse.from_config(document, 0.1375)

    def test_nonfinite_or_untransmitted_commands_are_rejected(self):
        model = CartResponse.load(0.1375)
        for value in ((True, 0), (math.nan, 0), (0,), (0, 0, 0)):
            with self.assertRaises(ValueError):
                model.commands_for(value)
            with self.assertRaises(ValueError):
                model.speeds_for(value)
        for command in (0.041, 0.2):
            with self.assertRaises(ValueError):
                model.speeds_for((command, 0))

    def test_old_process_cannot_sign_plan_with_new_disk_hashes(self):
        changed = copy.deepcopy(_PROCESS_INPUTS)
        changed["configs/rig.json"] = "old process input"
        with patch("takeone.config._PROCESS_INPUTS", changed):
            with self.assertRaisesRegex(ValueError, "restart"):
                provenance()
            with self.assertRaisesRegex(ValueError, "restart"):
                prepare_cart({"duration": 4})


class DriftAnalysisTests(unittest.TestCase):
    @staticmethod
    def trial(left=0.15, right=0.1375):
        return DriftTrial(
            "synthetic-1",
            math.copysign(0.04, left),
            math.copysign(0.04, left),
            4,
            (left + right) * 4 / 2,
            math.degrees((right - left) * 4 / 0.58),
            0.58,
            "synthetic analytic fixture",
            "no slip; steady synthetic speeds",
        )

    def test_independent_forward_and_reverse_arc_measurements_recover_wheel_travel(self):
        for left, right in ((0.15, 0.1375), (-0.15, -0.1375), (0.1375, 0.15)):
            report = analyze_trial(self.trial(left, right))
            inferred = report["inferred_under_no_slip"]
            self.assertAlmostEqual(inferred["left_travel_m"], left * 4)
            self.assertAlmostEqual(inferred["right_travel_m"], right * 4)
            self.assertEqual(inferred["faster_wheel"], "left" if abs(left) > abs(right) else "right")
            self.assertFalse(report["proportional_trim_hypothesis"]["enabled_for_execution"])
            self.assertFalse(report["hardware_qualified"])

    def test_reports_disappearing_trim_and_polarity_without_changing_commands(self):
        trial = self.trial(-0.15, -0.1375)
        report = analyze_trial(trial)
        hypothesis = report["proportional_trim_hypothesis"]
        self.assertTrue(hypothesis["below_minimum_raw"])
        self.assertFalse(hypothesis["changes_transmitted_command"])
        self.assertTrue(report["polarity_matches_simulator"])
        wrong_polarity = copy.copy(trial.__dict__) | {"left_command": 0.04, "right_command": 0.04}
        self.assertFalse(analyze_trial(DriftTrial(**wrong_polarity))["polarity_matches_simulator"])

    def test_straight_limit_and_signed_reverse_are_finite(self):
        for speed in (-0.1375, 0.1375):
            inferred = analyze_trial(self.trial(speed, speed))["inferred_under_no_slip"]
            self.assertAlmostEqual(inferred["axle_end_x_m"], 4 * speed)
            self.assertEqual(inferred["axle_end_y_m"], 0)
            self.assertIsNone(inferred["faster_wheel"])

    def test_bad_measurements_are_rejected(self):
        original = self.trial().__dict__
        for name, value in (
            ("duration_s", 0),
            ("track_width_m", -1),
            ("heading_change_deg", math.nan),
            ("axle_travel_m", 0),
            ("source", ""),
            ("right_command", 0.05),
            ("heading_change_deg", 180),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                DriftTrial(**(original | {name: value}))

    def test_csv_command_is_offline_and_refuses_overwriting_reports(self):
        with TemporaryDirectory() as folder:
            path, output = Path(folder) / "measurements.csv", Path(folder) / "report.json"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, DriftTrial.__dataclass_fields__)
                writer.writeheader()
                writer.writerow(self.trial().__dict__)
            with patch("takeone.cart.cli.identify_port") as ports:
                self.assertEqual(
                    main(["analyze-drift", "--measurements", str(path), "--output", str(output)]), 0
                )
                ports.assert_not_called()
            report = json.loads(output.read_text())
            self.assertFalse(report["changes_active_calibration"])
            self.assertEqual(len(report["trials"]), 1)
            self.assertEqual(len(report["source_sha256"]), 64)
            with self.assertRaises(FileExistsError):
                main(["analyze-drift", "--measurements", str(path), "--output", str(output)])
            with path.open("a", newline="", encoding="utf-8") as stream:
                csv.DictWriter(stream, DriftTrial.__dataclass_fields__).writerow(self.trial().__dict__)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                analyze_measurements(path)


if __name__ == "__main__":
    unittest.main()
