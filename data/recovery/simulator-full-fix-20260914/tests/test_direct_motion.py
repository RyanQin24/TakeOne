import json
import tempfile
import unittest
from pathlib import Path

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS
from takeone.direct import PERIOD_S, calibrated_positions, direct_shot
from takeone.motion.direct import load_direct_plan


class DirectMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shot = direct_shot({"duration": 2.0, "armTravel": 0.2, "lightTravel": 0.2})

    def test_starts_and_finishes_at_each_calibrated_raw_midpoint(self):
        for role in ("phone", "light"):
            _, ranges, midpoints = calibrated_positions(role)
            self.assertEqual(self.shot["frames"][0]["rawByRole"][role], midpoints)
            self.assertEqual(self.shot["frames"][-1]["rawByRole"][role], midpoints)
            for name in JOINTS:
                lower, upper = ranges[name]
                self.assertEqual(midpoints[name], int((lower + upper) / 2))

    def test_raw_counts_are_the_source_and_round_trip_through_real_adapter_mapping(self):
        for role, q_slice in (("phone", slice(3, 8)), ("light", slice(8, 13))):
            mapping = ArmMapping.load(role, require_motion=False)
            observed = set()
            for frame in self.shot["frames"]:
                raw = frame["rawByRole"][role]
                self.assertEqual(mapping.to_raw(frame["q"][q_slice]), raw)
                observed.add(tuple(raw[name] for name in JOINTS))
            self.assertGreater(len(observed), 10)

    def test_no_ik_and_cart_moves_forward_while_both_arms_pan(self):
        self.assertEqual(self.shot["solver"], {"mode": "none", "solves": 0, "failed": 0})
        self.assertNotIn("joint_curve", self.shot)
        self.assertEqual(self.shot["motorCommands"][0]["wire"], "0.04,0.04\n")
        self.assertEqual(self.shot["motorCommands"][-1]["wire"], "0.00,0.00\n")
        self.assertNotEqual(self.shot["frames"][0]["q"][:2], self.shot["frames"][-1]["q"][:2])
        direct = direct_shot({"duration": 2.0})
        for role in ("phone", "light"):
            midpoint = direct["calibration"][role]["midpoints"]
            self.assertGreater(
                len({frame["rawByRole"][role]["shoulder_pan"] for frame in direct["frames"]}),
                10,
            )
            for name in JOINTS[1:]:
                self.assertTrue(
                    all(frame["rawByRole"][role][name] == midpoint[name] for frame in direct["frames"])
                )
        gaps = [b["time_s"] - a["time_s"] for a, b in zip(self.shot["frames"], self.shot["frames"][1:])]
        self.assertLessEqual(max(gaps), PERIOD_S + 1e-12)

    def test_export_is_accepted_only_when_it_matches_current_calibration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "direct.json"
            path.write_text(json.dumps(self.shot), encoding="utf-8")
            self.assertEqual(load_direct_plan(path)["planId"], self.shot["planId"])
            changed = json.loads(path.read_text(encoding="utf-8"))
            changed["calibration"]["phone"]["midpoints"]["shoulder_pan"] += 1
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                load_direct_plan(path)


if __name__ == "__main__":
    unittest.main()
