"""Elevated staging moves the actor and aim together, never the cart or a fake staircase."""

import unittest

from takeone.previs.channels import ramp, validate_channels
from takeone.previs.program import subject
from takeone.previs.templates import defaults_for


class PlatformStagingTests(unittest.TestCase):
    def test_constant_platform_height_reaches_body_and_face(self):
        program = defaults_for("static")
        program["channels"] = validate_channels({"actor_position_m": ramp([0, 0, 0.6], [0, 0, 0.6])})
        for t in (0, 0.5, 1):
            actor, face = subject(program, t, 1.72)
            self.assertEqual(actor["position_m"][2], 0.6)
            self.assertAlmostEqual(face[2], 0.6 + 1.72 * 0.925)
            self.assertFalse(actor["walking"])

    def test_walking_stays_on_platform_and_retains_bob(self):
        program = defaults_for("static")
        program["channels"] = validate_channels({"actor_position_m": ramp([0, 0, 0.6], [1, 0, 0.6])})
        actor, face = subject(program, 0.4, 1.72)
        self.assertTrue(actor["walking"])
        self.assertGreaterEqual(actor["position_m"][2], 0.6)
        self.assertAlmostEqual(face[2] - actor["position_m"][2], 1.72 * 0.925)

    def test_climbing_and_invalid_surfaces_are_rejected(self):
        for a, b in ((0, 0.6), (-0.1, -0.1), (1.6, 1.6)):
            with self.assertRaisesRegex(ValueError, "one level surface"):
                validate_channels({"actor_position_m": ramp([0, 0, a], [0, 0, b])})

    def test_ground_level_result_is_unchanged(self):
        program = defaults_for("static")
        actor, face = subject(program, 0.5, 1.72)
        self.assertEqual(actor["position_m"], [0, 0, 0])
        self.assertAlmostEqual(face[2], 1.72 * 0.925)

    def test_held_cart_with_custom_arms_is_not_labelled_locked_camera(self):
        from takeone.previs.sequence import movement_name
        from takeone.previs.templates import BY_ID

        settings = defaults_for("static")
        self.assertEqual(movement_name(settings), BY_ID["static"]["name"])
        settings.update(
            channels=dict(camera_target_m=ramp([0, 0, 1.6], [0, 1, 1.6]), light_height_m=ramp(1.4, 1.6)),
            camera=dict(keyframes=[dict(at=0, focal_mm=75), dict(at=1, focal_mm=85)]),
        )
        self.assertEqual(movement_name(settings), "Held cart · custom phone / light / lens")
