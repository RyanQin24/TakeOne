"""Preview policy read through arm commissioning configuration, never motor capability."""

import math
from dataclasses import dataclass

from takeone.config import finite, read_json
from takeone.paths import CONFIGS


@dataclass(frozen=True)
class MotionPolicy:
    cart_pace_max_m_s: float
    arm_counts_per_tick: int
    arm_period_s: float
    aiming_rate_deg_s: float


def motion_policy():
    from takeone.motion.studio_plan import ARM_PERIOD

    config = read_json(CONFIGS / "arm-execution.json")
    value = config["previs_policy"]
    policy = MotionPolicy(**{k: value[k] for k in MotionPolicy.__dataclass_fields__})
    for key in ("cart_pace_max_m_s", "arm_period_s", "aiming_rate_deg_s"):
        if finite(getattr(policy, key), key) <= 0:
            raise ValueError(f"Preview policy {key} must be positive.")
    if type(policy.arm_counts_per_tick) is not int or policy.arm_counts_per_tick < 1:
        raise ValueError("Preview trajectory step needs positive encoder counts.")
    if policy.arm_period_s != config["period_s"] or policy.arm_period_s != ARM_PERIOD:
        raise ValueError("Preview, commissioning and the motion-plan arm periods must match.")
    rate = policy.arm_counts_per_tick * math.tau / 4095 / policy.arm_period_s
    if rate > min(config["commissioning_limits"]["velocity_rad_s"]):
        raise ValueError("Preview trajectory exceeds commissioning velocity policy.")
    return policy
