"""Inspection reads actual state without granting qualification or writing motors."""

import hashlib
import io
import json
import math
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from takeone.contracts import JOINTS
from takeone.motion.commission import inspect_arm, main, nominal_mapping, specification


@dataclass
class Calibration:
    id: int
    drive_mode: int = 0
    homing_offset: int = 400
    range_min: int = 100
    range_max: int = 2100


def fixture():
    raw = {name: vars(Calibration(i + 1)).copy() for i, name in enumerate(JOINTS)}
    device = dict(port="COM_TEST", usb_serial="TEST", motor_ids={n: v["id"] for n, v in raw.items()})
    return device, raw, "a" * 64


class ReadBus:
    def __init__(self, device, raw):
        self.is_connected = False
        self.raw = raw
        self.calls = []
        self.mismatch = False
        self.fail_read = False
        self.fail_connect = False
        self.phase = 0

    def connect(self):
        self.is_connected = True
        self.calls.append("connect")
        if self.fail_connect:
            raise ConnectionError("handshake failed after opening")

    def read_calibration(self):
        values = {n: Calibration(**v) for n, v in self.raw.items()}
        if self.mismatch:
            values[JOINTS[0]].homing_offset += 1
        return values

    def sync_read(self, register, *, normalize, num_retry):
        assert normalize is False and num_retry == 0
        self.calls.append(register)
        if self.fail_read:
            return {}
        value = {"Present_Position": 1200, "Goal_Position": 3500, "Phase": self.phase}.get(register, 0)
        return dict.fromkeys(JOINTS, value)

    def disconnect(self, *, disable_torque):
        assert disable_torque is False, "Inspection must preserve torque state"
        self.calls.append("close_without_torque_change")
        self.is_connected = False


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.spec = fixture()
        self.bus = ReadBus(*self.spec[:2])
        self.factory = Mock(return_value=self.bus)
        self.identity = Mock(return_value=dict(port="COM_TEST", usb_serial="TEST"))
        self.patchers = [
            patch("takeone.motion.commission.specification", return_value=self.spec),
            patch("takeone.motion.commission.model_ranges", return_value=dict.fromkeys(JOINTS, [-90, 90])),
            patch(
                "takeone.motion.commission.ArmMapping.load", side_effect=ValueError("not physically verified")
            ),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def inspect(self):
        return inspect_arm("phone", bus_factory=self.factory, identity_check=self.identity)

    def test_midpoint_conversion_and_raw_goal_are_reported_without_motion(self):
        result = self.inspect()
        self.assertTrue(result["completed"])
        self.assertTrue(result["configured_calibration_matches_hardware"])
        self.assertFalse(result["motor_register_writes"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertIsNone(result["model_joint_radians"])
        row = result["joints"][JOINTS[0]]
        self.assertAlmostEqual(row["servo_degrees"], 100 * 360 / 4095)
        self.assertAlmostEqual(row["model_radians_assuming_standard_calibration"], 100 * 2 * math.pi / 4095)
        self.assertEqual(row["registers_raw"]["Goal_Position"], 3500)
        self.assertEqual(len(result["live_state_issues"]), 5)
        self.assertEqual(self.bus.calls[-1], "close_without_torque_change")

    def test_identity_mismatch_does_not_construct_or_open_bus(self):
        self.identity.side_effect = ValueError("wrong USB serial")
        result = self.inspect()
        self.assertFalse(result["completed"])
        self.assertFalse(result["serial_port_opened"])
        self.factory.assert_not_called()

    def test_hardware_calibration_mismatch_prevents_degree_interpretation(self):
        self.bus.mismatch = True
        result = self.inspect()
        self.assertTrue(result["completed"])
        self.assertFalse(result["configured_calibration_matches_hardware"])
        self.assertIsNone(result["joints"][JOINTS[0]]["servo_degrees"])
        self.assertTrue(any("calibration differs" in issue for issue in result["live_state_issues"]))

    def test_extended_angle_mode_does_not_produce_nominal_pose(self):
        self.bus.phase = 16
        result = self.inspect()
        self.assertIsNone(result["joints"][JOINTS[0]]["model_radians_assuming_standard_calibration"])

    def test_incomplete_read_is_saved_as_failure_and_closes_without_torque_change(self):
        self.bus.fail_read = True
        result = self.inspect()
        self.assertFalse(result["completed"])
        self.assertIn("Incomplete", result["error"])
        self.assertEqual(self.bus.calls[-1], "close_without_torque_change")

    def test_failed_handshake_closes_partially_opened_bus(self):
        self.bus.fail_connect = True
        result = self.inspect()
        self.assertFalse(result["completed"])
        self.assertTrue(result["serial_port_opened"])
        self.assertFalse(self.bus.is_connected)

    def test_preexisting_owner_is_not_closed(self):
        self.bus.is_connected = True
        result = self.inspect()
        self.assertFalse(result["completed"])
        self.assertTrue(self.bus.is_connected)
        self.assertEqual(self.bus.calls, [])

    def test_nominal_model_midpoint_is_distinct_from_homing_reference(self):
        result = nominal_mapping("phone")
        row = result["joints"][JOINTS[0]]
        self.assertEqual(row["encoder_midpoint"], 1100)
        self.assertEqual(row["nominal_servo_zero_offset_deg"], 0)
        self.assertAlmostEqual(row["homing_reference_servo_deg"], (2047 - 1100) * 360 / 4095)
        self.assertFalse(result["verified"])
        self.assertFalse(result["tool_transform_verified"])
        self.assertIsNone(result["safe_ranges_rad"])
        self.factory.assert_not_called()

    def test_existing_report_is_preserved_before_any_inspection(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text("existing evidence", encoding="utf-8")
            with patch("takeone.motion.commission.inspect_arm") as inspect, redirect_stdout(io.StringIO()):
                self.assertEqual(main(["inspect", "--output", str(path)]), 1)
            inspect.assert_not_called()
            self.assertEqual(path.read_text(encoding="utf-8"), "existing evidence")

    def test_help_does_not_inspect(self):
        with patch("takeone.motion.commission.inspect_arm") as inspect, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                main(["--help"])
        self.assertEqual(result.exception.code, 0)
        inspect.assert_not_called()


class OriginalFileTests(unittest.TestCase):
    def test_original_uses_lerobot_joint_dictionary_not_takeone_schema(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            originals = root / "calibration"
            devices = root / "configs/devices"
            originals.mkdir()
            devices.mkdir(parents=True)
            device, raw, _ = fixture()
            device["calibration_id"] = "test-arm"
            source = json.dumps(raw).encode()
            (originals / "arm.json").write_bytes(source)
            registry = dict(
                schema_version=1,
                arms=dict(
                    phone=dict(
                        original_path="arm.json",
                        original_sha256=hashlib.sha256(source).hexdigest(),
                        calibration_id="test-arm",
                    )
                ),
            )
            (originals / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            (devices / "windows.json").write_text(
                json.dumps(dict(schema_version=1, arms=dict(phone=device))), encoding="utf-8"
            )
            with (
                patch("takeone.motion.commission.CALIBRATION", originals),
                patch("takeone.motion.commission.CONFIGS", root / "configs"),
            ):
                self.assertEqual(specification("phone", "windows")[1], raw)
