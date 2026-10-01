"""Shared calibrated reset and aiming transition, expressed in exact encoder counts."""

import math

from takeone.contracts import JOINTS

from .policy import motion_policy


def initial_counts(mapping):
    return {name: (raw["range_min"] + raw["range_max"]) // 2 for name, raw in mapping.raw_calibration.items()}


def aiming_duration(starts, targets, period_s=0.04):
    span = max(abs(targets[r][n] - starts[r][n]) for r in starts for n in JOINTS) * 360 / 4095
    return math.ceil(max(2.0, math.pi * span / (2 * motion_policy().aiming_rate_deg_s)) / period_s) * period_s


def aiming_counts(starts, targets, fraction):
    u = max(0.0, min(1.0, fraction))
    eased = (1 - math.cos(math.pi * u)) / 2
    return {
        r: {n: round(starts[r][n] + (targets[r][n] - starts[r][n]) * eased) for n in JOINTS} for r in starts
    }
