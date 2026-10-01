"""Learn larger real encoder maxima before commissioning, while torque is off."""

import argparse
import copy
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from takeone.calibration import ArmMapping
from takeone.config import file_hash, read_json
from takeone.contracts import JOINTS
from takeone.paths import CALIBRATION, DATA

from .calibration_revision import apply_revision
from .commission import make_bus, specification


def save(path, document):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def capture_maxima(role, profile):
    """One serial owner; read-only bus enforces no register writes during capture."""
    from dataclasses import asdict

    from takeone.adapters.identity import identify_port

    device, configured, _ = specification(role, profile)
    identity = identify_port(device["port"], device["usb_serial"])
    bus = make_bus(device, configured)
    try:
        bus.connect()
        attached = {n: asdict(c) for n, c in bus.read_calibration().items()}
        if attached != configured:
            raise ValueError(f"{role}: saved calibration and firmware differ")
        samples = []
        for _ in range(3):
            state = {
                key: bus.sync_read(key, normalize=False, num_retry=0)
                for key in ("Torque_Enable", "Operating_Mode", "Phase", "Present_Position")
            }
            if any(set(values) != set(JOINTS) for values in state.values()):
                raise ValueError(f"{role}: incomplete encoder capture")
            for name in JOINTS:
                p = state["Present_Position"][name]
                if state["Torque_Enable"][name] != 0:
                    raise ValueError(f"{role}/{name}: maximum capture requires torque already off")
                if state["Operating_Mode"][name] != 0 or state["Phase"][name] & 16:
                    raise ValueError(f"{role}/{name}: maximum capture requires ordinary position mode")
                if type(p) is not int or not 0 <= p <= 4095:
                    raise ValueError(f"{role}/{name}: invalid 12-bit position {p}")
                if p < configured[name]["range_min"]:
                    raise ValueError(f"{role}/{name}: {p} below minimum; only maximum learning is enabled")
            samples.append(state["Present_Position"])
        return dict(identity=identity, samples=samples, calibration_before=configured)
    finally:
        if bus.is_connected:
            bus.disconnect(disable_torque=False)


def learn_maxima(profile, folder, emit):
    report = dict(
        schema="takeone.observed-maxima.v1",
        completed=False,
        policy="User requested: increase each maximum to the largest valid torque-off encoder reading",
        torque_commands_sent=False,
        goal_position_commands_sent=False,
        captures={},
        revisions={},
    )
    try:
        # Capture both arms before changing either calibration.
        for role in ("phone", "light"):
            emit(dict(phase="reading_calibration_maxima", role=role))
            report["captures"][role] = capture_maxima(role, profile)
        save(folder / "maxima.json", report)
        for role, capture in report["captures"].items():
            before = capture["calibration_before"]
            requested = copy.deepcopy(before)
            changes = []
            for name in JOINTS:
                maximum = max(before[name]["range_max"], *(s[name] for s in capture["samples"]))
                if maximum > before[name]["range_max"]:
                    requested[name]["range_max"] = maximum
                    changes.append(dict(joint=name, before=before[name]["range_max"], after=maximum))
            if not changes:
                continue
            registry_path = CALIBRATION / "registry.json"
            registry = read_json(registry_path)
            entry = registry["arms"][role]
            mapping_path = (CALIBRATION / entry["mapping_path"]).resolve()
            if not mapping_path.is_relative_to(CALIBRATION.resolve()):
                raise ValueError("Mapping path escapes calibration directory")
            mapping = read_json(mapping_path)
            if mapping["range_source"] != "calibration":
                raise ValueError("Maximum learning requires the selected calibration range policy")
            (folder / f"{role}-mapping-before.json").write_bytes(mapping_path.read_bytes())
            (folder / f"{role}-registry-before.json").write_bytes(registry_path.read_bytes())
            previous_mapping = ArmMapping.load(role, require_motion=False)
            for change in changes:
                name = change["joint"]
                mapping.setdefault("raw_range_overrides", {}).setdefault(name, {})["range_max"] = change[
                    "after"
                ]
                # q=(servo_degrees-offset)/sign. Preserve q as the range midpoint changes.
                mapping["zero_offsets_deg"][JOINTS.index(name)] -= (
                    (change["after"] - change["before"]) * 180 / 4095
                )
            mapping["endpoint_learning"] = dict(
                policy="largest_valid_torque_off_reading",
                report=str(folder / "maxima.json"),
                model_zero_preserved=True,
            )
            mapping["note"] = (
                "Nominal SO101 mapping with operator-authorized observed maximum revisions. "
                "zero_offsets_deg compensates changes in the normalization midpoint so the same raw "
                "encoder reading retains its model angle. Originals and firmware homing are unchanged."
            )
            save(folder / f"{role}-mapping-requested.json", mapping)
            emit(dict(phase="updating_calibration_maxima", role=role, changes=changes))
            revision = apply_revision(role, profile, requested_calibration=requested)
            revision_path = folder / f"{role}-firmware-revision.json"
            save(revision_path, revision)
            # Commit active configuration only after acknowledged write AND matching readback.
            save(mapping_path, mapping)
            current_mapping = ArmMapping.load(role, require_motion=False)
            reference = {n: before[n]["range_min"] for n in JOINTS}
            angle_error = max(
                abs(a - b)
                for a, b in zip(previous_mapping.from_raw(reference), current_mapping.from_raw(reference))
            )
            if angle_error > 1e-12:
                raise ValueError("Endpoint update changed model zero")
            entry.setdefault("observed_maximum_revisions", []).append(
                dict(changes=changes, evidence=str(revision_path), evidence_sha256=file_hash(revision_path))
            )
            legacy = entry.get("configured_revision")
            if legacy and any(c["joint"] == legacy["joint"] for c in changes):
                entry.setdefault("configured_revision_history", []).append(copy.deepcopy(legacy))
                legacy.update(
                    configured=requested[legacy["joint"]]["range_max"],
                    evidence=str(revision_path),
                    evidence_sha256=file_hash(revision_path),
                )
            save(registry_path, registry)
            report["revisions"][role] = dict(
                changes=changes, firmware_report=str(revision_path), model_angle_error_rad=angle_error
            )
            save(folder / "maxima.json", report)
        report["completed"] = True
        return report
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        save(folder / "maxima.json", report)


def refresh_plan(path, profile, emit):
    from .checked import record_check, require_checked
    from .limits import preflight
    from .plan import load_plan, prepare_shot

    document = json.loads(path.read_text(encoding="utf-8-sig"))
    plan = load_plan(document, current_sources=False)
    if document.get("staging"):
        raise ValueError("Use the original shot plan, not a previous captured approach")
    folder = (
        DATA
        / "commissioning"
        / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-maxima-" + uuid.uuid4().hex[:8])
    )
    folder.mkdir(parents=True)
    (folder / "plan-before.json").write_bytes(path.read_bytes())
    report = learn_maxima(profile, folder, emit)
    try:
        require_checked(plan)
        needs_prepare = False
    except ValueError:
        needs_prepare = True
    if report["revisions"] or needs_prepare:
        emit(
            dict(
                phase="repreparing_plan",
                message="Calibration or source changed; solving and checking this shot once",
            )
        )
        from takeone.planning.compiler import compile_shot

        plan = prepare_shot(
            compile_shot(document["settings"]),
            **document["revision"],
            criteria=document["acceptance_criteria"],
        )
        readiness = preflight(plan, profile, execution_mode="commissioning")
        save(folder / "prepared-preflight.json", readiness)
        (folder / "prepared-plan.json").write_bytes(plan.payload)
        if readiness["blockers"]:
            raise ValueError("Updated plan rejected: " + "; ".join(readiness["blockers"]))
        record_check(plan, "canonical_preparation")
        save(path, plan.to_dict())
    return dict(
        completed=True,
        report=str(folder / "maxima.json"),
        changes=report["revisions"],
        plan_id=plan.plan_id,
        plan=str(path.resolve()),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture real torque-off maxima and refresh the commissioning plan"
    )
    parser.add_argument("--profile", choices=("windows", "linux"), default="windows")
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.perf_counter()

    def emit(event):
        print(json.dumps(event), flush=True)

    try:
        result = refresh_plan(args.plan, args.profile, emit)
        emit(result | dict(elapsed_s=round(time.perf_counter() - started, 3)))
        return 0
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        emit(dict(completed=False, error=str(error), elapsed_s=round(time.perf_counter() - started, 3)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
