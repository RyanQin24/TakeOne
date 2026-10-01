"""Compile synchronized joint trajectories over authoritative wheel odometry."""

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.interpolate import CubicSpline

from takeone.simulation import drive

from .kinematics import ArmSolver, IKResult
from .targets import ARMS, ArmRole, TargetStrategy, actor_target

SOLVE_SAMPLES = 81
PREVIEW_SAMPLES = 321


@dataclass(slots=True)
class JointTrajectory:
    time_s: np.ndarray
    q: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray
    jerk: np.ndarray
    drive_frames: list[dict]
    solves: list[IKResult]


def solve_trajectory(
    model, settings: dict, motion: dict, programs: Mapping[ArmRole, TargetStrategy]
) -> JointTrajectory:
    if set(programs) != {arm.role for arm in ARMS}:
        raise ValueError("An explicit target strategy is required for each arm")
    solver = ArmSolver(model)
    phases = np.linspace(0, 1, SOLVE_SAMPLES)
    seed = np.zeros(model.nq)
    keyframes, results = [], []
    for phase in phases:
        q = seed.copy()
        q[:3] = drive.sample(motion, phase * settings["duration"])["cart"]
        subject = actor_target(settings, phase)
        for arm in ARMS:
            target = programs[arm.role].at(phase, q[:3], subject)
            result = solver.solve(q, arm, target)
            q[arm.qpos_slice] = result.joints_rad
            results.append(result)
        keyframes.append(q)
        seed = q

    # A moving dolly needs nonzero arm boundary velocities for continuous tracking.
    boundary = (
        "not-a-knot"
        if settings["driveProfile"] == "arms"
        else ((1, np.zeros(model.nq)), (1, np.zeros(model.nq)))
    )
    spline = CubicSpline(phases * settings["duration"], keyframes, axis=0, bc_type=boundary)
    time_s = np.linspace(0, settings["duration"], PREVIEW_SAMPLES)
    q, velocity, acceleration, jerk = (spline(time_s, derivative) for derivative in range(4))
    drive_frames = [drive.sample(motion, float(t)) for t in time_s]
    q[:, :3] = [frame["cart"] for frame in drive_frames]
    velocity[:, :3] = np.gradient(q[:, :3], time_s, axis=0)
    acceleration[:, :3] = np.gradient(velocity[:, :3], time_s, axis=0)
    # Chassis derivatives also come from wheel odometry, not the obsolete spline.
    jerk[:, :3] = np.gradient(acceleration[:, :3], time_s, axis=0)
    return JointTrajectory(time_s, q, velocity, acceleration, jerk, drive_frames, results)
