"""Forward-kinematics validation of the interpolated plan, not just IK keyframes."""

from dataclasses import dataclass

import mujoco
import numpy as np

from takeone.simulation.robot import matrix_quat

from .kinematics import pointing_basis
from .targets import ARMS, ArmRole, actor_target
from .trajectory import JointTrajectory


@dataclass(slots=True)
class PlanEvaluation:
    frames: list[dict]
    checks: list[dict]
    camera_heights_m: list[float]
    height_revision_required: bool

    @property
    def playable(self) -> bool:
        preview_only = {"Assumed payload margin", "Camera height request"}
        return all(check["passed"] for check in self.checks if check["name"] not in preview_only)


def check(name: str, passed: bool, value: float, unit: str, digits: int = 3) -> dict:
    return dict(name=name, passed=bool(passed), value=round(float(value), digits), unit=unit)


def evaluate_plan(
    model, settings: dict, trajectory: JointTrajectory, programs: dict, drive_report: dict
) -> PlanEvaluation:
    data = mujoco.MjData(model)
    sites = {arm.role: model.site(arm.model_prefix + "_optical").id for arm in ARMS}
    camera_site, light_site = sites[ArmRole.PHONE], sites[ArmRole.LIGHT]
    camera_geoms = [
        g
        for g in range(model.ngeom)
        if model.body(model.geom_bodyid[g]).name.startswith("cam_") and model.geom_group[g] != 2
    ]
    light_geoms = [
        g
        for g in range(model.ngeom)
        if model.body(model.geom_bodyid[g]).name.startswith("light_") and model.geom_group[g] != 2
    ]
    entire_light = [
        g for g in range(model.ngeom) if model.body(model.geom_bodyid[g]).name.startswith("light_")
    ]
    frames, aim_errors, height_errors, demand, clearance, behind = [], [], [], [], [], []

    for index, q in enumerate(trajectory.q):
        data.qpos[:] = q
        data.qvel[:] = 0
        mujoco.mj_forward(model, data)
        phase = trajectory.time_s[index] / settings["duration"]
        subject = actor_target(settings, phase)
        for arm in ARMS:
            target = programs[arm.role].at(phase, q[:3], subject)
            position = data.site_xpos[sites[arm.role]]
            direction, _ = pointing_basis(position, np.asarray(target.look_at_m))
            actual_forward = data.site_xmat[sites[arm.role]].reshape(3, 3)[:, 2]
            aim_errors.append(float(np.degrees(np.arccos(np.clip(actual_forward @ direction, -1, 1)))))
            if arm.role == ArmRole.PHONE:
                height_errors.append(abs(position[2] - target.position_m[2]))

        frames.append(
            dict(
                q=q.tolist(),
                drive=trajectory.drive_frames[index],
                bodies=np.c_[data.xpos, data.xquat[:, 1:], data.xquat[:, 0]].tolist(),
                camera=dict(
                    pos=data.site_xpos[camera_site].tolist(), quat=matrix_quat(data.site_xmat[camera_site])
                ),
                light=dict(
                    pos=data.site_xpos[light_site].tolist(), quat=matrix_quat(data.site_xmat[light_site])
                ),
            )
        )
        forward = data.site_xmat[camera_site].reshape(3, 3)[:, 2]
        behind.append(
            min(
                -float((data.geom_xpos[g] - data.site_xpos[camera_site]) @ forward) - model.geom_rbound[g]
                for g in entire_light
            )
        )
        # Expensive distance and inverse-dynamics screens remain explicitly sampled.
        if index % 8 == 0:
            clearance.append(
                min(
                    mujoco.mj_geomDistance(model, data, a, b, 0.5, None)
                    for a in camera_geoms
                    for b in light_geoms
                )
            )
            data.qvel[:] = trajectory.velocity[index]
            data.qacc[:] = trajectory.acceleration[index]
            mujoco.mj_inverse(model, data)
            demand.append(float(np.max(abs(data.qfrc_inverse[3:]))))

    joint_positions = trajectory.q[:, 3:]
    margin = float(
        np.min(np.minimum(joint_positions - model.jnt_range[3:, 0], model.jnt_range[3:, 1] - joint_positions))
    )
    speed, acceleration, jerk = (
        float(np.max(abs(values[:, 3:])))
        for values in (trajectory.velocity, trajectory.acceleration, trajectory.jerk)
    )
    cart_speed = float(np.max(np.linalg.norm(trajectory.velocity[:, :2], axis=1)))
    failed_solves = sum(not result.converged for result in trajectory.solves)
    checks = [
        check("IK convergence", failed_solves == 0, failed_solves, "failed solves", 0),
        check("Aim at actor", max(aim_errors) < 1.0, max(aim_errors), "° max"),
        check("Joint limits", margin > 0.01, np.degrees(margin), "° margin", 2),
        check("Arm speed", speed < 0.8, speed, "rad/s"),
        check("Arm acceleration", acceleration < 1.8, acceleration, "rad/s²"),
        check("Arm jerk", jerk < 12, jerk, "rad/s³"),
        check("Cart speed", cart_speed <= 0.25, cart_speed, "m/s"),
        check(
            "Motor command caps",
            not drive_report["commandClipped"],
            drive_report["commandCap"],
            "± command cap",
        ),
        check(
            "UART path agreement",
            drive_report["reproducesRequestedPath"],
            drive_report["maxPathError"] * 100,
            "cm max error",
            1,
        ),
        check("Sampled arm clearance", min(clearance) > 0.015, min(clearance) * 100, "cm", 1),
        check("Light behind camera", min(behind) > 0.025, min(behind) * 100, "cm min behind lens", 1),
        check(
            "Camera height request", max(height_errors) <= 0.02, max(height_errors) * 100, "cm adjustment", 1
        ),
        check("Assumed payload margin", max(demand) < 0.8, max(demand), "N·m / 0.800 allowed"),
    ]
    return PlanEvaluation(
        frames, checks, [frame["camera"]["pos"][2] for frame in frames], max(height_errors) > 0.02
    )
