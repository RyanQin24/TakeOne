"""Explicit URDF-radian to calibrated-servo-degree mapping with provenance gates."""

import math
from dataclasses import dataclass

from .config import file_hash, finite, read_json
from .contracts import JOINTS, joints
from .paths import CALIBRATION, CONFIGS, REFERENCE


@dataclass(frozen=True)
class ArmMapping:
    signs: tuple
    offsets_deg: tuple
    safe_ranges_rad: tuple
    raw_calibration: dict

    def __post_init__(self):
        if len(self.signs) != 5 or any(type(s) not in (int, float) or s not in (-1, 1) for s in self.signs):
            raise ValueError("Five measured axis signs required")
        if (
            len(self.offsets_deg) != 5
            or len(self.safe_ranges_rad) != 5
            or set(self.raw_calibration) != set(JOINTS)
        ):
            raise ValueError("Incomplete joint mapping")
        for offset, bounds in zip(self.offsets_deg, self.safe_ranges_rad):
            finite(offset, "Zero offset")
            if len(bounds) != 2 or finite(bounds[0], "Lower limit") >= finite(bounds[1], "Upper limit"):
                raise ValueError("Invalid measured joint limits")
        for name in JOINTS:
            raw = self.raw_calibration[name]
            if not (0 <= raw["range_min"] < raw["range_max"] <= 4095):
                raise ValueError("Invalid calibration encoder range")

    @classmethod
    def load(cls, role):
        registry = read_json(CALIBRATION / "registry.json")
        if role not in registry["arms"]:
            raise ValueError("Unknown arm role")
        entry = registry["arms"][role]
        if not entry.get("original_path"):
            raise ValueError(f"{role}: original calibration is missing locally")
        source = (CALIBRATION / entry["original_path"]).resolve()
        if not source.is_relative_to(CALIBRATION.resolve()) or file_hash(source) != entry["original_sha256"]:
            raise ValueError(f"{role}: original calibration hash/path mismatch")
        mapping_path = (CALIBRATION / entry["mapping_path"]).resolve()
        if not mapping_path.is_relative_to(CALIBRATION.resolve()):
            raise ValueError("Mapping path escapes calibration directory")
        mapping = read_json(mapping_path)
        if mapping.get("role") != role:
            raise ValueError(f"{role}: alignment file names a different arm role")
        if mapping.get("verified") is not True or mapping.get("tool_transform_verified") is not True:
            raise ValueError(f"{role}: model alignment or tool transform unverified")
        if mapping["reference_model_sha256"] != file_hash(REFERENCE / "rig_5dof.xml"):
            raise ValueError("Mapping is for a different reference model")
        import json

        raw = json.loads(source.read_text(encoding="utf-8"))
        return cls(
            tuple(mapping["axis_signs"]),
            tuple(mapping["zero_offsets_deg"]),
            tuple(mapping["safe_ranges_rad"]),
            raw,
        )

    def to_degrees(self, q_rad):
        values = joints(q_rad)
        result = {}
        for name, q, sign, offset, bounds in zip(
            JOINTS, values, self.signs, self.offsets_deg, self.safe_ranges_rad
        ):
            if not bounds[0] <= q <= bounds[1]:
                raise ValueError(f"{name}: outside measured safe range")
            degrees = math.degrees(q) * sign + offset
            raw = self.raw_calibration[name]
            midpoint = (raw["range_min"] + raw["range_max"]) / 2
            target = int(degrees * 4095 / 360 + midpoint)
            if not raw["range_min"] <= target <= raw["range_max"]:
                raise ValueError(f"{name}: exceeds encoder calibration")
            # Firmware homing offsets already apply to Present/Goal_Position.
            result[name + ".pos"] = degrees
        return result

    def from_degrees(self, observation):
        return tuple(
            math.radians((finite(observation[n + ".pos"], n) - offset) / sign)
            for n, offset, sign in zip(JOINTS, self.offsets_deg, self.signs)
        )


def hardware_blockers():
    blockers = []
    qualification = read_json(CONFIGS / "qualification.json")
    required = (
        "hardware_enabled",
        "device_identity_verified",
        "loaded_arm_limits_verified",
        "cart_speed_and_stopping_verified",
        "firmware_timeout_verified",
        "independent_stop_procedure_verified",
        "payload_support_and_hold_verified",
        "combined_start_stop_trajectory_verified",
    )
    for key in required:
        if qualification.get(key) is not True:
            blockers.append(key.replace("_", " "))
    for role in ("phone", "light"):
        try:
            ArmMapping.load(role)
        except (ValueError, OSError, KeyError, TypeError) as error:
            blockers.append(str(error))
    return blockers
