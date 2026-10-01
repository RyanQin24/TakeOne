import math
import unittest
from unittest.mock import patch

from takeone.adapters.uart import MotorUART
from takeone.calibration import ArmMapping, hardware_blockers
from takeone.config import read_json, rig_config
from takeone.contracts import JOINTS, MotionFrame
from takeone.protocol import uart_pair


def missing_originals_config(path):
    """Missing-file fixture independent of the operator's recovered calibration."""
    if path.name == "registry.json":
        return {"schema_version": 1, "arms": {role: {"original_path": None} for role in ("phone", "light")}}
    return read_json(path)


class SerialDouble:
    def __init__(self):
        self.is_open = False
        self.sent = []
        self.at_open = None

    def open(self):
        self.at_open = vars(self).copy()
        self.is_open = True

    def write(self, data):
        self.sent.append(data)
        return len(data)

    def close(self):
        self.is_open = False


def mapping(last_id=6):
    return ArmMapping(
        (1, -1, 1, 1, 1),
        (10.0, 0.0, 0.0, 0.0, 0.0),
        ((-1.0, 1.0),) * 5,
        {
            name: dict(id=motor_id, range_min=0, range_max=4095, homing_offset=-1886, drive_mode=0)
            for name, motor_id in zip(JOINTS, [1, 2, 3, 4, last_id])
        },
    )


class ProtocolTests(unittest.TestCase):
    def test_uart_matches_supplied_cap_and_rounding(self):
        self.assertEqual(uart_pair(1, -1), "0.15,-0.15\n")
        self.assertEqual(uart_pair(0.04, 0.06), "0.04,0.06\n")
        self.assertEqual(uart_pair(0.0349, 0.0351), "0.03,0.04\n")
        for value in [True, float("nan"), float("inf"), "0.04"]:
            with self.assertRaises(ValueError):
                uart_pair(value, 0)

    def test_serial_opens_only_explicitly_with_reset_controls_low(self):
        serial = SerialDouble()
        calls = []

        def factory():
            calls.append(1)
            return serial

        cart = MotorUART("TEST_PORT", serial_factory=factory)
        self.assertFalse(cart.connected)
        self.assertEqual(calls, [])
        cart.connect()
        cart.connect()
        self.assertEqual(len(calls), 1)
        for flag in ("dtr", "rts", "rtscts", "dsrdtr", "xonxoff"):
            self.assertIs(serial.at_open[flag], False)
        self.assertEqual(serial.at_open["port"], "TEST_PORT")
        self.assertEqual(serial.at_open["baudrate"], 115200)
        cart.set_speed(0.04, 0.06)
        cart.disconnect()
        self.assertEqual(serial.sent, [b"0.04,0.06\n", b"0.00,0.00\n"])
        self.assertFalse(cart.connected)

    def test_partial_packet_is_an_error_not_a_successful_command(self):
        serial = SerialDouble()
        cart = MotorUART("TEST_PORT", serial_factory=lambda: serial)
        cart.connect()
        serial.write = lambda data: 2
        with self.assertRaises(IOError):
            cart.set_speed(0.04, 0.04)

    def test_bad_motion_contract_is_rejected(self):
        for args in [
            (0, 0.0, 0.16, 0.0, {"phone": (0,) * 5}),
            (0, 0.0, 0.0, 0.0, {"phone": (0,) * 6}),
            (-1, 0.0, 0.0, 0.0, {"phone": (0,) * 5}),
            (0, float("nan"), 0.0, 0.0, {"phone": (0,) * 5}),
        ]:
            with self.assertRaises(ValueError):
                MotionFrame(*args)

    def test_mapping_applies_sign_and_offset_once_and_roundtrips(self):
        calibration = mapping()
        q = (0.1, 0.2, 0.3, 0.4, 0.5)
        converted = calibration.to_degrees(q)
        self.assertAlmostEqual(converted["shoulder_pan.pos"], math.degrees(0.1) + 10)
        self.assertAlmostEqual(converted["shoulder_lift.pos"], -math.degrees(0.2))
        for actual, expected in zip(calibration.from_degrees(converted), q):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(set(converted), {n + ".pos" for n in JOINTS})
        with self.assertRaises(ValueError):
            calibration.to_degrees((2.0, 0.0, 0.0, 0.0, 0.0))

    def test_missing_original_calibration_blocks_live_mapping(self):
        with patch("takeone.calibration.read_json", side_effect=missing_originals_config):
            for role in ("phone", "light"):
                with self.assertRaisesRegex(ValueError, f"{role}: original calibration is missing"):
                    ArmMapping.load(role)
            blockers = hardware_blockers()
        for role in ("phone", "light"):
            self.assertIn(f"{role}: original calibration is missing locally", blockers)

    def test_calibration_policy_uses_original_bounds_without_a_second_range_table(self):
        def aligned_config(path):
            config = read_json(path)
            if path.name in ("phone.json", "light.json"):
                config.update(verified=True, range_source="calibration", safe_ranges_rad=None)
            return config

        # Numerical fixture only: this does not qualify the connected robot.
        with patch("takeone.calibration.read_json", side_effect=aligned_config):
            for role in ("phone", "light"):
                calibration = ArmMapping.load(role)
                for index, (name, bounds) in enumerate(zip(JOINTS, calibration.safe_ranges_rad)):
                    raw = calibration.raw_calibration[name]
                    span = (raw["range_max"] - raw["range_min"]) * 180 / 4095
                    # The operating range is the calibration span less the stop
                    # margin, recentred by this joint's zero offset; a joint with a
                    # nonzero offset is deliberately not symmetric about zero.
                    usable = max(span - calibration.limit_margin_deg, span / 2)
                    offset = calibration.offsets_deg[index]
                    sign = calibration.signs[index]
                    expected = sorted(math.radians((v - offset) / sign) for v in (-usable, usable))
                    self.assertAlmostEqual(bounds[0], expected[0])
                    self.assertAlmostEqual(bounds[1], expected[1])
                q = [0.0] * 5
                q[2] = calibration.safe_ranges_rad[2][1] + math.radians(360 / 4095)
                with self.assertRaisesRegex(ValueError, "outside configured operating range"):
                    calibration.to_raw(q)

    def test_calibration_policy_does_not_assert_model_alignment(self):
        def unaligned_config(path):
            config = read_json(path)
            if path.name in ("phone.json", "light.json"):
                config.update(verified=False, range_source="calibration", safe_ranges_rad=None)
            return config

        with patch("takeone.calibration.read_json", side_effect=unaligned_config):
            with self.assertRaisesRegex(ValueError, "verified model alignment"):
                ArmMapping.load("phone")

    def test_calibration_policy_rejects_conflicting_or_unknown_range_sources(self):
        for source, bounds, message in (
            ("calibration", [[-1, 1]] * 5, "second range table"),
            ("anything", None, "unknown operating range source"),
            ("measured", None, "operating ranges are required"),
        ):

            def invalid_config(path):
                config = read_json(path)
                if path.name == "phone.json":
                    config.update(verified=True, range_source=source, safe_ranges_rad=bounds)
                return config

            with patch("takeone.calibration.read_json", side_effect=invalid_config):
                with self.assertRaisesRegex(ValueError, message):
                    ArmMapping.load("phone")

    def test_rig_dimensions_preserved(self):
        cart = rig_config()["cart"]
        self.assertEqual((cart["wheel_diameter_m"], cart["wheel_width_m"]), (0.19, 0.06))
        # Inverted motor wiring is handled by cart-runtime wire_polarity at the
        # transport. This flag reverses the planned path itself, so it stays off.
        self.assertIs(cart["reverse_enabled"], False)
        self.assertEqual(cart["drive_forward_sign"], 1)

    def test_invalid_config_schema_and_limits_fail_closed(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for text in ["[]", '{"schema_version":2}', '{"schema_version":true}']:
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_json(path)
        invalid = rig_config()
        invalid["cart"]["track_width_m"] = -0.5
        with patch("takeone.config.read_json", return_value=invalid):
            with self.assertRaises(ValueError):
                rig_config()
        modified = rig_config()
        modified["cart"]["reverse_enabled"] = False
        with patch("takeone.config.read_json", return_value=modified):
            self.assertIs(rig_config()["cart"]["reverse_enabled"], False)
        for value in (None, 1, "true"):
            invalid = rig_config()
            invalid["cart"]["reverse_enabled"] = value
            with patch("takeone.config.read_json", return_value=invalid):
                with self.assertRaisesRegex(ValueError, "reverse_enabled"):
                    rig_config()

    def test_planner_import_does_not_load_serial_or_lerobot(self):
        import subprocess
        import sys

        command = 'import sys; import takeone.planning.compiler; assert "serial" not in sys.modules; assert "lerobot" not in sys.modules'
        subprocess.run([sys.executable, "-c", command], check=True)


if __name__ == "__main__":
    unittest.main()
