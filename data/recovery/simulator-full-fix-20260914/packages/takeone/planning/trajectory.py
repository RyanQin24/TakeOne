"""Compile synchronized arm paths over an executable differential-drive trace."""

from dataclasses import dataclass
from typing import Mapping

import mujoco
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares, minimize
from scipy.sparse import lil_matrix

from takeone.simulation import drive

from .curve import JointCurve
from .kinematics import (
    AIM_LIMIT_RAD,
    LIGHT_POSITION_GOAL_M,
    LIGHT_POSITION_LIMIT_M,
    PHONE_POSITION_GOAL_M,
    PHONE_POSITION_LIMIT_M,
    ROLL_LIMIT_RAD,
    ArmSolver,
    IKResult,
    pointing_basis,
    task_errors,
)
from .targets import ARMS, ArmRole, TargetStrategy, actor_target

SOLVE_SAMPLES = 81
MOBILE_SOLVE_SAMPLES = 13
FINAL_ARM_SAMPLES = 17
PREVIEW_SAMPLES = 321
MOBILE_PLAN_MARGIN_RAD = 0.018


@dataclass(slots=True)
class JointTrajectory:
    time_s: np.ndarray
    q: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray
    jerk: np.ndarray
    drive_frames: list[dict]
    solves: list[IKResult]
    curve: JointCurve
    motion: dict
    coordination: dict


def _arm_task_rows(model, data, q, phase, settings, programs):
    data.qpos[:] = q
    mujoco.mj_forward(model, data)
    rows = []
    for arm in ARMS:
        target = programs[arm.role].at(phase, q[:3], actor_target(settings, phase))
        site = model.site(arm.model_prefix + "_optical").id
        position = data.site_xpos[site]
        rotation = data.site_xmat[site].reshape(3, 3)
        direction, right = pointing_basis(position, np.asarray(target.look_at_m), rotation[:, 0])
        position_scale = 0.004 if arm.role == ArmRole.PHONE else 0.015
        roll_scale = np.deg2rad(1.5) if arm.role == ArmRole.PHONE else np.deg2rad(30.0)
        rows.extend((position - np.asarray(target.position_m)) / position_scale)
        rows.extend((rotation[:, 2] - direction) / (0.45 * AIM_LIMIT_RAD))
        rows.extend((rotation[:, 0] - right) / roll_scale)
    return np.asarray(rows)


def _continuous_cart(reference_motion, settings, parameters, elapsed_s):
    reference_start = np.asarray(drive.sample(reference_motion, 0.0)["cart"])
    initial = reference_start + parameters[:3]
    axle = np.array(
        [
            initial[0] + drive.AXLE_OFFSET * np.cos(initial[2]),
            initial[1] + drive.AXLE_OFFSET * np.sin(initial[2]),
            initial[2] + drive.HEADING_OFFSET,
        ]
    )
    axle = drive.integrate(axle, parameters[3] * elapsed_s, parameters[4] * elapsed_s, settings["trackWidth"])
    return drive.cart_from_axle(axle)


def _sparsity(sample_count, base_variables):
    task_rows = 18
    row_count = sample_count * task_rows + (sample_count - 1) * 10 + base_variables
    column_count = base_variables + sample_count * 10
    result = lil_matrix((row_count, column_count), dtype=int)
    if base_variables:
        result[:, :base_variables] = 1
    row = 0
    for index in range(sample_count):
        start = base_variables + 10 * index
        result[row : row + task_rows, start : start + 10] = 1
        row += task_rows
        if index:
            previous = start - 10
            result[row : row + 10, previous : start + 10] = 1
            row += 10
    return result.tocsr()


def _seed_mobile_arms(model, settings, reference_motion, programs, phases, base_guess):
    data = mujoco.MjData(model)
    lower = model.jnt_range[3:, 0] + MOBILE_PLAN_MARGIN_RAD
    upper = model.jnt_range[3:, 1] - MOBILE_PLAN_MARGIN_RAD
    random = np.random.default_rng(22)
    previous = np.zeros(10)
    result = []
    for sample_index, phase in enumerate(phases):
        cart = _continuous_cart(reference_motion, settings, base_guess, phase * settings["duration"])

        def residual(joints):
            return np.r_[
                _arm_task_rows(model, data, np.r_[cart, joints], phase, settings, programs),
                0.2 * (joints - previous),
            ]

        seeds = [np.clip(previous, lower, upper), (lower + upper) / 2]
        if sample_index == 0:
            seeds.extend(random.uniform(lower, upper) for _ in range(8))
        candidates = [
            least_squares(
                residual,
                seed,
                bounds=(lower, upper),
                max_nfev=600,
                ftol=1e-9,
                xtol=1e-9,
                gtol=1e-9,
            )
            for seed in seeds
        ]
        solution = min(candidates, key=lambda item: float(np.linalg.norm(residual(item.x))))
        previous = solution.x.copy()
        result.append(previous)
    return np.asarray(result)


def _optimize_mobile(model, settings, reference_motion, programs):
    phases = np.linspace(0.0, 1.0, MOBILE_SOLVE_SAMPLES)
    times = phases * settings["duration"]
    minimum = settings["minimumSpeed"]
    maximum = min(0.3, minimum * 0.15 / 0.04)
    base_guess = np.array([-0.12, 0.05, np.deg2rad(-4.0), minimum, min(maximum, minimum + 0.0125)])
    seeds = _seed_mobile_arms(model, settings, reference_motion, programs, phases, base_guess)
    lower_joints = model.jnt_range[3:, 0] + MOBILE_PLAN_MARGIN_RAD
    upper_joints = model.jnt_range[3:, 1] - MOBILE_PLAN_MARGIN_RAD
    lower = np.r_[[-0.4, -0.4, np.deg2rad(-30.0), minimum, minimum], np.tile(lower_joints, len(phases))]
    upper = np.r_[[0.4, 0.4, np.deg2rad(30.0), maximum, maximum], np.tile(upper_joints, len(phases))]
    initial = np.r_[base_guess, seeds.ravel()]
    data = mujoco.MjData(model)

    def residual(values):
        rows = []
        for index, (phase, elapsed) in enumerate(zip(phases, times)):
            joints = values[5 + 10 * index : 15 + 10 * index]
            cart = _continuous_cart(reference_motion, settings, values[:5], elapsed)
            rows.extend(_arm_task_rows(model, data, np.r_[cart, joints], phase, settings, programs))
            if index:
                rows.extend(0.3 * (joints - values[5 + 10 * (index - 1) : 15 + 10 * (index - 1)]))
        rows.extend(
            [
                0.02 * values[0] / 0.2,
                0.02 * values[1] / 0.2,
                0.02 * values[2] / np.deg2rad(10.0),
                0.02 * (values[3] - minimum) / 0.05,
                0.02 * (values[4] - minimum) / 0.05,
            ]
        )
        return np.asarray(rows)

    solution = least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        jac_sparsity=_sparsity(len(phases), 5),
        max_nfev=1000,
        ftol=1e-9,
        xtol=1e-9,
        gtol=1e-9,
    )
    reference_start = np.asarray(drive.sample(reference_motion, 0.0)["cart"])
    initial_cart = reference_start + solution.x[:3]
    motion = drive.simulate_constant_schedule(settings, initial_cart, solution.x[3:5])

    # The two-decimal packet stream is authoritative. Re-solve both arms on its
    # exact integrated path so continuous average speeds cannot hide an error.
    arm_initial = solution.x[5:].copy()

    def quantized_residual(values):
        rows = []
        for index, (phase, elapsed) in enumerate(zip(phases, times)):
            joints = values[10 * index : 10 * (index + 1)]
            cart = drive.sample(motion, float(elapsed))["cart"]
            rows.extend(_arm_task_rows(model, data, np.r_[cart, joints], phase, settings, programs))
            if index:
                rows.extend(0.3 * (joints - values[10 * (index - 1) : 10 * index]))
        return np.asarray(rows)

    arm_solution = least_squares(
        quantized_residual,
        arm_initial,
        bounds=(np.tile(lower_joints, len(phases)), np.tile(upper_joints, len(phases))),
        jac_sparsity=_sparsity(len(phases), 0),
        max_nfev=1000,
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
    )
    coarse_keyframes = arm_solution.x.reshape(len(phases), 10)
    final_phases = np.linspace(0.0, 1.0, FINAL_ARM_SAMPLES)
    keyframes = CubicSpline(phases, coarse_keyframes, axis=0)(final_phases)
    keyframes = np.clip(keyframes, lower_joints, upper_joints)
    keyframes, constraint_terminated, constraint_diagnostics = _enforce_keyframe_constraints(
        model, settings, final_phases, keyframes, motion, programs, lower_joints, upper_joints
    )
    coordination = dict(
        mode="joint_cart_constant_wheel_trajectory_optimization",
        target_frame="frozen_world",
        local_search=True,
        continuous_optimizer_terminated=bool(solution.success),
        quantized_optimizer_terminated=bool(arm_solution.success),
        constraint_optimizer_terminated=constraint_terminated,
        initial_staging_offset_m_rad=solution.x[:3].tolist(),
        continuous_wheel_speeds_m_s=solution.x[3:5].tolist(),
        quantized_average_wire_commands=motion["desired_average_commands"],
        joint_plan_margin_rad=MOBILE_PLAN_MARGIN_RAD,
        search_evaluations=int(solution.nfev + arm_solution.nfev),
        arm_constraint_samples=FINAL_ARM_SAMPLES,
        constraint_diagnostics=constraint_diagnostics,
    )
    return (
        final_phases,
        keyframes,
        motion,
        coordination,
        bool(solution.success and arm_solution.success and constraint_terminated),
    )


def _enforce_keyframe_constraints(
    model, settings, phases, keyframes, motion, programs, lower_joints, upper_joints
):
    """Project near-feasible mobile solutions into the declared task corridors."""
    data = mujoco.MjData(model)
    result = keyframes.copy()
    terminated = True
    diagnostics = []
    random = np.random.default_rng(440)
    previous = {arm.role: None for arm in ARMS}
    for frame_index, phase in enumerate(phases):
        cart = np.asarray(drive.sample(motion, phase * settings["duration"])["cart"])
        for arm in ARMS:
            local = slice(arm.qpos_start - 3, arm.qpos_start + 2)
            model_slice = arm.qpos_slice
            target = programs[arm.role].at(phase, cart, actor_target(settings, phase))
            site = model.site(arm.model_prefix + "_optical").id
            start = result[frame_index, local].copy()
            reference = start if previous[arm.role] is None else previous[arm.role]
            q = np.r_[cart, result[frame_index]]

            def errors(joints):
                q[model_slice] = joints
                data.qpos[:] = q
                mujoco.mj_forward(model, data)
                return task_errors(data.site_xpos[site], data.site_xmat[site].reshape(3, 3), target)

            position_goal = PHONE_POSITION_GOAL_M if arm.role == ArmRole.PHONE else LIGHT_POSITION_GOAL_M
            # Plan inside the public corridors. The remaining allowance covers
            # spline behavior and integer encoder conversion; these inner
            # values are planning margins, not smaller hard limits.
            position_limit = 0.0192 if arm.role == ArmRole.PHONE else 0.045
            aim_limit = np.deg2rad(0.90)
            roll_limit = np.deg2rad(1.75)

            def objective(joints):
                position_error, aim_error, roll_error = errors(joints)
                roll_term = (roll_error / ROLL_LIMIT_RAD) ** 2 if arm.role == ArmRole.PHONE else 0.0
                return float(
                    (position_error / position_goal) ** 2
                    + (aim_error / aim_limit) ** 2
                    + 0.1 * roll_term
                    + np.sum((joints - reference) ** 2)
                )

            def constraints(joints):
                position_error, aim_error, roll_error = errors(joints)
                values = [position_limit - position_error, aim_limit - aim_error]
                if arm.role == ArmRole.PHONE:
                    values.append(roll_limit - roll_error)
                return np.asarray(values)

            bounds = list(zip(lower_joints[local], upper_joints[local]))

            def optimize(seed):
                return minimize(
                    objective,
                    seed,
                    method="SLSQP",
                    bounds=bounds,
                    constraints={"type": "ineq", "fun": constraints},
                    options={"maxiter": 300, "ftol": 1e-11, "disp": False},
                )

            candidates = [optimize(start)]
            if np.min(constraints(candidates[0].x)) < -1e-7:
                midpoint = (lower_joints[local] + upper_joints[local]) / 2
                alternate_seeds = [
                    midpoint,
                    0.5 * (start + midpoint),
                    random.uniform(lower_joints[local], upper_joints[local]),
                    random.uniform(lower_joints[local], upper_joints[local]),
                ]
                candidates.extend(optimize(seed) for seed in alternate_seeds)

            def rank(item):
                corridor = constraints(item.x)
                violation = float(np.sum(np.square(np.minimum(corridor, 0.0))))
                return (violation > 1e-14, violation, objective(item.x))

            solution = min(candidates, key=rank)
            candidate = solution.x
            if np.min(constraints(candidate)) < -1e-7:
                terminated = False
                diagnostics.append(
                    dict(
                        role=arm.role.value,
                        phase=float(phase),
                        corridor_values=constraints(candidate).tolist(),
                        optimizer_status=int(solution.status),
                        optimizer_message=str(solution.message),
                        alternatives=len(candidates),
                    )
                )
            else:
                terminated &= bool(solution.success)
            result[frame_index, local] = candidate
            previous[arm.role] = candidate.copy()
    return result, terminated, diagnostics


def _solve_fixed_cart(model, settings, motion, programs):
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
        keyframes.append(q[3:])
        seed = q
    return (
        phases,
        np.asarray(keyframes),
        motion,
        dict(mode="fixed_cart_hierarchical_arm_ik"),
        all(result.optimizer_terminated for result in results),
    )


def _results(model, settings, phases, keyframes, motion, programs, optimizer_terminated):
    data = mujoco.MjData(model)
    results = []
    for phase, joints in zip(phases, keyframes):
        q = np.r_[drive.sample(motion, phase * settings["duration"])["cart"], joints]
        data.qpos[:] = q
        mujoco.mj_forward(model, data)
        for arm in ARMS:
            site = model.site(arm.model_prefix + "_optical").id
            target = programs[arm.role].at(phase, q[:3], actor_target(settings, phase))
            errors = task_errors(data.site_xpos[site], data.site_xmat[site].reshape(3, 3), target)
            position_limit = PHONE_POSITION_LIMIT_M if arm.role == ArmRole.PHONE else LIGHT_POSITION_LIMIT_M
            feasible = errors[0] <= position_limit and errors[1] <= AIM_LIMIT_RAD
            if arm.role == ArmRole.PHONE:
                feasible &= errors[2] <= ROLL_LIMIT_RAD
            solution = q[arm.qpos_slice]
            margins = np.minimum(
                solution - model.jnt_range[arm.qpos_slice, 0],
                model.jnt_range[arm.qpos_slice, 1] - solution,
            )
            results.append(
                IKResult(
                    tuple(solution),
                    bool(feasible),
                    optimizer_terminated,
                    0,
                    errors[0],
                    float(np.degrees(errors[1])),
                    float(np.degrees(errors[2])),
                    tuple(int(index) for index in np.flatnonzero(margins <= 1e-4)),
                )
            )
    return results


def solve_trajectory(
    model,
    settings: dict,
    reference_motion: dict,
    programs: Mapping[ArmRole, TargetStrategy],
    *,
    validation_period_s: float | None = None,
) -> JointTrajectory:
    if set(programs) != {arm.role for arm in ARMS}:
        raise ValueError("An explicit frozen target strategy is required for each arm")
    if settings["driveProfile"] == "arms":
        phases, keyframes, motion, coordination, terminated = _optimize_mobile(
            model, settings, reference_motion, programs
        )
    else:
        phases, keyframes, motion, coordination, terminated = _solve_fixed_cart(
            model, settings, reference_motion, programs
        )
    results = _results(model, settings, phases, keyframes, motion, programs, terminated)
    boundary = "natural" if settings["driveProfile"] == "arms" else ((1, np.zeros(10)), (1, np.zeros(10)))
    spline = CubicSpline(phases * settings["duration"], keyframes, axis=0, bc_type=boundary)
    # Validate the smoothed curve on a dense, independent grid and at every
    # actual arm-dispatch instant.  This remains finite sampled coverage; the
    # polynomial joint-range and derivative screens below are analytic.
    time_s = np.linspace(0, settings["duration"], PREVIEW_SAMPLES)
    if validation_period_s is not None:
        dispatch = np.arange(0.0, settings["duration"], validation_period_s)
        time_s = np.unique(np.r_[time_s, dispatch, settings["duration"]])
    coordination["validation_sampling"] = dict(
        samples=len(time_s),
        maximum_gap_s=float(np.max(np.diff(time_s))),
        includes_dispatch_grid=validation_period_s is not None,
        dispatch_period_s=validation_period_s,
        scope="finite task-space FK samples plus analytic joint polynomial extrema",
    )
    arm_values = [spline(time_s, derivative) for derivative in range(4)]
    drive_frames = [drive.sample(motion, float(t)) for t in time_s]
    q = np.c_[[frame["cart"] for frame in drive_frames], arm_values[0]]
    velocity = np.c_[np.gradient(q[:, :3], time_s, axis=0), arm_values[1]]
    acceleration = np.c_[np.gradient(velocity[:, :3], time_s, axis=0), arm_values[2]]
    jerk = np.c_[np.gradient(acceleration[:, :3], time_s, axis=0), arm_values[3]]
    curve = JointCurve(
        tuple(spline.x),
        tuple(
            tuple(tuple(spline.c[3 - power, index, :]) if power < 4 else (0.0,) * 10 for power in range(6))
            for index in range(len(spline.x) - 1)
        ),
    )
    return JointTrajectory(
        time_s, q, velocity, acceleration, jerk, drive_frames, results, curve, motion, coordination
    )
