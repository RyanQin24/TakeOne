"""Bounded IK service with explicit convergence and independent forward checks."""

from dataclasses import dataclass

import mujoco
import numpy as np
from scipy.optimize import least_squares

from .targets import ArmSpec, ToolTarget


@dataclass(frozen=True, slots=True)
class IKResult:
    joints_rad: tuple[float, ...]
    converged: bool
    evaluations: int


def pointing_basis(position: np.ndarray, look_at: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    direction = np.asarray(look_at, dtype=float) - position
    distance = np.linalg.norm(direction)
    if distance < 1e-9:
        raise ValueError("Look-at target coincides with the solved tool position")
    direction /= distance
    right = np.cross(direction, [0.0, 0.0, 1.0])
    horizontal = np.linalg.norm(right)
    if horizontal < 1e-9:
        raise ValueError("Vertical look-at has no defined horizon; provide a different target")
    return direction, right / horizontal


class ArmSolver:
    """Owns one MuJoCo scratch state for a compile; never shared between requests."""

    def __init__(self, model: mujoco.MjModel) -> None:
        if model.nq != 13 or model.njnt != 13:
            raise ValueError("Expected three cart coordinates and two five-joint arms")
        self.model = model
        self.data = mujoco.MjData(model)
        self.lower = model.jnt_range[:, 0] + 0.04
        self.upper = model.jnt_range[:, 1] - 0.04

    def solve(self, cart_and_joints: np.ndarray, arm: ArmSpec, target: ToolTarget) -> IKResult:
        q = cart_and_joints.copy()
        indices = arm.qpos_slice
        previous = q[indices].copy()
        lower, upper = self.lower[indices], self.upper[indices]
        if not np.isfinite(q).all() or np.any(previous < lower) or np.any(previous > upper):
            raise ValueError(f"{arm.role.value}: invalid IK seed; no silent clipping")
        site = self.model.site(arm.model_prefix + "_optical").id
        desired = np.asarray(target.position_m)
        aim = np.asarray(target.look_at_m)

        def residual(joints: np.ndarray) -> np.ndarray:
            q[indices] = joints
            self.data.qpos[:] = q
            mujoco.mj_forward(self.model, self.data)
            position = self.data.site_xpos[site]
            rotation = self.data.site_xmat[site].reshape(3, 3)
            direction, right = pointing_basis(position, aim)
            return np.r_[
                2 * (position - desired),
                12 * (rotation[:, 2] - direction),
                1.2 * (rotation[:, 0] - right),
                0.004 * (joints - previous),
            ]

        solution = least_squares(
            residual, previous, bounds=(lower, upper), max_nfev=120, ftol=1e-8, xtol=1e-8, gtol=1e-8
        )
        if not np.isfinite(solution.x).all():
            raise ValueError(f"{arm.role.value}: non-finite IK result")
        return IKResult(tuple(solution.x), bool(solution.success), int(solution.nfev))
