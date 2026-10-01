"""Reference URDF forward kinematics and bounded, simulation-only inverse kinematics.

No servo driver is imported. URDF angles are deliberately not treated as calibrated
servo angles. Optical frames use +X forward, +Y left, +Z up.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

try:
    from scipy.optimize import least_squares
except ImportError:
    least_squares = None


def rotation_rpy(rpy: list[float] | np.ndarray) -> np.ndarray:
    """URDF extrinsic roll-pitch-yaw: Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array(
        [[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
         [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
         [-sp, cp * sr, cp * cr]]
    )


def transform(xyz: list[float] | np.ndarray, rpy: list[float] | np.ndarray) -> np.ndarray:
    result = np.eye(4)
    result[:3, :3] = rotation_rpy(rpy)
    result[:3, 3] = xyz
    return result


def axis_rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(angle) * skew + (1 - np.cos(angle)) * (skew @ skew)


def normalize(vector: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(vector)
    if length < 1e-10:
        raise ValueError("A direction cannot be zero.")
    return vector / length


def look_at(position: np.ndarray, target: np.ndarray, roll_rad: float = 0.0) -> np.ndarray:
    """Camera pose with +X looking at target and preferred +Z vertical."""
    forward = normalize(target - position)
    up_hint = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(forward, up_hint)) > 0.999:
        up_hint = np.array([0.0, 1.0, 0.0])
    left = normalize(np.cross(up_hint, forward))
    up = np.cross(forward, left)
    rotation = np.column_stack((forward, left, up)) @ rotation_rpy([roll_rad, 0, 0])
    pose = np.eye(4)
    pose[:3, :3] = rotation
    pose[:3, 3] = position
    return pose


class ReferenceArm:
    """Five revolute joints copied exactly from the official SO101 URDF chain."""

    def __init__(self, model: dict, arm_config: dict):
        self.model = model
        self.config = arm_config
        self.names = [joint["name"] for joint in model["joints"]]
        self.origins = [transform(j["xyz"], j["rpy"]) for j in model["joints"]]
        self.axes = [np.array(j["axis"], dtype=float) for j in model["joints"]]
        self.limits = np.array([j["limits_rad"] for j in model["joints"]])
        self.mount = transform(arm_config["lens_mount_xyz_m"], arm_config["lens_mount_rpy_rad"])
        self.base = transform(arm_config["base_xyz_m"], arm_config["base_rpy_rad"])

    @classmethod
    def from_files(cls, model_path: str | Path, rig_path: str | Path, role: str) -> ReferenceArm:
        return cls(json.loads(Path(model_path).read_text()), json.loads(Path(rig_path).read_text())["arms"][role])

    def fk(self, q_rad: np.ndarray, cart_pose: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        if len(q_rad) != 5 or not np.isfinite(q_rad).all():
            raise ValueError("Five finite URDF joint angles are required.")
        pose = (np.eye(4) if cart_pose is None else cart_pose) @ self.base
        points = [pose[:3, 3].copy()]
        for angle, origin, axis in zip(q_rad, self.origins, self.axes, strict=True):
            joint_rotation = np.eye(4)
            joint_rotation[:3, :3] = axis_rotation(axis, angle)
            pose = pose @ origin @ joint_rotation
            points.append(pose[:3, 3].copy())
        optical_pose = pose @ self.mount
        points.append(optical_pose[:3, 3].copy())
        return optical_pose, np.array(points)

    def solve(
        self,
        desired_pose: np.ndarray,
        seed_rad: np.ndarray,
        cart_pose: np.ndarray | None = None,
        roll_weight: float = 0.0,
    ) -> dict:
        """Bounded numerical IK; position+pointing tasks, optional optical roll.

        SciPy is used because the existing LeRobot Placo adapter exposes a full
        orientation task, while this preview needs an explicitly underactuated
        pointing task. Every result is independently checked with FK.
        """
        if least_squares is None:
            raise ImportError("Preview IK requires scipy. Install lerobot[scipy-dep].")
        seed = np.clip(seed_rad, self.limits[:, 0] + 1e-8, self.limits[:, 1] - 1e-8)

        def residual(q: np.ndarray) -> np.ndarray:
            actual, _ = self.fk(q, cart_pose)
            terms = [(actual[:3, 3] - desired_pose[:3, 3]) / 0.01,
                     (actual[:3, 0] - desired_pose[:3, 0]) / np.deg2rad(3)]
            if roll_weight:
                terms.append(roll_weight * (actual[:3, 2] - desired_pose[:3, 2]) / np.deg2rad(5))
            terms.append(0.001 * (q - seed))
            return np.concatenate(terms)

        result = least_squares(residual, seed, bounds=(self.limits[:, 0], self.limits[:, 1]), max_nfev=100,
                               ftol=1e-8, xtol=1e-8, gtol=1e-8)
        actual, points = self.fk(result.x, cart_pose)
        pointing_error = np.rad2deg(np.arccos(np.clip(np.dot(actual[:3, 0], desired_pose[:3, 0]), -1, 1)))
        # Roll compares projected up axes around the achieved optical direction.
        forward = actual[:3, 0]
        desired_up = desired_pose[:3, 2] - np.dot(desired_pose[:3, 2], forward) * forward
        roll_error = np.rad2deg(np.arccos(np.clip(np.dot(actual[:3, 2], normalize(desired_up)), -1, 1)))
        return {"q_rad": result.x, "pose": actual, "points": points, "solver_converged": bool(result.success),
                "position_error_m": float(np.linalg.norm(actual[:3, 3] - desired_pose[:3, 3])),
                "pointing_error_deg": float(pointing_error), "roll_error_deg": float(roll_error)}
