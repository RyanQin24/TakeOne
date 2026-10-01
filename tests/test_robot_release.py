"""Release reporting must retain partial outcomes without touching hardware."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from takeone.motion import play


class ReleaseTests(unittest.TestCase):
    def test_port_failure_preserves_other_arm_readback(self):
        closed = []

        class FakeArm:
            def __init__(self, role, device, joints):
                self.role = role
                self.bus = self

            def open(self):
                if self.role == "light":
                    raise OSError("COM8 unavailable")

            def release(self):
                return []

            def read(self, register, name, **kwargs):
                self.assert_register(register)
                return 0

            def assert_register(self, register):
                assert register == "Torque_Enable"

            def close(self):
                closed.append(self.role)

        devices = {
            "arms": {
                "phone": {"port": "COM9", "usb_serial": "phone"},
                "light": {"port": "COM8", "usb_serial": "light"},
            }
        }
        with (
            patch.object(play, "read_json", return_value=devices),
            patch.object(play, "identify_port", return_value={}),
            patch.object(play, "Joints", return_value=object()),
            patch.object(play, "Arm", FakeArm),
        ):
            results = play.release_only("windows")

        self.assertEqual(closed, ["phone", "light"])
        self.assertTrue(results["phone"]["torque_off_confirmed"])
        self.assertEqual(results["phone"]["torque"], dict.fromkeys(play.JOINTS, 0))
        self.assertFalse(results["light"]["torque_off_confirmed"])
        self.assertIn("COM8 unavailable", results["light"]["errors"][0])

    def test_partial_release_returns_failure_and_prints_both_arms(self):
        results = {
            "phone": {"torque_off_confirmed": True, "errors": []},
            "light": {"torque_off_confirmed": False, "errors": ["COM8 unavailable"]},
        }
        output = io.StringIO()
        with patch.object(play, "release_only", return_value=results), contextlib.redirect_stdout(output):
            exit_code = play.main(["--release"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue()), results)


if __name__ == "__main__":
    unittest.main()
