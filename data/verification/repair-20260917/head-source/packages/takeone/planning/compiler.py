"""Application service: validate intent, solve targets, evaluate and serialize one plan."""

import hashlib
import json
import time
from copy import deepcopy

import numpy as np

from takeone.calibration import ArmMapping
from takeone.config import provenance, read_json
from takeone.paths import CONFIGS
from takeone.simulation import drive
from takeone.simulation.robot import load_model, model_hash, model_path

from .preview import execution_preview
from .settings import parameters
from .targets import (
    actor_target,
    freeze_world_programs,
    movement_outline,
    serialize_world_programs,
    tracking_programs,
)
from .trajectory import solve_trajectory
from .validation import evaluate_plan

_last_compilation = None


def compile_shot(request: dict | None = None) -> dict:
    """Reuse one canonical solve within a process; content and sources bind the cache."""
    global _last_compilation

    settings = parameters({} if request is None else request)
    snapshot = provenance()
    key = json.dumps([settings, snapshot], sort_keys=True, allow_nan=False)
    cached = _last_compilation
    if cached is not None and cached[0] == key:
        return deepcopy(cached[1])
    result = _compile_shot(settings, snapshot)
    _last_compilation = (key, deepcopy(result))
    return result


def _compile_shot(settings, snapshot):
    started = time.perf_counter()
    model = load_model(settings["lightType"], settings["trackWidth"])
    arm_execution = read_json(CONFIGS / "arm-execution.json")
    reference_motion = drive.simulate(settings)
    authored_programs = tracking_programs(settings, drive.DIRECTION_SIGN)
    programs = freeze_world_programs(settings, reference_motion, authored_programs)
    trajectory = solve_trajectory(
        model,
        settings,
        reference_motion,
        programs,
        validation_period_s=arm_execution["period_s"],
    )
    motion = trajectory.motion
    drive_report = drive.summary(motion)
    mappings = {role: ArmMapping.load(role.value, require_motion=False) for role in programs}
    evaluation = evaluate_plan(
        model,
        settings,
        trajectory,
        programs,
        drive_report,
        mappings=mappings,
        dispatch_period_s=arm_execution["period_s"],
    )
    ranges = np.degrees(np.ptp(trajectory.q[:, 3:], axis=0))
    commands = [
        dict(
            time=record["time"],
            duration=motion["dt"],
            wire=record["wire"],
            commands=record["commands"].tolist(),
            requestedWheelSpeeds=record["desired"].tolist(),
            targetWheelSpeeds=record["target"].tolist(),
        )
        for record in motion["records"]
    ]
    commands.append(
        dict(
            time=settings["duration"],
            duration=0,
            wire="0.00,0.00\n",
            requestedWheelSpeeds=[0, 0],
            targetWheelSpeeds=[0, 0],
        )
    )
    identity = json.dumps({"settings": settings, "provenance": snapshot}, sort_keys=True).encode()
    return dict(
        schema="take-one.shot.v2",
        settings=settings,
        scene=read_json(CONFIGS / "scene.json"),
        provenance=snapshot,
        frames=evaluation.frames,
        executionPreview=execution_preview(
            settings,
            trajectory.curve,
            arm_execution["period_s"],
            trace=motion,
        ),
        joint_curve=trajectory.curve.to_dict(),
        checks=evaluation.checks,
        drive=drive_report,
        coordination=trajectory.coordination,
        motionOutline=movement_outline(authored_programs),
        requestedWorldTargets=serialize_world_programs(programs),
        taskMetrics=evaluation.metrics,
        solver=dict(
            solves=len(trajectory.solves),
            failed=sum(not result.converged for result in trajectory.solves),
            optimizerTerminations={
                name: value
                for name, value in trajectory.coordination.items()
                if name.endswith("_optimizer_terminated")
            },
            evaluations=sum(result.evaluations for result in trajectory.solves),
            activeLimitSolves=sum(bool(result.active_limits) for result in trajectory.solves),
        ),
        movement=dict(
            baseTurnDegrees=drive_report["baseTurnDegrees"],
            cameraJointRangesDegrees=ranges[:5].tolist(),
            lightJointRangesDegrees=ranges[5:].tolist(),
            requestedArmSweep=settings["armTravel"],
            requestedArmLift=settings["armLift"],
            requestedLightSweep=settings["lightTravel"],
            requestedLightLift=settings["lightLift"],
        ),
        motorCommands=commands,
        initialCartPose=trajectory.drive_frames[0]["cart"],
        playable=evaluation.playable,
        planValid=evaluation.plan_valid,
        shotFidelityPassed=evaluation.fidelity_passed,
        previewAvailable=bool(np.isfinite(trajectory.q).all()),
        requiresRevision=not evaluation.playable,
        hardwareReady=False,
        scope="Offline UART-command prediction with no-slip wheel odometry, quantization and assumed motor response. Physical dynamics and hardware execution remain unvalidated.",
        cameraHeightRange=[min(evaluation.camera_heights_m), max(evaluation.camera_heights_m)],
        target=actor_target(settings, 1.0).tolist(),
        compileSeconds=round(time.perf_counter() - started, 2),
        modelHash=model_hash(model_path(settings["lightType"]), settings["trackWidth"]),
        planId=hashlib.sha256(identity).hexdigest()[:12],
        actorCues=[
            {"phase": 0, "text": "Stand on mark A. Face the camera. Ready."},
            {"phase": 0.03, "text": "Action. Turn slowly toward mark B."},
            {"phase": 0.8, "text": "Finish your turn. Hold your eyeline."},
            {"phase": 1, "text": "Cut. Hold position."},
        ],
    )
