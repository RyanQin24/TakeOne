"""Hierarchical bounded IK with task-space feasibility measured after solving."""

import math
from dataclasses import dataclass

import mujoco
import numpy as np
from scipy.optimize import least_squares, minimize

from .targets import ArmRole, ArmSpec, ToolTarget

PHONE_POSITION_GOAL_M = 0.01
PHONE_POSITION_LIMIT_M = 0.02
LIGHT_POSITION_GOAL_M = 0.02
LIGHT_POSITION_LIMIT_M = 0.05
AIM_LIMIT_RAD = np.deg2rad(1.0)
ROLL_LIMIT_RAD = np.deg2rad(2.0)
PREFERRED_LIMIT_MARGIN_RAD = 0.04


@dataclass(frozen=True, slots=True)
class IKResult:
    joints_rad: tuple[float, ...]
    converged: bool
    optimizer_terminated: bool
    evaluations: int
    position_error_m: float
    aim_error_deg: float
    roll_error_deg: float
    active_limits: tuple[int, ...]


def pointing_basis(
    position: np.ndarray, look_at: np.ndarray, reference_right: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return optical forward and a continuous zero-roll right direction."""
    direction = np.asarray(look_at, dtype=float) - np.asarray(position, dtype=float)
    distance = np.linalg.norm(direction)
    if distance < 1e-9:
        raise ValueError("Look-at target coincides with the solved tool position")
    direction /= distance
    right = np.cross(direction, [0.0, 0.0, 1.0])
    if np.linalg.norm(right) < 1e-9:
        candidate = np.asarray(reference_right if reference_right is not None else [1.0, 0.0, 0.0])
        right = candidate - direction * float(candidate @ direction)
        if np.linalg.norm(right) < 1e-9:
            right = np.cross(direction, [0.0, 1.0, 0.0])
    return direction, right / np.linalg.norm(right)


def task_errors(position: np.ndarray, rotation: np.ndarray, target: ToolTarget) -> tuple[float, float, float]:
    """Position, pointing and true roll errors in metres/radians/radians."""
    direction, desired_right = pointing_basis(position, np.asarray(target.look_at_m), rotation[:, 0])
    actual_forward = rotation[:, 2]
    aim = float(np.arccos(np.clip(actual_forward @ direction, -1.0, 1.0)))
    projected_right = rotation[:, 0] - direction * float(rotation[:, 0] @ direction)
    length = np.linalg.norm(projected_right)
    if length < 1e-12:
        roll = np.pi
    else:
        projected_right /= length
        roll = abs(
            float(
                np.arctan2(
                    direction @ np.cross(desired_right, projected_right), desired_right @ projected_right
                )
            )
        )
    return float(np.linalg.norm(position - np.asarray(target.position_m))), aim, roll


class ArmSolver:
    """Solve position and aim first, then improve roll without leaving their limits."""

    def __init__(self, model: mujoco.MjModel) -> None:
        if model.nq != 13 or model.njnt != 13:
            raise ValueError("Expected three cart coordinates and two five-joint arms")
        self.model = model
        self.data = mujoco.MjData(model)
        # Calibration/model ranges are hard limits. The former 0.04 rad inset is
        # a posture preference below, so it no longer cuts reachable workspace.
        self.lower = model.jnt_range[:, 0] + 1e-7
        self.upper = model.jnt_range[:, 1] - 1e-7
        # Solve inside what the servos can actually reach, not just what the URDF
        # allows. These were only checked after solving, so a solution could sit
        # on a calibration limit the model knew nothing about: that is how the
        # light shoulder ended up commanded to its own mechanical stop.
        from takeone.calibration import ArmMapping

        # Solve inside a hair tighter than we validate. The optimizer settles onto
        # an active bound to ~0.1 deg, which lands one encoder count outside the
        # range the calibration then checks; this inset absorbs that slop without
        # clipping a returned solution.
        inset = math.radians(0.5)
        for offset, role in enumerate(("phone", "light")):
            mapping = ArmMapping.load(role, require_motion=False)
            # With no configured margin the model range already is the calibration
            # range, so leave the solver exactly as it was and add no inset.
            if not mapping.limit_margin_deg:
                continue
            for joint, (low, high) in enumerate(mapping.safe_ranges_rad):
                index = 3 + offset * 5 + joint
                self.lower[index] = max(self.lower[index], low + inset)
                self.upper[index] = min(self.upper[index], high - inset)
        # Only the ten arm joints are constrained here; the three cart coordinates
        # are unlimited slides/hinges and MuJoCo reports a zero range for those.
        if np.any(self.lower[3:] >= self.upper[3:]):
            raise ValueError("Calibration and model joint limits leave no travel; check limit_margin_deg")

    def solve(self, cart_and_joints: np.ndarray, arm: ArmSpec, target: ToolTarget) -> IKResult:
        q = cart_and_joints.copy()
        indices = arm.qpos_slice
        previous = q[indices].copy()
        lower, upper = self.lower[indices], self.upper[indices]
        if not np.isfinite(q).all() or np.any(previous < lower) or np.any(previous > upper):
            raise ValueError(f"{arm.role.value}: invalid IK seed; no silent clipping")
        site = self.model.site(arm.model_prefix + "_optical").id
        desired = np.asarray(target.position_m)
        aim_point = np.asarray(target.look_at_m)
        position_goal = PHONE_POSITION_GOAL_M if arm.role == ArmRole.PHONE else LIGHT_POSITION_GOAL_M
        position_limit = PHONE_POSITION_LIMIT_M if arm.role == ArmRole.PHONE else LIGHT_POSITION_LIMIT_M

        def state(joints: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            q[indices] = joints
            self.data.qpos[:] = q
            mujoco.mj_forward(self.model, self.data)
            return self.data.site_xpos[site].copy(), self.data.site_xmat[site].reshape(3, 3).copy()

        def primary(joints: np.ndarray) -> np.ndarray:
            position, rotation = state(joints)
            direction, _ = pointing_basis(position, aim_point, rotation[:, 0])
            return np.r_[
                (position - desired) / position_goal,
                (rotation[:, 2] - direction) / AIM_LIMIT_RAD,
                0.002 * (joints - previous),
            ]

        midpoint = (lower + upper) / 2
        span = upper - lower
        seeds = [previous, midpoint, lower + 0.25 * span, lower + 0.75 * span]
        candidates = []
        evaluations = 0
        optimizer_terminated = False
        for seed in seeds:
            primary_solution = least_squares(
                primary,
                seed,
                bounds=(lower, upper),
                max_nfev=240,
                ftol=1e-10,
                xtol=1e-10,
                gtol=1e-10,
            )
            evaluations += int(primary_solution.nfev)
            optimizer_terminated |= bool(primary_solution.success)

            def constraints(joints: np.ndarray) -> np.ndarray:
                position, rotation = state(joints)
                direction, _ = pointing_basis(position, aim_point, rotation[:, 0])
                return np.array(
                    [
                        position_limit**2 - float(np.sum((position - desired) ** 2)),
                        float(rotation[:, 2] @ direction) - float(np.cos(AIM_LIMIT_RAD)),
                    ]
                )

            def lower_priority(joints: np.ndarray) -> float:
                position, rotation = state(joints)
                position_error, aim_error, roll_error = task_errors(position, rotation, target)
                margin = np.minimum(joints - lower, upper - joints)
                margin_penalty = np.sum(np.maximum(0.0, PREFERRED_LIMIT_MARGIN_RAD - margin) ** 2)
                return float(
                    (roll_error / ROLL_LIMIT_RAD) ** 2
                    + 0.01 * (position_error / position_goal) ** 2
                    + 0.01 * (aim_error / AIM_LIMIT_RAD) ** 2
                    + 0.002 * np.sum((joints - previous) ** 2)
                    + 0.05 * margin_penalty / PREFERRED_LIMIT_MARGIN_RAD**2
                )

            refined = minimize(
                lower_priority,
                primary_solution.x,
                method="SLSQP",
                bounds=list(zip(lower, upper)),
                constraints={"type": "ineq", "fun": constraints},
                options={"maxiter": 180, "ftol": 1e-10, "disp": False},
            )
            evaluations += int(getattr(refined, "nfev", 0))
            optimizer_terminated |= bool(refined.success)
            for candidate in (refined.x, primary_solution.x):
                position, rotation = state(candidate)
                errors = task_errors(position, rotation, target)
                hard_feasible = errors[0] <= position_limit + 1e-7 and errors[1] <= AIM_LIMIT_RAD + 1e-7
                roll_feasible = arm.role != ArmRole.PHONE or errors[2] <= ROLL_LIMIT_RAD + 1e-7
                score = (
                    not (hard_feasible and roll_feasible),
                    not hard_feasible,
                    max(errors[0] / position_limit, errors[1] / AIM_LIMIT_RAD),
                    errors[2] / ROLL_LIMIT_RAD,
                    errors[0] / position_goal,
                    float(np.linalg.norm(candidate - previous)),
                )
                candidates.append((score, candidate.copy(), errors))
        _, solution, errors = min(candidates, key=lambda item: item[0])
        active = tuple(
            index
            for index, margin in enumerate(np.minimum(solution - lower, upper - solution))
            if margin <= 1e-4
        )
        feasible = (
            errors[0] <= position_limit + 1e-7
            and errors[1] <= AIM_LIMIT_RAD + 1e-7
            and (arm.role != ArmRole.PHONE or errors[2] <= ROLL_LIMIT_RAD + 1e-7)
        )
        return IKResult(
            tuple(solution),
            feasible,
            optimizer_terminated,
            evaluations,
            errors[0],
            float(np.degrees(errors[1])),
            float(np.degrees(errors[2])),
            active,
        )
