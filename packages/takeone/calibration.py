"""Explicit URDF-radian to calibrated-servo-degree mapping with provenance gates."""

import math
from dataclasses import dataclass

from .config import file_hash, finite, read_json
from .contracts import JOINTS, joints
from .paths import CALIBRATION, CONFIGS, REFERENCE

# One STS3215 encoder count, 0.088 degrees.
COUNT_RAD = math.radians(360 / 4095)
# Three counts. Wide enough for spline overshoot at an active bound, far too
# small to hide a real reach problem.
ENCODE_TOLERANCE_RAD = 3 * COUNT_RAD


def apply_range_overrides(role, raw, mapping):
    """Return the configured calibration while preserving the source dictionary."""
    import copy

    configured = copy.deepcopy(raw)
    overrides = mapping.get("raw_range_overrides", {})
    if not isinstance(overrides, dict) or not set(overrides).issubset(JOINTS):
        raise ValueError(f"{role}: invalid calibration range overrides")
    for name, changes in overrides.items():
        if (
            not isinstance(changes, dict)
            or not changes
            or not set(changes).issubset({"range_min", "range_max"})
        ):
            raise ValueError(f"{role}/{name}: invalid calibration range override")
        for key, value in changes.items():
            if type(value) is not int:
                raise ValueError(f"{role}/{name}: calibration range override must be an integer")
            configured[name][key] = value
        if not 0 <= configured[name]["range_min"] < configured[name]["range_max"] <= 4095:
            raise ValueError(f"{role}/{name}: calibration range override is invalid")
    return configured


@dataclass(frozen=True)
class ArmMapping:
    signs: tuple
    offsets_deg: tuple
    safe_ranges_rad: tuple
    raw_calibration: dict
    limit_margin_deg: float = 0.0
    raw_goal_positions: dict | None = None

    def __post_init__(self):
        if len(self.signs) != 5 or any(type(s) not in (int, float) or s not in (-1, 1) for s in self.signs):
            raise ValueError("Five axis signs required")
        if (
            len(self.offsets_deg) != 5
            or len(self.safe_ranges_rad) != 5
            or set(self.raw_calibration) != set(JOINTS)
        ):
            raise ValueError("Incomplete joint mapping")
        for offset, bounds in zip(self.offsets_deg, self.safe_ranges_rad):
            finite(offset, "Zero offset")
            if len(bounds) != 2 or finite(bounds[0], "Lower limit") >= finite(bounds[1], "Upper limit"):
                raise ValueError("Invalid operating joint limits")
        for name in JOINTS:
            raw = self.raw_calibration[name]
            if not (0 <= raw["range_min"] < raw["range_max"] <= 4095):
                raise ValueError("Invalid calibration encoder range")
        if self.raw_goal_positions is not None:
            if not isinstance(self.raw_goal_positions, dict) or set(self.raw_goal_positions) != set(JOINTS):
                raise ValueError("Starting goals require all five named joints")
            for name, position in self.raw_goal_positions.items():
                raw = self.raw_calibration[name]
                if type(position) is not int or not raw["range_min"] <= position <= raw["range_max"]:
                    raise ValueError(f"{name}: starting goal must be an integer inside its calibration")

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
        range_source = mapping.get("range_source", "measured")
        if range_source not in ("calibration", "measured"):
            raise ValueError(f"{role}: unknown operating range source")
        if range_source == "calibration" and mapping.get("safe_ranges_rad") is not None:
            raise ValueError(f"{role}: calibration-defined limits cannot have a second range table")
        if require_motion and mapping.get("verified") is not True:
            raise ValueError(f"{role}: verified model alignment is required")
        if require_motion and range_source == "measured" and mapping.get("safe_ranges_rad") is None:
            raise ValueError(f"{role}: operating ranges are required for the measured range policy")
        if mapping["reference_model_sha256"] != file_hash(REFERENCE / "rig_5dof.xml"):
            raise ValueError("Mapping is for a different reference model")
        import json

        raw = apply_range_overrides(role, json.loads(source.read_text(encoding="utf-8")), mapping)
        # Keep the planner off the mechanical stops. Commanding the exact end of
        # travel stalls a gravity-loaded joint against its own hard limit, which
        # is what dropped the light arm to 773 counts mid-shot.
        margin_deg = mapping.get("limit_margin_deg", 0.0)
        if isinstance(margin_deg, bool) or not isinstance(margin_deg, (int, float)):
            raise ValueError(f"{role}: limit margin must be a number of degrees")
        if not 0 <= margin_deg <= 30:
            raise ValueError(f"{role}: limit margin must be between 0 and 30 degrees")
        bounds = mapping["safe_ranges_rad"]
        if bounds is None:
            # The operator may select the original calibration as the operating
            # range. Diagnostic loading also uses it when measured ranges are absent.
            bounds = []
            for name, sign, offset in zip(JOINTS, mapping["axis_signs"], mapping["zero_offsets_deg"]):
                span = (raw[name]["range_max"] - raw[name]["range_min"]) * 180 / 4095
                usable = max(span - margin_deg, span / 2)
                bounds.append(sorted(math.radians((v - offset) / sign) for v in (-usable, usable)))
        return cls(
            tuple(mapping["axis_signs"]),
            tuple(mapping["zero_offsets_deg"]),
            tuple(tuple(b) for b in bounds),
            raw,
            float(margin_deg),
            mapping.get("raw_goal_positions"),
        )

    def to_degrees(self, q_rad):
        values = joints(q_rad)
        result = {}
        for name, q, sign, offset, bounds in zip(
            JOINTS, values, self.signs, self.offsets_deg, self.safe_ranges_rad
        ):
            if not bounds[0] <= q <= bounds[1]:
                raise ValueError(f"{name}: outside configured operating range")
            degrees = math.degrees(q) * sign + offset
            raw = self.raw_calibration[name]
            midpoint = (raw["range_min"] + raw["range_max"]) / 2
            target = int(degrees * 4095 / 360 + midpoint)
            if not raw["range_min"] <= target <= raw["range_max"]:
                raise ValueError(f"{name}: exceeds encoder calibration")
            encoded_q = math.radians(((target - midpoint) * 360 / 4095 - offset) / sign)
            if not bounds[0] <= encoded_q <= bounds[1]:
                raise ValueError(f"{name}: encoder quantization leaves configured operating range")
            # Firmware homing offsets already apply to Present/Goal_Position.
            result[name + ".pos"] = degrees
        return result

    def from_degrees(self, observation):
        return tuple(
            math.radians((finite(observation[n + ".pos"], n) - offset) / sign)
            for n, offset, sign in zip(JOINTS, self.offsets_deg, self.signs)
        )

    def encode(self, q_rad):
        """Encode to counts the way the hardware adapter does, absorbing curve slop.

        The IK settles a waypoint exactly onto an operating bound, and the fitted
        joint curve then overshoots that waypoint by a fraction of an encoder
        count. The resulting integer count is still inside the calibration, so
        this is numerical noise, not a reach violation: pull it back onto the
        bound, exactly as the real adapter clamps. Anything past the tolerance is
        a genuine violation and still raises.
        """
        values = joints(q_rad)
        settled = []
        for name, q, bounds in zip(JOINTS, values, self.safe_ranges_rad):
            if not bounds[0] - ENCODE_TOLERANCE_RAD <= q <= bounds[1] + ENCODE_TOLERANCE_RAD:
                raise ValueError(f"{name}: outside configured operating range")
            # Settle a whole count inside, not onto the bound itself. int() drops
            # up to one count, so a value sitting exactly on the bound can quantize
            # back outside it; one count of inset makes that impossible.
            settled.append(min(bounds[1] - COUNT_RAD, max(bounds[0] + COUNT_RAD, q)))
        return self.to_raw(tuple(settled))

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
