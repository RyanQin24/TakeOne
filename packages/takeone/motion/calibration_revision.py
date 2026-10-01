"""Apply explicitly configured endpoint revisions without recalibrating an arm."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from takeone.adapters.identity import identify_port
from takeone.clock import monotonic
from takeone.config import file_hash, read_json
from takeone.contracts import JOINTS
from takeone.paths import CALIBRATION

from .commission import specification


def original_calibration(role):
    entry = read_json(CALIBRATION / "registry.json")["arms"][role]
    path = (CALIBRATION / entry["original_path"]).resolve()
    if not path.is_relative_to(CALIBRATION.resolve()) or file_hash(path) != entry["original_sha256"]:
        raise ValueError(f"{role}: original calibration hash/path mismatch")
    return json.loads(path.read_text(encoding="utf-8")), entry


def endpoint_changes(original, configured):
    changes = []
    if set(original) != set(JOINTS) or set(configured) != set(JOINTS):
        raise ValueError("Exactly five named joints are required")
    for name in JOINTS:
        if set(original[name]) != set(configured[name]):
            raise ValueError(f"{name}: calibration fields changed")
        for key in original[name]:
            before, after = original[name][key], configured[name][key]
            if before == after:
                continue
            if key != "range_max" or type(after) is not int or not before < after <= 4095:
                raise ValueError(f"{name}: only an increased range_max revision is supported")
            changes.append(dict(joint=name, register="Max_Position_Limit", before=before, after=after))
    if not changes:
        raise ValueError("No endpoint revision is configured")
    return changes


def make_bus(device, calibration):
    from lerobot.motors import Motor, MotorCalibration, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    motors = {
        name: Motor(motor_id, "sts3215", MotorNormMode.DEGREES)
        for name, motor_id in device["motor_ids"].items()
    }
    values = {name: MotorCalibration(**row) for name, row in calibration.items()}
    return FeetechMotorsBus(device["port"], motors, calibration=values)


def apply_revision(
    role, profile="windows", *, requested_calibration=None, bus_factory=make_bus, identity_check=identify_port
):
    """Write only reviewed maximum endpoints while torque is already disabled."""
    device, configured, original_hash = specification(role, profile)
    original, entry = original_calibration(role)
    baseline = original if requested_calibration is None else configured
    configured = configured if requested_calibration is None else requested_calibration
    changes = endpoint_changes(baseline, configured)
    report = dict(
        schema="takeone.calibration-endpoint-revision.v1",
        role=role,
        profile=profile,
        calibration_id=entry["calibration_id"],
        original_sha256=original_hash,
        requested_changes=changes,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed=False,
        torque_commands_sent=False,
        goal_position_commands_sent=False,
        writes=[],
    )
    report["identity"] = identity_check(device["port"], device["usb_serial"])
    bus = bus_factory(device, baseline)
    initial_locks = {}
    try:
        if bus.is_connected:
            raise ValueError("Endpoint revision requires exclusive ownership of a closed bus")
        bus.connect()
        report["serial_port_opened"] = True
        torque = bus.sync_read("Torque_Enable", normalize=False, num_retry=0)
        modes = bus.sync_read("Operating_Mode", normalize=False, num_retry=0)
        phases = bus.sync_read("Phase", normalize=False, num_retry=0)
        report.update(torque_enable_before=torque, operating_mode=modes, phase=phases)
        if set(torque) != set(JOINTS) or any(value != 0 for value in torque.values()):
            raise RuntimeError("All five motors must already have torque disabled")
        if any(modes[name] != 0 or phases[name] & 16 for name in JOINTS):
            raise RuntimeError("All five motors must use ordinary position mode")
        attached = {name: asdict(value) for name, value in bus.read_calibration().items()}
        report["firmware_before"] = attached
        allowed = {(row["joint"], row["register"]): row for row in changes}
        for name in JOINTS:
            for key, expected in baseline[name].items():
                if key == "range_max" and (name, "Max_Position_Limit") in allowed:
                    values = {expected, configured[name][key]}
                    if attached[name][key] not in values:
                        raise RuntimeError(f"{name}: firmware maximum is neither the baseline nor revision")
                elif attached[name][key] != expected:
                    raise RuntimeError(f"{name}/{key}: unrelated firmware calibration differs")
        for change in changes:
            name = change["joint"]
            if attached[name]["range_max"] == change["after"]:
                report["writes"].append({**change, "status": "already_applied"})
                continue
            initial_lock = bus.read("Lock", name, normalize=False, num_retry=0)
            if initial_lock not in (0, 1):
                raise RuntimeError(f"{name}: invalid EEPROM lock state")
            initial_locks[name] = initial_lock
            if initial_lock:
                bus.write("Lock", name, 0, normalize=False, num_retry=0)
            started = monotonic()
            bus.write(change["register"], name, change["after"], normalize=False, num_retry=0)
            finished = monotonic()
            if initial_lock:
                bus.write("Lock", name, initial_lock, normalize=False, num_retry=0)
            report["writes"].append(
                {
                    **change,
                    "status": "acknowledged",
                    "started_monotonic_s": started,
                    "finished_monotonic_s": finished,
                    "restored_lock": initial_lock,
                }
            )
        attached = {name: asdict(value) for name, value in bus.read_calibration().items()}
        report["firmware_after"] = attached
        if attached != configured:
            raise RuntimeError("Firmware readback does not match the configured calibration revision")
        torque_after = bus.sync_read("Torque_Enable", normalize=False, num_retry=0)
        report["torque_enable_after"] = torque_after
        if any(torque_after.values()):
            raise RuntimeError("Torque state changed during the endpoint revision")
        report["completed"] = True
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        return report
    finally:
        if getattr(bus, "is_connected", False):
            for name, initial_lock in initial_locks.items():
                try:
                    if bus.read("Lock", name, normalize=False, num_retry=0) != initial_lock:
                        bus.write("Lock", name, initial_lock, normalize=False, num_retry=0)
                except Exception as error:
                    report.setdefault("cleanup_errors", []).append(f"{name}: {error}")
            bus.disconnect(disable_torque=False)
        report["serial_port_closed"] = not getattr(bus, "is_connected", False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply a configured arm range-maximum revision; no motion")
    parser.add_argument("--role", choices=("phone", "light"), required=True)
    parser.add_argument("--profile", choices=("windows", "linux"), default="windows")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = apply_revision(args.role, args.profile)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(json.dumps(result | {"output": str(args.output.resolve())}, indent=2))
        return 0
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        print(json.dumps({"completed": False, "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
