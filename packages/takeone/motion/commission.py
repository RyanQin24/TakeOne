"""Read actual arm state through LeRobot without motor-register writes.

This is the measurement entry point for model alignment. It never configures,
calibrates, enables/disables torque or moves an arm. Import and --help do no IO.
"""

import argparse
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from takeone.adapters.identity import identify_port
from takeone.calibration import ArmMapping, apply_range_overrides
from takeone.clock import monotonic
from takeone.config import file_hash, read_json
from takeone.contracts import JOINTS
from takeone.paths import CALIBRATION, CONFIGS, MODELS, REFERENCE

REGISTERS = (
    "Present_Position",
    "Goal_Position",
    "Torque_Enable",
    "Operating_Mode",
    "Phase",
    "Present_Voltage",
    "Present_Temperature",
)


def specification(role, profile):
    if role not in ("phone", "light") or profile not in ("windows", "linux"):
        raise ValueError("A named arm role and device profile are required")
    device = read_json(CONFIGS / f"devices/{profile}.json")["arms"][role]
    entry = read_json(CALIBRATION / "registry.json")["arms"][role]
    if not entry.get("original_path"):
        raise ValueError(f"{role}: original calibration is missing")
    original = (CALIBRATION / entry["original_path"]).resolve()
    if not original.is_relative_to(CALIBRATION.resolve()):
        raise ValueError("Original calibration path escapes calibration directory")
    if file_hash(original) != entry["original_sha256"]:
        raise ValueError(f"{role}: original calibration hash mismatch")
    # LeRobot originals are plain joint dictionaries, not TakeOne schema documents.
    original_raw = json.loads(original.read_text(encoding="utf-8"))
    mapping_path = (CALIBRATION / entry["mapping_path"]).resolve() if entry.get("mapping_path") else None
    if mapping_path is not None:
        if not mapping_path.is_relative_to(CALIBRATION.resolve()):
            raise ValueError("Mapping path escapes calibration directory")
        raw = apply_range_overrides(role, original_raw, read_json(mapping_path))
    else:
        raw = original_raw
    if set(raw) != set(JOINTS) or set(device["motor_ids"]) != set(JOINTS):
        raise ValueError("Expected exactly the five TakeOne joint names")
    ids = [raw[name]["id"] for name in JOINTS]
    if len(set(ids)) != 5 or any(type(id_) is not int or not 1 <= id_ <= 253 for id_ in ids):
        raise ValueError("Five distinct valid motor IDs are required")
    for name in JOINTS:
        value = raw[name]
        if value["id"] != device["motor_ids"][name]:
            raise ValueError(f"{role}: profile and original motor IDs differ")
        if not (0 <= value["range_min"] < value["range_max"] <= 4095) or value["drive_mode"] != 0:
            raise ValueError("Unsupported encoder calibration; no automatic repair")
    if device["calibration_id"] != entry["calibration_id"]:
        raise ValueError("Profile and original calibration IDs differ")
    return device, raw, entry["original_sha256"]


def make_bus(device, raw):
    # Lazy imports: no simulator, training or Placo dependencies are needed.
    from lerobot.motors import Motor, MotorCalibration, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    class ReadOnlyBus(FeetechMotorsBus):
        def reject_write(self, *args, **kwargs):
            raise PermissionError("Arm inspection prohibits motor-register writes")

        write = sync_write = _write = _sync_write = reject_write
        enable_torque = disable_torque = write_calibration = configure_motors = reject_write

    motors = {name: Motor(id_, "sts3215", MotorNormMode.DEGREES) for name, id_ in device["motor_ids"].items()}
    calibration = {name: MotorCalibration(**value) for name, value in raw.items()}
    return ReadOnlyBus(device["port"], motors, calibration=calibration)


def model_ranges(role):
    prefix = "cam" if role == "phone" else "light"
    tree = ET.parse(MODELS / "rig_tall.xml")
    result = {}
    for name in JOINTS:
        node = tree.find(f".//joint[@name='{prefix}_{name}']")
        if node is None:
            raise ValueError(f"Model joint missing: {name}")
        result[name] = [math.degrees(float(v)) for v in node.attrib["range"].split()]
    return result


def nominal_mapping(role, profile="windows"):
    """Derive the standard new-calibration convention; never mark it measured."""
    device, raw, original_hash = specification(role, profile)
    upstream = ET.parse(REFERENCE / "upstream/so101_new_calib.urdf").getroot()
    if upstream.get("name") != "so101_new_calib":
        raise ValueError("The nominal midpoint convention requires the SO101 new-calibration model")
    ranges = model_ranges(role)
    values = {}
    for name in JOINTS:
        saved = raw[name]
        midpoint = (saved["range_min"] + saved["range_max"]) / 2
        span = (saved["range_max"] - saved["range_min"]) * 180 / 4095
        bounds = [max(-span, ranges[name][0]), min(span, ranges[name][1])]
        if bounds[0] >= bounds[1]:
            raise ValueError("Encoder and model ranges have no nominal intersection")
        values[name] = dict(
            motor_id=saved["id"],
            encoder_midpoint=midpoint,
            nominal_axis_sign=1,
            nominal_servo_zero_offset_deg=0.0,
            nominal_range_intersection_deg=bounds,
            homing_reference_raw=2047,
            homing_reference_servo_deg=(2047 - midpoint) * 360 / 4095,
        )
    return dict(
        role=role,
        profile=profile,
        calibration_sha256=original_hash,
        reference_model_sha256=file_hash(REFERENCE / "rig_5dof.xml"),
        motor_ids=device["motor_ids"],
        convention="SO101 new calibration: model zero and calibrated degree zero at range midpoint",
        formula="model_rad = radians((raw_position - (range_min + range_max)/2) * 360/4095)",
        homing_note="Firmware homing is already applied. The initial Enter pose (raw 2047) need not equal the later range midpoint.",
        joints=values,
        axis_signs=[1] * 5,
        zero_offsets_deg=[0.0] * 5,
        safe_ranges_rad=None,
        verified=False,
        tool_transform_verified=False,
        status="Nominal standard-assembly mapping for physical comparison; not measured loaded limits",
        source="https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md",
    )


def inspect_arm(role, profile="windows", *, bus_factory=make_bus, identity_check=identify_port):
    result = dict(
        role=role,
        profile=profile,
        completed=False,
        serial_port_opened=False,
        motor_register_writes=False,
        motion_commands_sent=False,
        live_execution_allowed=False,
        scope="One sequential state snapshot; not a tracking, load or physical-pose qualification",
    )
    bus = None
    owned = False
    started = monotonic()
    try:
        device, raw, original_hash = specification(role, profile)
        result.update(
            identity=identity_check(device["port"], device["usb_serial"]),
            calibration_sha256=original_hash,
            reference_model_sha256=file_hash(REFERENCE / "rig_5dof.xml"),
            model_sha256=file_hash(MODELS / "rig_tall.xml"),
        )
        ranges = model_ranges(role)
        bus = bus_factory(device, raw)
        if bus.is_connected:
            raise ValueError("Inspection requires exclusive ownership of a closed arm bus")
        owned = True
        # The motor-bus handshake only pings/reads; follower.connect configures.
        bus.connect()
        result["serial_port_opened"] = True
        attached = {name: asdict(value) for name, value in bus.read_calibration().items()}
        matches = attached == raw
        entry = read_json(CALIBRATION / "registry.json")["arms"][role]
        original_path = CALIBRATION / entry["original_path"]
        original_raw = json.loads(original_path.read_text(encoding="utf-8"))
        result.update(
            firmware_calibration=attached,
            configured_calibration_matches_hardware=matches,
            original_matches_hardware=attached == original_raw,
            calibration_revision_active=raw != original_raw,
        )
        registers = {}
        for register in REGISTERS:
            values = bus.sync_read(register, normalize=False, num_retry=0)
            if set(values) != set(JOINTS) or any(type(v) is not int for v in values.values()):
                raise ValueError(f"Incomplete or invalid {register} read")
            registers[register] = values
        issues = [] if matches else ["Attached firmware calibration differs from the configured revision"]
        rows = {}
        for name in JOINTS:
            saved = raw[name]
            state = {register: registers[register][name] for register in REGISTERS}
            position = state["Present_Position"]
            supported_angle = not state["Phase"] & 16 and 0 <= position <= 4095
            if state["Operating_Mode"] != 0:
                issues.append(f"{name}: not in position mode")
            if state["Torque_Enable"] != 1:
                issues.append(f"{name}: torque-enabled hold is not established")
            if not supported_angle:
                issues.append(f"{name}: unsupported angle mode or raw position")
            if not saved["range_min"] <= position <= saved["range_max"]:
                issues.append(f"{name}: outside the configured encoder range")
            midpoint = (saved["range_min"] + saved["range_max"]) / 2
            rows[name] = dict(
                motor_id=saved["id"],
                registers_raw=state,
                servo_degrees=(position - midpoint) * 360 / 4095 if matches and supported_angle else None,
                model_radians_assuming_standard_calibration=(
                    math.radians((position - midpoint) * 360 / 4095) if matches and supported_angle else None
                ),
                configured_encoder_range=[saved["range_min"], saved["range_max"]],
                configured_servo_range_deg=[
                    (saved[key] - midpoint) * 360 / 4095 for key in ("range_min", "range_max")
                ],
                simulator_joint_range_deg=ranges[name],
                range_scope="Configured calibration range under the operator's mechanical-stop policy",
            )
        result.update(joints=rows, live_state_issues=issues, model_joint_radians=None)
        try:
            mapping = ArmMapping.load(role)
            if all(row["servo_degrees"] is not None for row in rows.values()):
                result["model_joint_radians"] = mapping.from_degrees(
                    {name + ".pos": rows[name]["servo_degrees"] for name in JOINTS}
                )
                result["mapping_status"] = "Registered mapping applied; no physical pose acceptance implied"
        except (ValueError, OSError, KeyError, TypeError) as error:
            result["mapping_status"] = str(error)
        result["completed"] = True
    except (Exception, KeyboardInterrupt) as error:
        result["error"] = f"{type(error).__name__}: {error}"
        causes = []
        cause = error.__cause__
        while cause is not None:
            causes.append(f"{type(cause).__name__}: {cause}")
            cause = cause.__cause__
        result["causes"] = causes
    finally:
        if owned and bus is not None and bus.is_connected:
            result["serial_port_opened"] = True
            try:
                # Closing a read-only inspection must preserve the existing torque state.
                bus.disconnect(disable_torque=False)
            except Exception as error:
                result.update(completed=False, close_error=f"{type(error).__name__}: {error}")
        result["duration_s"] = monotonic() - started
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="TakeOne arm state inspection through LeRobot; no motion")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("inspect", "Read calibration, raw joint positions and motor state; opens only arm ports"),
        ("nominal", "Derive the standard midpoint mapping from saved files; no ports opened"),
    ):
        action = sub.add_parser(name, help=help_text)
        action.add_argument("--role", choices=("phone", "light", "both"), default="both")
        action.add_argument("--profile", choices=("windows", "linux"), default="windows")
        action.add_argument(
            "--output", type=Path, required=True, help="New JSON file; existing files are preserved"
        )
    args = parser.parse_args(argv)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the report before hardware access; never overwrite a previous capture.
        with args.output.open("x", encoding="utf-8") as destination:
            roles = ("phone", "light") if args.role == "both" else (args.role,)
            action = inspect_arm if args.command == "inspect" else nominal_mapping
            arms = {role: action(role, args.profile) for role in roles}
            result = dict(
                schema=f"takeone.arm-{args.command}.v1",
                captured_utc=datetime.now(timezone.utc).isoformat(),
                completed=all(arm.get("completed", args.command == "nominal") for arm in arms.values()),
                arms=arms,
                motor_register_writes=False,
                motion_commands_sent=False,
                qualification_modified=False,
                output=str(args.output.resolve()),
            )
            destination.write(json.dumps(result, indent=2, allow_nan=False))
        print(json.dumps(result, indent=2, allow_nan=False))
        return int(not result["completed"])
    except (ValueError, OSError) as error:
        print(json.dumps(dict(completed=False, error=str(error))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
