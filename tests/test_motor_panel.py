"""The per-motor panel: real calibration in, posed links out. No IK, no hardware."""

import unittest

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS
from takeone.motors import motor_table, pose_from_counts

ROLES = ("phone", "light")


class MotorTableTests(unittest.TestCase):
    def setUp(self):
        self.table = motor_table()

    def test_every_motor_reports_the_installed_calibration(self):
        for role in ROLES:
            mapping = ArmMapping.load(role, require_motion=False)
            for name in JOINTS:
                joint = self.table["roles"][role]["joints"][name]
                raw = mapping.raw_calibration[name]
                self.assertEqual(joint["id"], raw["id"])
                self.assertEqual(joint["min"], raw["range_min"])
                self.assertEqual(joint["max"], raw["range_max"])
                self.assertLess(joint["min"], joint["midpoint"])
                self.assertLess(joint["midpoint"], joint["max"])

    def test_operator_range_overrides_reach_the_panel(self):
        # The phone keeps its measured revision; the light uses the replacement
        # ranges supplied after its motor upgrade.
        self.assertEqual(self.table["roles"]["phone"]["joints"]["elbow_flex"]["max"], 3092)
        self.assertEqual(self.table["roles"]["light"]["joints"]["wrist_flex"]["min"], 547)
        self.assertEqual(self.table["roles"]["light"]["joints"]["wrist_flex"]["max"], 2879)
        self.assertEqual(self.table["roles"]["light"]["joints"]["shoulder_lift"]["min"], 1684)

    def test_joint_order_matches_the_hardware_contract(self):
        self.assertEqual(self.table["joint_order"], list(JOINTS))


class PoseTests(unittest.TestCase):
    def setUp(self):
        self.table = motor_table()

    def test_default_pose_sits_at_every_calibrated_midpoint(self):
        pose = pose_from_counts()
        for role in ROLES:
            self.assertEqual(pose["motors"][role], self.table["roles"][role]["midpoints"])
            for value in pose["degreesFromMidpoint"][role].values():
                self.assertEqual(value, 0.0)

    def test_a_motor_out_of_range_is_clamped_rather_than_refused(self):
        pose = pose_from_counts({"motors": {"phone": {"elbow_flex": 99999, "shoulder_pan": -5000}}})
        joints = self.table["roles"]["phone"]["joints"]
        self.assertEqual(pose["motors"]["phone"]["elbow_flex"], joints["elbow_flex"]["max"])
        self.assertEqual(pose["motors"]["phone"]["shoulder_pan"], joints["shoulder_pan"]["min"])

    def test_counts_agree_with_what_the_hardware_player_would_send(self):
        counts = {"shoulder_pan": 2400, "shoulder_lift": 1800, "elbow_flex": 2100}
        pose = pose_from_counts({"motors": {"phone": counts}})
        mapping = ArmMapping.load("phone", require_motion=False)
        # from_raw here and to_raw on the robot are the same mapping, so a count
        # shown in the panel is the count written to Goal_Position.
        self.assertEqual(mapping.to_raw(mapping.from_raw(pose["motors"]["phone"])), pose["motors"]["phone"])
        self.assertEqual(len(pose["jointRadians"]["phone"]), 5)

    def test_moving_one_motor_moves_the_tool_and_solves_no_ik(self):
        low = pose_from_counts({"motors": {"phone": {"shoulder_pan": 1500}}})
        high = pose_from_counts({"motors": {"phone": {"shoulder_pan": 2800}}})
        self.assertEqual(low["ikSolves"], 0)
        self.assertFalse(low["hardwareCommandsSent"])
        moved = max(abs(a - b) for a, b in zip(low["frame"]["camera"]["pos"], high["frame"]["camera"]["pos"]))
        self.assertGreater(moved, 0.1, "the phone shoulder pan must swing the camera")

    def test_the_light_arm_is_independent_of_the_phone_arm(self):
        base = pose_from_counts()
        moved = pose_from_counts({"motors": {"light": {"shoulder_pan": 2600}}})
        self.assertEqual(base["frame"]["camera"]["pos"], moved["frame"]["camera"]["pos"])
        self.assertNotEqual(base["frame"]["light"]["pos"], moved["frame"]["light"]["pos"])

    def test_unknown_motors_and_light_types_are_explicit_errors(self):
        with self.assertRaises(ValueError):
            pose_from_counts({"motors": {"phone": {"not_a_joint": 2000}}})
        with self.assertRaises(ValueError):
            pose_from_counts({"lightType": "spotlight"})
        with self.assertRaises(ValueError):
            pose_from_counts({"motors": {"phone": {"shoulder_pan": "middle"}}})


if __name__ == "__main__":
    unittest.main()
