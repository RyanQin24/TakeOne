"""Application service: validate intent, solve targets, evaluate and serialize one plan."""

import hashlib
import json
import time

import numpy as np

from takeone.config import provenance
from takeone.simulation import drive
from takeone.simulation.robot import load_model, model_hash, model_path

from .settings import parameters
from .targets import actor_target, movement_outline, tracking_programs
from .trajectory import solve_trajectory
from .validation import evaluate_plan


def compile_shot(request: dict | None = None) -> dict:
    started = time.perf_counter()
    settings = parameters({} if request is None else request)
    snapshot = provenance()
    model = load_model(settings["lightType"], settings["trackWidth"])
    motion = drive.simulate(settings)
    drive_report = drive.summary(motion)
    programs = tracking_programs(settings, drive.DIRECTION_SIGN)
    trajectory = solve_trajectory(model, settings, motion, programs)
    evaluation = evaluate_plan(model, settings, trajectory, programs, drive_report)
    ranges = np.degrees(np.ptp(trajectory.q[:, 3:], axis=0))
    commands = [
        dict(
            time=record["time"],
            duration=motion["dt"],
            wire=record["wire"],
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
        provenance=snapshot,
        frames=evaluation.frames,
        checks=evaluation.checks,
        drive=drive_report,
        motionOutline=movement_outline(programs),
        solver=dict(
            solves=len(trajectory.solves),
            failed=sum(not result.converged for result in trajectory.solves),
            evaluations=sum(result.evaluations for result in trajectory.solves),
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
        playable=evaluation.playable,
        previewAvailable=bool(np.isfinite(trajectory.q).all()),
        requiresRevision=bool(evaluation.height_revision_required),
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
