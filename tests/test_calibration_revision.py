import hashlib
import json
import math
import unittest
from dataclasses import make_dataclass, replace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS
from takeone.motion.calibration_revision import apply_revision, endpoint_changes, original_calibration
from takeone.paths import CALIBRATION
from takeone.previs.start_pose import initial_counts

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
        # Replacement limits supplied after the light-arm motor upgrade.
        expected = {1: (619, 3313), 2: (1684, 4085), 3: (1308, 3511), 4: (547, 2879), 5: (1398, 4090)}
        self.assertEqual(
            {row["id"]: (row["range_min"], row["range_max"]) for row in light.raw_calibration.values()},
            expected,
        )
        self.assertEqual(phone_original["elbow_flex"]["range_max"], 3085)
        self.assertEqual(light_original["wrist_flex"]["range_max"], 3199)

    def test_upgraded_light_reset_matches_operator_confirmed_straight_wrist(self):
        from takeone.motion.play import Joints

        mapping = ArmMapping.load("light", require_motion=False)
        expected = dict(zip(JOINTS, (1880, 2900, 2472, 1669, 2629)))
        self.assertEqual(initial_counts(mapping), expected)
        angles = mapping.from_raw(expected)
        self.assertEqual(Joints("light").counts(angles), mapping.to_raw(angles))
        for name, actual in mapping.to_raw(angles).items():
            self.assertLessEqual(abs(actual - expected[name]), 1)
        # Other joints retain their prior angle mapping. The operator confirmed
        # the upgraded wrist is physically straight at its explicit reset count.
        self.assertAlmostEqual(angles[1], math.radians((2900 - 2885.5) * 360 / 4095))
        self.assertAlmostEqual(angles[3], 0)
        self.assertEqual(mapping.to_raw((0.0,) * 5), dict(zip(JOINTS, (1966, 2885, 2409, 1669, 2744))))

    def test_start_goals_fall_back_to_midpoints_and_return_independent_values(self):
        phone = ArmMapping.load("phone", require_motion=False)
        self.assertIsNone(phone.raw_goal_positions)
        self.assertEqual(initial_counts(phone), dict(zip(JOINTS, (2120, 1987, 1987, 2018, 2047))))
        light = ArmMapping.load("light", require_motion=False)
        self.assertEqual(
            initial_counts(replace(light, raw_goal_positions=None)),
            dict(zip(JOINTS, (1966, 2884, 2409, 1713, 2744))),
        )
        returned = initial_counts(light)
        returned["wrist_flex"] = 0
        self.assertEqual(initial_counts(light)["wrist_flex"], 1669)

    def test_invalid_start_goals_are_rejected_before_any_plan_or_hardware(self):
        mapping = ArmMapping.load("light", require_motion=False)
        for goals in ({}, [], {"wrist_flex": 1669}, {**mapping.raw_goal_positions, "unknown": 1000}):
            with self.subTest(goals=goals), self.assertRaisesRegex(ValueError, "all five named joints"):
                replace(mapping, raw_goal_positions=goals)
        for position in (True, 1669.0, "1669", 546, 2880):
            with self.subTest(position=position), self.assertRaisesRegex(ValueError, "wrist_flex"):
                replace(mapping, raw_goal_positions={**mapping.raw_goal_positions, "wrist_flex": position})

    def test_aiming_transition_starts_at_supplied_goals_and_preserves_exact_endpoints(self):
        from takeone.previs.start_pose import aiming_counts

        mapping = ArmMapping.load("light", require_motion=False)
        starts = {"light": initial_counts(mapping)}
        targets = {"light": dict(zip(JOINTS, (2000, 3000, 2500, 1500, 2700)))}
        self.assertEqual(aiming_counts(starts, targets, 0), starts)
        self.assertEqual(aiming_counts(starts, targets, 1), targets)
        for step in range(101):
            mapping.from_raw(aiming_counts(starts, targets, step / 100)["light"])

    def test_upgraded_light_ranges_accept_new_positions_and_reject_old_outside_values(self):
        mapping = ArmMapping.load("light", require_motion=False)
        positions = initial_counts(mapping)
        for name, raw in mapping.raw_calibration.items():
            for endpoint in (raw["range_min"], raw["range_max"]):
                with self.subTest(joint=name, endpoint=endpoint):
                    mapping.from_raw({**positions, name: endpoint})
            for outside in (raw["range_min"] - 1, raw["range_max"] + 1):
                with self.subTest(joint=name, outside=outside):
                    with self.assertRaisesRegex(ValueError, name):
                        mapping.from_raw({**positions, name: outside})
        # The 06:50:52 UTC snapshot now passes the real player's raw start check.
        from takeone.motion.play import Joints

        captured = dict(zip(JOINTS, (2972, 1685, 3509, 2599, 2630)))
        mapping.from_raw(captured)
        player = Joints("light")
        self.assertTrue(all(player.low[name] <= captured[name] <= player.high[name] for name in JOINTS))
        # Old accepted wrist-flex/roll positions are outside the updated limits.
        for name, old_position in (("wrist_flex", 3199), ("wrist_roll", 1000), ("shoulder_lift", 774)):
            with self.subTest(joint=name, old_position=old_position):
                with self.assertRaisesRegex(ValueError, name):
                    mapping.from_raw({**positions, name: old_position})

    def test_upgraded_light_does_not_reuse_old_physical_pose_confirmation(self):
        mapping = json.loads((CALIBRATION / "derived/light.json").read_text())
        self.assertFalse(mapping["verified"])
        self.assertFalse(mapping["visual_pose_match_confirmed"])
        self.assertFalse(mapping["firmware_calibration_verified"])
        self.assertIn("visual_pose_evidence", mapping["historical_evidence_before_motor_upgrade"])

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
