"""Catch mixed timer epochs and coarse Windows timing before hardware tests."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from takeone.adapters.lerobot_arm import LeRobotArm
from takeone.adapters.simulated import SimulatedArm, SimulatedCart
from takeone.cart.runtime import CartRunner, Timing
from takeone.execution import DEVICES, READY, Coordination
from takeone.motion.arm import ArmRunner
from takeone.motion.limits import ArmTiming


class MotionClockTests(unittest.TestCase):
    def test_default_motion_components_share_the_high_resolution_epoch(self):
        # Older Windows Python exposes a coarse clock with a different epoch.
        # Comparing its timestamps to performance-counter deadlines is invalid.
        with (
            patch("time.monotonic", return_value=9000.0),
            patch("time.perf_counter", return_value=100.025),
        ):
            simulated = SimulatedArm((0.0,) * 5)
            physical = LeRobotArm(None, None, {})
            cart = CartRunner(SimulatedCart(), Timing.load())
            runner = ArmRunner(simulated, "phone", None, None, ArmTiming.load())
            self.assertEqual(simulated.read().captured_monotonic_s, 100.025)
            self.assertEqual(physical.clock(), 100.025)
            self.assertEqual(cart.now(), 100.025)
            self.assertEqual(runner.now(), 100.025)

    def test_supervisor_and_peer_leases_use_the_same_epoch_as_motion(self):
        shared = Coordination(
            booted=None,
            epoch=SimpleNamespace(value=100.0),
            supervisor=SimpleNamespace(value=100.0),
            cancel=SimpleNamespace(is_set=lambda: False),
            heartbeat={role: SimpleNamespace(value=100.0) for role in DEVICES},
            state={role: SimpleNamespace(value=READY) for role in DEVICES},
        )
        with (
            patch("time.monotonic", return_value=9000.0),
            patch("time.perf_counter", return_value=100.025),
        ):
            shared.pulse("phone")
            self.assertEqual(shared.heartbeat["phone"].value, 100.025)
            shared.check("phone", 1.0, ArmTiming.load())
