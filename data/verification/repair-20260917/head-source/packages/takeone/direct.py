"""Direct calibrated joint-space rehearsal with no inverse kinematics or task planner."""

import hashlib
import json
import math
from pathlib import Path

import mujoco
import numpy as np

from takeone.calibration import ArmMapping
from takeone.config import finite, provenance, read_json
from takeone.contracts import JOINTS
from takeone.paths import CONFIGS
from takeone.planning.settings import DEFAULTS
from takeone.simulation import drive
from takeone.simulation.robot import load_model, model_hash, model_path, pose_frame

ROLES = ("phone", "light")
PERIOD_S = 0.04


def calibrated_positions(role):
    """Return the exact usable raw ranges and their representable integer midpoints."""
    mapping = ArmMapping.load(role, require_motion=False)
    ranges = {name: (raw["range_min"], raw["range_max"]) for name, raw in mapping.raw_calibration.items()}
    midpoints = {name: int((lower + upper) / 2) for name, (lower, upper) in ranges.items()}
    return mapping, ranges, midpoints


def direct_raw_at(role, time_s, duration_s, amplitude_fraction):
    """Create motor goals directly in encoder counts, always inside calibration."""
    mapping, ranges, midpoints = calibrated_positions(role)
    phase = finite(time_s, "Direct motion time") / finite(duration_s, "Direct motion duration")
    amplitude_fraction = finite(amplitude_fraction, "Direct motion amplitude")
    if duration_s <= 0 or not 0 <= time_s <= duration_s or not 0 <= amplitude_fraction <= 1:
        raise ValueError("Direct motion requires a positive duration, an in-range time and 0..1 amplitude")

    # One intentional shoulder-pan sweep is visually obvious without making the
    # complete arm wobble. The other four joints remain at their exact midpoint.
    harmonics = (1, 1, 1, 1, 1)
    directions = (1, 1, 1, 1, 1) if role == "phone" else (-1, 1, 1, 1, 1)
    scales = (1.0, 0.0, 0.0, 0.0, 0.0)
    result = {}
    for name, harmonic, direction, scale in zip(JOINTS, harmonics, directions, scales):
        lower, upper = ranges[name]
        midpoint = midpoints[name]
        half_span = min(midpoint - lower, upper - midpoint)
        amplitude = int(half_span * amplitude_fraction * scale)
        value = midpoint + round(direction * amplitude * math.sin(2 * math.pi * harmonic * phase))
        result[name] = min(upper, max(lower, int(value)))
    # Conversion is deliberately performed after the raw targets exist. This is
    # the same calibration mapping used by the physical arm adapter.
    return result, mapping.from_raw(result)


def _settings(request):
    if request is None:
        request = {}
    if not isinstance(request, dict):
        raise ValueError("Direct rehearsal settings must be an object")
    unknown = set(request) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown direct rehearsal settings: {sorted(unknown)}")
    # Both arms use one simple direct shoulder-pan sweep by default. There is no
    # task-space target or IK; the amplitudes are fractions of calibrated range.
    settings = dict(DEFAULTS) | {"armTravel": 0.16, "lightTravel": 0.16} | request
    numeric = {name for name, value in DEFAULTS.items() if not isinstance(value, str)}
    for name in numeric:
        settings[name] = finite(settings[name], name)
    if settings["duration"] <= 0:
        raise ValueError("Direct rehearsal duration must be positive")
    if settings["lightType"] not in ("ring", "panel", "tube"):
        raise ValueError("Unknown light type")
    if settings["trackWidth"] <= 0 or settings["minimumSpeed"] <= 0:
        raise ValueError("Track width and forward speed must be positive")
    for name in ("armTravel", "lightTravel"):
        if not 0 <= settings[name] <= 1:
            raise ValueError(f"{name} is a raw calibration-span fraction and must be between 0 and 1")
    # This route is intentionally a constant forward drive. The rest of the
    # legacy shot fields remain only so the existing viewer can render the scene.
    settings["driveProfile"] = "arms"
    settings["orbit"] = 0.0
    settings["turn"] = 0.0
    settings["responseTime"] = 0.0
    settings["brakeTime"] = 0.0
    return settings


def direct_shot(request=None):
    """Build a browser-ready raw-motor rehearsal without solving IK."""
    settings = _settings(request)
    duration = settings["duration"]
    model = load_model(settings["lightType"], settings["trackWidth"])
    data = mujoco.MjData(model)
    trace = drive.simulate(settings)
    count = math.ceil(duration / PERIOD_S)
    times = [min(index * PERIOD_S, duration) for index in range(count + 1)]
    if times[-1] != duration:
        times.append(duration)

    calibration = {}
    for role in ROLES:
        _, ranges, midpoints = calibrated_positions(role)
        calibration[role] = {
            "ranges": {name: list(bounds) for name, bounds in ranges.items()},
            "midpoints": midpoints,
        }

    frames = []
    q_rows = []
    for time_s in times:
        raw_by_role = {}
        q_arms = []
        for role, amplitude in (("phone", settings["armTravel"]), ("light", settings["lightTravel"])):
            raw, q_rad = direct_raw_at(role, time_s, duration, amplitude)
            raw_by_role[role] = raw
            q_arms.extend(q_rad)
        drive_frame = drive.sample(trace, time_s)
        q = (*drive_frame["cart"], *q_arms)
        frame = pose_frame(model, data, q, time_s, drive_frame)
        frame["rawPositions"] = [raw_by_role[role][name] for role in ROLES for name in JOINTS]
        frame["rawByRole"] = raw_by_role
        frames.append(frame)
        q_rows.append(q_arms)

    q_rows = np.asarray(q_rows)
    ranges_deg = np.degrees(np.ptp(q_rows, axis=0))
    drive_report = drive.summary(trace)
    commands = [
        {
            "time": record["time"],
            "duration": trace["dt"],
            "wire": record["wire"],
            "commands": record["commands"].tolist(),
        }
        for record in trace["records"]
    ]
    commands.append({"time": duration, "duration": 0, "wire": "0.00,0.00\n", "commands": [0, 0]})

    identity = json.dumps(
        {"mode": "direct_joint", "settings": settings, "calibration": calibration},
        sort_keys=True,
    ).encode()
    return {
        "schema": "take-one.direct-joint-rehearsal.v1",
        "directJointMode": True,
        "settings": settings,
        "scene": read_json(CONFIGS / "scene.json"),
        "provenance": provenance(),
        # Direct mode has no separate execution reintegration: the frames ARE the
        # executed values, so no executionPreview copy is emitted. The viewer
        # falls back to these frames; takeone.motion.direct validates them.
        "frames": frames,
        "calibration": calibration,
        "checks": [
            {
                "name": "Direct calibrated joint commands",
                "passed": True,
                "value": "10/10",
                "unit": (
                    "joints remain at raw calibrated midpoints"
                    if settings["armTravel"] == settings["lightTravel"] == 0
                    else "joints start at raw midpoint and remain within min/max"
                ),
            },
            {
                "name": "Inverse kinematics",
                "passed": True,
                "value": "0",
                "unit": "solves used",
            },
        ],
        "drive": drive_report,
        "motionOutline": [
            {
                "role": role,
                "target": (
                    "fixed calibrated midpoint"
                    if settings["armTravel" if role == "phone" else "lightTravel"] == 0
                    else "direct raw motor cycle"
                ),
                "sweep_m": settings["armTravel" if role == "phone" else "lightTravel"],
                "lift_m": 0.0,
            }
            for role in ROLES
        ],
        "solver": {"mode": "none", "solves": 0, "failed": 0},
        "movement": {
            "baseTurnDegrees": drive_report["baseTurnDegrees"],
            "cameraJointRangesDegrees": ranges_deg[:5].tolist(),
            "lightJointRangesDegrees": ranges_deg[5:].tolist(),
            "requestedArmSweep": settings["armTravel"],
            "requestedArmLift": 0.0,
            "requestedLightSweep": settings["lightTravel"],
            "requestedLightLift": 0.0,
        },
        "motorCommands": commands,
        "initialCartPose": frames[0]["q"][:3],
        "playable": True,
        "planValid": True,
        "shotFidelityPassed": True,
        "previewAvailable": True,
        "requiresRevision": False,
        "hardwareReady": False,
        "scope": "Direct calibrated raw joint-space rehearsal. No IK, task targets, collision screen, or trajectory optimizer.",
        "cameraHeightRange": [
            min(frame["camera"]["pos"][2] for frame in frames),
            max(frame["camera"]["pos"][2] for frame in frames),
        ],
        "target": [0.0, 0.0, settings["actorHeight"]],
        "compileSeconds": 0.0,
        "modelHash": model_hash(model_path(settings["lightType"]), settings["trackWidth"]),
        "planId": hashlib.sha256(identity).hexdigest()[:12],
        "actorCues": [
            {"phase": 0, "text": "Direct motor test ready at calibrated midpoints."},
            {"phase": 0.03, "text": "Cart forward. Both arms begin a smooth shoulder-pan sweep."},
            {"phase": 0.8, "text": "Both arms return smoothly toward their calibrated midpoints."},
            {"phase": 1, "text": "Direct test complete at calibrated midpoints."},
        ],
    }


def main(argv=None):
    """Write the exact direct-motor rehearsal as a portable JSON file."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate direct calibrated raw motor motion; no IK")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=float(DEFAULTS["duration"]))
    parser.add_argument("--phone-amplitude", type=float, default=0.16)
    parser.add_argument("--light-amplitude", type=float, default=0.16)
    args = parser.parse_args(argv)
    shot = direct_shot(
        {
            "duration": args.duration,
            "armTravel": args.phone_amplitude,
            "lightTravel": args.light_amplitude,
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(shot, indent=2, allow_nan=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "plan_id": shot["planId"],
                "duration_s": shot["settings"]["duration"],
                "period_s": PERIOD_S,
                "phone_midpoints": shot["calibration"]["phone"]["midpoints"],
                "light_midpoints": shot["calibration"]["light"]["midpoints"],
                "cart_wire": shot["motorCommands"][0]["wire"].strip(),
                "ik_solves": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
