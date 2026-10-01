import hashlib
import json
import unittest
from dataclasses import make_dataclass
from tempfile import TemporaryDirectory
from unittest.mock import patch

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS
from takeone.motion.calibration_revision import apply_revision, endpoint_changes, original_calibration
from takeone.paths import CALIBRATION

Calibration = make_dataclass(
    "Calibration",
    [("id", int), ("drive_mode", int), ("homing_offset", int), ("range_min", int), ("range_max", int)],
)


def values(maximum=3000):
    return {
        name: dict(id=index + 1, drive_mode=0, homing_offset=0, range_min=1000, range_max=maximum)
        for index, name in enumerate(JOINTS)
    }


class Bus:
    def __init__(self, calibration, torque=None):
        self.calibration = json.loads(json.dumps(calibration))
        self.torque = dict.fromkeys(JOINTS, 0) if torque is None else torque
        self.locks = dict.fromkeys(JOINTS, 1)
        self.is_connected = False
        self.writes = []

    def connect(self):
        self.is_connected = True

    def disconnect(self, disable_torque):
        self.is_connected = False

    def sync_read(self, register, **kwargs):
        if register == "Torque_Enable":
            return self.torque.copy()
        if register == "Operating_Mode":
            return dict.fromkeys(JOINTS, 0)
        if register == "Phase":
            return dict.fromkeys(JOINTS, 12)
        raise AssertionError(register)

    def read_calibration(self):
        return {name: Calibration(**row) for name, row in self.calibration.items()}

    def read(self, register, name, **kwargs):
        if register != "Lock":
            raise AssertionError(register)
        return self.locks[name]

    def write(self, register, name, value, **kwargs):
        self.writes.append((register, name, value))
        if register == "Lock":
            self.locks[name] = value
        elif register == "Max_Position_Limit":
            self.calibration[name]["range_max"] = value
        else:
            raise AssertionError(register)


class CalibrationRevisionTests(unittest.TestCase):
    def test_active_mappings_apply_overrides_without_changing_originals(self):
        phone = ArmMapping.load("phone", require_motion=False)
        light = ArmMapping.load("light", require_motion=False)
        phone_original = json.loads((CALIBRATION / "originals" / "arm_5B14111456.json").read_text())
        light_original = json.loads((CALIBRATION / "originals" / "arm_5A7A058801.json").read_text())

        # The phone elbow maximum was raised 3085 -> 3086 -> 3092 from measured
        # torque-off readings, each recorded with firmware evidence in the
        # registry. The overrides move; the original files must not.
        self.assertEqual(phone.raw_calibration["elbow_flex"]["range_max"], 3092)
        self.assertEqual(light.raw_calibration["wrist_flex"]["range_max"], 3204)
        self.assertEqual(light.raw_calibration["elbow_flex"]["range_max"], 3098)
        self.assertEqual(phone_original["elbow_flex"]["range_max"], 3085)
        self.assertEqual(light_original["wrist_flex"]["range_max"], 3199)

    def test_only_increased_maximum_is_accepted(self):
        original = values()
        configured = values()
        configured["elbow_flex"]["range_max"] = 3001
        self.assertEqual(endpoint_changes(original, configured)[0]["after"], 3001)
        configured["elbow_flex"]["range_min"] = 999
        with self.assertRaisesRegex(ValueError, "only an increased range_max"):
            endpoint_changes(original, configured)

    def test_revision_requires_torque_off_and_preserves_lock(self):
        original, configured = values(), values()
        configured["elbow_flex"]["range_max"] = 3001
        bus = Bus(original)
        with (
            patch(
                "takeone.motion.calibration_revision.specification",
                return_value=({"port": "COM9", "usb_serial": "serial"}, configured, "hash"),
            ),
            patch(
                "takeone.motion.calibration_revision.original_calibration",
                return_value=(original, {"calibration_id": "x"}),
            ),
        ):
            result = apply_revision(
                "phone",
                bus_factory=lambda device, raw: bus,
                identity_check=lambda port, serial: {"port": "COM9", "usb_serial": "serial"},
            )
        self.assertTrue(result["completed"])
        self.assertEqual(bus.calibration, configured)
        self.assertEqual(bus.locks["elbow_flex"], 1)
        self.assertEqual(
            bus.writes,
            [
                ("Lock", "elbow_flex", 0),
                ("Max_Position_Limit", "elbow_flex", 3001),
                ("Lock", "elbow_flex", 1),
            ],
        )

        bus = Bus(original, {**dict.fromkeys(JOINTS, 0), "elbow_flex": 1})
        with (
            patch(
                "takeone.motion.calibration_revision.specification",
                return_value=({"port": "COM9", "usb_serial": "serial"}, configured, "hash"),
            ),
            patch(
                "takeone.motion.calibration_revision.original_calibration",
                return_value=(original, {"calibration_id": "x"}),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "torque disabled"):
                apply_revision("phone", bus_factory=lambda device, raw: bus, identity_check=lambda *args: {})
        self.assertEqual(bus.writes, [])

    def test_original_loader_checks_preserved_hash(self):
        with TemporaryDirectory() as folder:
            from pathlib import Path

            root = Path(folder)
            source = json.dumps(values()).encode()
            (root / "original.json").write_bytes(source)
            (root / "registry.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "arms": {
                            "phone": {
                                "original_path": "original.json",
                                "original_sha256": hashlib.sha256(source).hexdigest(),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("takeone.motion.calibration_revision.CALIBRATION", root):
                self.assertEqual(original_calibration("phone")[0], values())


if __name__ == "__main__":
    unittest.main()
