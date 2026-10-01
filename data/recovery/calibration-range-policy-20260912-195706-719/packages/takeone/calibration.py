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
    def load(cls, role, *, require_motion=True):
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
        if require_motion and (mapping.get("verified") is not True or mapping.get("safe_ranges_rad") is None):
            raise ValueError(f"{role}: measured model alignment and loaded cable-safe ranges are required")
        if mapping["reference_model_sha256"] != file_hash(REFERENCE / "rig_5dof.xml"):
            raise ValueError("Mapping is for a different reference model")
        import json

        raw = json.loads(source.read_text(encoding="utf-8"))
        bounds = mapping["safe_ranges_rad"]
        if bounds is None:
            # Encoder arithmetic only. These are not cable-safe operating limits.
            bounds = []
            for name, sign, offset in zip(JOINTS, mapping["axis_signs"], mapping["zero_offsets_deg"]):
                span = (raw[name]["range_max"] - raw[name]["range_min"]) * 180 / 4095
                bounds.append(sorted(math.radians((v - offset) / sign) for v in (-span, span)))
        return cls(
            tuple(mapping["axis_signs"]),
            tuple(mapping["zero_offsets_deg"]),
            tuple(tuple(b) for b in bounds),
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
            encoded_q = math.radians(((target - midpoint) * 360 / 4095 - offset) / sign)
            if not bounds[0] <= encoded_q <= bounds[1]:
                raise ValueError(f"{name}: encoder quantization leaves measured safe range")
            # Firmware homing offsets already apply to Present/Goal_Position.
            result[name + ".pos"] = degrees
        return result

    def from_degrees(self, observation):
        return tuple(
            math.radians((finite(observation[n + ".pos"], n) - offset) / sign)
            for n, offset, sign in zip(JOINTS, self.offsets_deg, self.signs)
        )

    def to_raw(self, q_rad):
        """Single conversion, identical int truncation to installed LeRobot degree mode."""
        degrees = self.to_degrees(q_rad)
        return {
            n: int(
                degrees[n + ".pos"] * 4095 / 360
                + (self.raw_calibration[n]["range_min"] + self.raw_calibration[n]["range_max"]) / 2
            )
            for n in JOINTS
        }

    def from_raw(self, positions):
        if set(positions) != set(JOINTS):
            raise ValueError("All five raw encoder observations are required")
        degrees = {}
        for name in JOINTS:
            raw = self.raw_calibration[name]
            position = positions[name]
            if type(position) is not int or not raw["range_min"] <= position <= raw["range_max"]:
                raise ValueError(f"{name}: invalid or out-of-range measured encoder")
            degrees[name + ".pos"] = (position - (raw["range_min"] + raw["range_max"]) / 2) * 360 / 4095
        return self.from_degrees(degrees)


def hardware_blockers(profile="windows"):
    """Capability inventory only; exact-plan preflight validates the supporting evidence."""
    from .motion.limits import measured_limits

    blockers = []
    devices = read_json(CONFIGS / "devices" / f"{profile}.json")
    if devices.get("hardware_enabled") is not True:
        blockers.append(f"{profile}: device profile is not enabled for physical execution")
    for role in ("phone", "light", "cart"):
        device = devices["cart"] if role == "cart" else devices["arms"][role]
        if not device.get("port") or not device.get("usb_serial"):
            blockers.append(f"{role}: an explicit port and USB serial identity are required")
    if read_json(CONFIGS / "cart-response.json")["mode"] != "measured_table":
        blockers.append("Independent loaded left/right wire-command response measurements are missing")
    evidence = read_json(CONFIGS / "motion-evidence.json")
    for capability, description in evidence["required"].items():
        if not isinstance(evidence["records"].get(capability), dict):
            blockers.append(description)
    for role in ("phone", "light"):
        for check in (ArmMapping.load, measured_limits):
            try:
                check(role)
            except (ValueError, OSError, KeyError, TypeError) as error:
                blockers.append(str(error))
    return blockers
