"""Explicit read-only capture worker. Never enables torque or writes motor registers."""

import argparse
import json
from pathlib import Path

from takeone.calibration import ArmMapping
from takeone.clock import monotonic
from takeone.contracts import JOINTS
from takeone.motion.commission import inspect_arm
from takeone.motion.studio_worker import device_ownership


def capture(*, inspect=inspect_arm):
    started = monotonic()
    reports = {role: inspect(role) for role in ("phone", "light")}
    qpos = [0.0, 0.0, 0.0]  # Run-local stationary chassis origin, NOT localization.
    for role, report in reports.items():
        if not report.get("completed") or not report.get("configured_calibration_matches_hardware"):
            raise ValueError(
                f"{role}: complete matching encoder inspection required: {report.get('error', 'calibration mismatch')}"
            )
        raw = {name: report["joints"][name]["registers_raw"]["Present_Position"] for name in JOINTS}
        for row in report["joints"].values():
            registers = row["registers_raw"]
            if registers["Operating_Mode"] != 0 or registers["Phase"] & 16:
                raise ValueError(f"{role}: unsupported motor mode")
        qpos.extend(ArmMapping.load(role, require_motion=False).from_raw(raw))
    return dict(
        qpos=qpos,
        reports=reports,
        acquisition_started_s=started,
        acquisition_completed_s=monotonic(),
        source="measured_snapshot",
        frame="stationary_chassis_run_local_origin",
        motor_register_writes=False,
        physical_pose_verified=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8") as handle:
        with device_ownership():
            result = capture()
        json.dump(result, handle, indent=2)


if __name__ == "__main__":
    main()
