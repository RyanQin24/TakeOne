"""Explicit offline plants and virtual time; never substitutes for a live device."""

import math

from takeone.clock import monotonic
from takeone.contracts import ArmObservation, joints
from takeone.protocol import uart_pair


class SimulatedCart:
    simulated = True
    connected = True

    def set_speed(self, left, right):
        return uart_pair(left, right)

    def close(self):
        self.connected = False


class SimulatedArm:
    """A lagging test plant, so replay actually exercises feedback error handling."""

    simulated = True
    connected = True

    def __init__(self, initial, clock=monotonic, response_s=0.03):
        self.q = self.goal = tuple(initial)
        self.clock, self.response_s = clock, response_s
        self.previous = clock()

    def _advance(self):
        now = self.clock()
        alpha = 1 - math.exp(-max(0, now - self.previous) / self.response_s)
        self.q = tuple(q + alpha * (g - q) for q, g in zip(self.q, self.goal))
        self.previous = now

    def read(self):
        self._advance()
        return ArmObservation(self.q, self.previous, "simulated")

    def validate(self, q_rad):
        joints(q_rad)

    def command(self, q_rad):
        self._advance()
        self.goal = joints(q_rad)
        return dict(source="simulated", target_rad=self.goal)

    def hold(self, observation):
        self.command(observation.q_rad)

    def disconnect(self):
        self.connected = False


class VirtualClock:
    def __init__(self):
        self.value = 100.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def software_limits():
    """Unmeasured envelope solely for injected software fault cases."""
    from takeone.motion.limits import ArmLimits

    return ArmLimits(
        (5.0,) * 5, (500.0,) * 5, (0.30,) * 5, (0.02,) * 5, (0.12,) * 5, (0.02,) * 5, (1000.0,) * 5
    )
