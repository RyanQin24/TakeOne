"""Execution frames from the shared polynomial, command prediction and existing FK."""

import mujoco
import numpy as np

from takeone.planning.curve import dispatch_times
from takeone.simulation import drive
from takeone.simulation.robot import load_model, pose_frame


def execution_preview(
    settings, curve, period_s, transition_s=0, *, include_envelope=False, trace=None, joint_ranges=None
):
    """Frames at dispatch instants; browser holds each entire FK frame until the next.

    The time-quantization bound is exact. Spatial differences are sampled at each
    inter-frame midpoint, explicitly not a continuous or physical error bound.
    The existing drive integrator supplies cart state, including a zero-command
    brake segment after the original shot when a departure is requested.
    """
    model = load_model(settings["lightType"], settings["trackWidth"])
    data = mujoco.MjData(model)
    trace = drive.simulate(settings) if trace is None else trace
    times = dispatch_times(curve.duration_s, period_s)
    envelope = None
    if include_envelope:
        from takeone.config import read_json
        from takeone.paths import CONFIGS

        from .envelope import EnvelopeScreen

        envelope = EnvelopeScreen(model, curve, trace, read_json(CONFIGS / "scene.json"), settings)

    def at(t):
        source_time = t - transition_s
        frame = drive.sample(trace, min(settings["duration"], max(0.0, source_time)))
        if source_time < 0:
            frame.update(
                wheelSpeeds=[0.0, 0.0], speed=0.0, yawRate=0.0, commands=[0.0, 0.0], wire="0.00,0.00\n"
            )
        if source_time > settings["duration"]:
            axle, speeds, distances = drive.segment(
                *trace["final"],
                (0.0, 0.0),
                source_time - settings["duration"],
                settings["trackWidth"],
                settings["responseTime"],
                settings["brakeTime"],
            )
            frame.update(
                axle=axle.tolist(),
                cart=drive.cart_from_axle(axle).tolist(),
                wheelAngles=(distances / drive.WHEEL_RADIUS).tolist(),
                wheelSpeeds=speeds.tolist(),
                speed=float(sum(speeds) / 2),
                yawRate=float((speeds[1] - speeds[0]) / settings["trackWidth"]),
                pathError=float(np.linalg.norm(axle[:2] - np.array(frame["referenceAxle"])[:2])),
                yawError=float(abs(axle[2] - frame["referenceAxle"][2])),
                commands=[0.0, 0.0],
                wire="0.00,0.00\n",
            )
        q = (*frame["cart"], *curve.at(t))
        result = pose_frame(model, data, q, t, frame)
        if envelope:
            envelope.observe(data, q, t)
        return result

    frames = [at(t) for t in times]
    errors = {"joint_rad": 0.0, "body_position_m": 0.0, "body_rotation_rad": 0.0}
    for a, b in zip(frames, frames[1:]):
        midpoint = at((a["time_s"] + b["time_s"]) / 2)
        errors["joint_rad"] = max(
            errors["joint_rad"], max(abs(x - y) for x, y in zip(a["q"][3:], midpoint["q"][3:]))
        )
        aa, mm = np.array(a["bodies"]), np.array(midpoint["bodies"])
        errors["body_position_m"] = max(
            errors["body_position_m"], float(np.max(np.linalg.norm(aa[:, :3] - mm[:, :3], axis=1)))
        )
        angles = 2 * np.arccos(np.clip(abs(np.sum(aa[:, 3:] * mm[:, 3:], axis=1)), 0, 1))
        errors["body_rotation_rad"] = max(errors["body_rotation_rad"], float(np.max(angles)))
    lower, upper = curve.extrema()
    if envelope:
        # Refine an inconclusive between-frame bound without changing motion or
        # display timing. Stop if a sampled distance itself violates the margin.
        for _ in range(2):
            bounds = envelope.report()
            if bounds["conditional_clearance_proven"] or bounds["sampled_clearance_lower_bound_m"] <= 0.015:
                break
            evaluated = sorted(set(envelope.times))
            for a, b in zip(evaluated, evaluated[1:]):
                at((a + b) / 2)
    ranges = model.jnt_range[3:] if joint_ranges is None else np.asarray(joint_ranges)
    margin = float(np.min(np.minimum(np.array(lower) - ranges[:, 0], ranges[:, 1] - np.array(upper))))
    peaks = [max(abs(v) for bounds in curve.extrema(d) for v in bounds) for d in (1, 2, 3)]
    revision_checks = [
        dict(
            name="Continuous joint range",
            passed=margin > 0.01 if joint_ranges is None else margin >= -1e-9,
            value=margin,
            unit="rad margin",
        )
    ]
    for name, value, cap, unit in zip(
        ("Continuous reference speed", "Continuous reference acceleration", "Piecewise reference jerk"),
        peaks,
        (0.8, 1.8, 12),
        ("rad/s", "rad/s²", "rad/s³"),
    ):
        revision_checks.append(dict(name=name, passed=value < cap, value=value, unit=unit))
    return dict(
        frames=frames,
        model_envelope=envelope.report() if envelope else None,
        semantics="hold_previous_complete_fk_frame",
        revision_checks=revision_checks,
        unverified_geometry=[
            "whole scene swept clearance",
            "loaded support polygon and tipping",
            "cable routing",
            "measured payload demand and motor margin",
        ],
        time_quantization_bound_s=max(b - a for a, b in zip(times, times[1:])),
        midpoint_display_differences=errors,
        scope="Command reference and model prediction; servo interpolation and physical lag require measurements",
    )
