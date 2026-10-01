"""Forward-kinematics validation of the interpolated plan, not just IK keyframes."""

from dataclasses import dataclass

import mujoco
import numpy as np

from takeone.simulation import drive
from takeone.simulation.robot import pose_frame

from .curve import dispatch_times
from .kinematics import (
    AIM_LIMIT_RAD,
    LIGHT_POSITION_GOAL_M,
    LIGHT_POSITION_LIMIT_M,
    PHONE_POSITION_GOAL_M,
    PHONE_POSITION_LIMIT_M,
    ROLL_LIMIT_RAD,
    task_errors,
)
from .targets import ARMS, ArmRole, actor_target
from .trajectory import JointTrajectory


@dataclass(slots=True)
class PlanEvaluation:
    frames: list[dict]
    checks: list[dict]
    camera_heights_m: list[float]
    height_revision_required: bool
    metrics: dict

    @property
    def playable(self) -> bool:
        return self.plan_valid and self.fidelity_passed

    @property
    def plan_valid(self) -> bool:
        excluded = {
            "Optimizer termination",
            "Assumed payload margin",
            "Camera height request",
            "Phone position request",
            "Light position request",
            "Phone preferred position",
            "Light preferred position",
            "Aim at actor",
            "Horizon preference",
            "Encoded phone position request",
            "Encoded light position request",
            "Encoded aim at actor",
            "Encoded horizon preference",
        }
        return all(item["passed"] for item in self.checks if item["name"] not in excluded)

    @property
    def fidelity_passed(self) -> bool:
        names = {
            "Camera height request",
            "Phone position request",
            "Light position request",
            "Aim at actor",
            "Horizon preference",
            "Encoded phone position request",
            "Encoded light position request",
            "Encoded aim at actor",
            "Encoded horizon preference",
        }
        return all(item["passed"] for item in self.checks if item["name"] in names)


def check(name: str, passed: bool, value: float, unit: str, digits: int = 3) -> dict:
    return dict(name=name, passed=bool(passed), value=round(float(value), digits), unit=unit)


def evaluate_plan(
    model,
    settings: dict,
    trajectory: JointTrajectory,
    programs: dict,
    drive_report: dict,
    *,
    mappings: dict,
    dispatch_period_s: float,
) -> PlanEvaluation:
    data = mujoco.MjData(model)
    sites = {arm.role: model.site(arm.model_prefix + "_optical").id for arm in ARMS}
    camera_site = sites[ArmRole.PHONE]
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
    frames, height_errors, demand, clearance, behind = [], [], [], [], []
    position_errors = {arm.role: [] for arm in ARMS}
    position_vectors = {arm.role: [] for arm in ARMS}
    aim_errors = {arm.role: [] for arm in ARMS}
    roll_errors = {arm.role: [] for arm in ARMS}
    achieved_positions = {arm.role: [] for arm in ARMS}
    requested_positions = {arm.role: [] for arm in ARMS}

    for index, q in enumerate(trajectory.q):
        frame = pose_frame(model, data, q, trajectory.time_s[index], trajectory.drive_frames[index])
        phase = trajectory.time_s[index] / settings["duration"]
        subject = actor_target(settings, phase)
        for arm in ARMS:
            target = programs[arm.role].at(phase, q[:3], subject)
            position = data.site_xpos[sites[arm.role]]
            rotation = data.site_xmat[sites[arm.role]].reshape(3, 3)
            position_error, aim_error, roll_error = task_errors(position, rotation, target)
            position_errors[arm.role].append(position_error)
            position_vectors[arm.role].append((position - np.asarray(target.position_m)).tolist())
            achieved_positions[arm.role].append(position.tolist())
            requested_positions[arm.role].append(list(target.position_m))
            aim_errors[arm.role].append(float(np.degrees(aim_error)))
            roll_errors[arm.role].append(float(np.degrees(roll_error)))
            if arm.role == ArmRole.PHONE:
                height_errors.append(abs(position[2] - target.position_m[2]))

        frames.append(frame)
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

    # Replay the exact integer count conversion used by the real adapters at
    # every arm dispatch instant, then evaluate those representable joints by
    # FK. The mapping arithmetic is exact; physical tool alignment is still an
    # independent measurement prerequisite.
    encoded_errors = {arm.role: [] for arm in ARMS}
    encoded_vectors = {arm.role: [] for arm in ARMS}
    encoded_aim = {arm.role: [] for arm in ARMS}
    encoded_roll = {arm.role: [] for arm in ARMS}
    encoded_requested = {arm.role: [] for arm in ARMS}
    encoded_achieved = {arm.role: [] for arm in ARMS}
    encoding_failures = {arm.role: 0 for arm in ARMS}
    encoded_times = dispatch_times(settings["duration"], dispatch_period_s)
    for elapsed in encoded_times:
        cart = np.asarray(drive.sample(trajectory.motion, elapsed)["cart"])
        encoded_joints = np.asarray(trajectory.curve.at(elapsed))
        for arm in ARMS:
            local = slice(arm.qpos_start - 3, arm.qpos_start + 2)
            mapping = mappings[arm.role]
            try:
                encoded_joints[local] = mapping.from_raw(mapping.encode(encoded_joints[local]))
            except ValueError:
                # An infeasible request must remain inspectable in the simulator.
                # Keep its finite planned joints for diagnostic FK, record that
                # no representable command exists, and fail the plan below.
                encoding_failures[arm.role] += 1
        q = np.r_[cart, encoded_joints]
        data.qpos[:] = q
        mujoco.mj_forward(model, data)
        phase = elapsed / settings["duration"]
        subject = actor_target(settings, phase)
        for arm in ARMS:
            target = programs[arm.role].at(phase, cart, subject)
            position = data.site_xpos[sites[arm.role]]
            rotation = data.site_xmat[sites[arm.role]].reshape(3, 3)
            position_error, aim_error, roll_error = task_errors(position, rotation, target)
            encoded_errors[arm.role].append(position_error)
            encoded_vectors[arm.role].append((position - np.asarray(target.position_m)).tolist())
            encoded_aim[arm.role].append(float(np.degrees(aim_error)))
            encoded_roll[arm.role].append(float(np.degrees(roll_error)))
            encoded_requested[arm.role].append(list(target.position_m))
            encoded_achieved[arm.role].append(position.tolist())

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
    stage_terminations = [
        value for name, value in trajectory.coordination.items() if name.endswith("_optimizer_terminated")
    ]
    failed_terminations = (
        sum(not value for value in stage_terminations)
        if stage_terminations
        else sum(not result.optimizer_terminated for result in trajectory.solves)
    )
    maximum_aim = max(max(values) for values in aim_errors.values())
    maximum_phone_roll = max(roll_errors[ArmRole.PHONE])
    checks = [
        check("Optimizer termination", failed_terminations == 0, failed_terminations, "failed stages", 0),
        check("IK task feasibility", failed_solves == 0, failed_solves, "failed solves", 0),
        check("Aim at actor", maximum_aim <= np.degrees(AIM_LIMIT_RAD), maximum_aim, "° max"),
        check(
            "Horizon preference",
            maximum_phone_roll <= np.degrees(ROLL_LIMIT_RAD),
            maximum_phone_roll,
            "° camera roll max",
        ),
        # Extend the existing 2 cm height policy to each complete requested position.
        # This is a model fidelity screen, not a physical accuracy qualification.
        check(
            "Phone position request",
            max(position_errors[ArmRole.PHONE]) <= PHONE_POSITION_LIMIT_M,
            max(position_errors[ArmRole.PHONE]) * 100,
            "cm max",
        ),
        check(
            "Light position request",
            max(position_errors[ArmRole.LIGHT]) <= LIGHT_POSITION_LIMIT_M,
            max(position_errors[ArmRole.LIGHT]) * 100,
            "cm max",
        ),
        check(
            "Phone preferred position",
            max(position_errors[ArmRole.PHONE]) <= PHONE_POSITION_GOAL_M,
            max(position_errors[ArmRole.PHONE]) * 100,
            "cm max; warning above 1 cm",
        ),
        check(
            "Light preferred position",
            max(position_errors[ArmRole.LIGHT]) <= LIGHT_POSITION_GOAL_M,
            max(position_errors[ArmRole.LIGHT]) * 100,
            "cm max; stricter 2 cm comparison",
        ),
        check(
            "Encoder operating ranges",
            sum(encoding_failures.values()) == 0,
            sum(encoding_failures.values()),
            "failed arm dispatch samples",
            0,
        ),
        check(
            "Encoded phone position request",
            max(encoded_errors[ArmRole.PHONE]) <= PHONE_POSITION_LIMIT_M,
            max(encoded_errors[ArmRole.PHONE]) * 100,
            "cm max after integer encoder conversion",
        ),
        check(
            "Encoded light position request",
            max(encoded_errors[ArmRole.LIGHT]) <= LIGHT_POSITION_LIMIT_M,
            max(encoded_errors[ArmRole.LIGHT]) * 100,
            "cm max after integer encoder conversion",
        ),
        check(
            "Encoded aim at actor",
            max(max(values) for values in encoded_aim.values()) <= np.degrees(AIM_LIMIT_RAD),
            max(max(values) for values in encoded_aim.values()),
            "° max after integer encoder conversion",
        ),
        check(
            "Encoded horizon preference",
            max(encoded_roll[ArmRole.PHONE]) <= np.degrees(ROLL_LIMIT_RAD),
            max(encoded_roll[ArmRole.PHONE]),
            "° camera roll max after integer encoder conversion",
        ),
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
    metrics = {}
    for arm in ARMS:
        role = arm.role
        worst = int(np.argmax(position_errors[role]))
        metrics[role.value] = dict(
            position_max_m=max(position_errors[role]),
            position_rms_m=float(np.sqrt(np.mean(np.square(position_errors[role])))),
            position_goal_m=PHONE_POSITION_GOAL_M if role == ArmRole.PHONE else LIGHT_POSITION_GOAL_M,
            position_limit_m=PHONE_POSITION_LIMIT_M if role == ArmRole.PHONE else LIGHT_POSITION_LIMIT_M,
            aim_max_deg=max(aim_errors[role]),
            roll_max_deg=max(roll_errors[role]),
            worst_aim_time_s=float(trajectory.time_s[int(np.argmax(aim_errors[role]))]),
            worst_roll_time_s=float(trajectory.time_s[int(np.argmax(roll_errors[role]))]),
            worst_position=dict(
                time_s=float(trajectory.time_s[worst]),
                requested_m=requested_positions[role][worst],
                achieved_m=achieved_positions[role][worst],
                error_vector_m=position_vectors[role][worst],
                error_m=position_errors[role][worst],
            ),
        )
        encoded_worst = int(np.argmax(encoded_errors[role]))
        metrics[role.value]["command_stage"] = dict(
            mapping_status=(
                "nominal calibration mapping; physical tool alignment remains unverified"
                if encoding_failures[role] == 0
                else "planned joints exceeded the configured encoder operating range"
            ),
            encoding_failures=encoding_failures[role],
            dispatch_samples=len(encoded_times),
            position_max_m=max(encoded_errors[role]),
            position_rms_m=float(np.sqrt(np.mean(np.square(encoded_errors[role])))),
            aim_max_deg=max(encoded_aim[role]),
            roll_max_deg=max(encoded_roll[role]),
            worst_position=dict(
                time_s=float(encoded_times[encoded_worst]),
                requested_m=encoded_requested[role][encoded_worst],
                achieved_m=encoded_achieved[role][encoded_worst],
                error_vector_m=encoded_vectors[role][encoded_worst],
                error_m=encoded_errors[role][encoded_worst],
            ),
        )
    return PlanEvaluation(
        frames,
        checks,
        [frame["camera"]["pos"][2] for frame in frames],
        max(height_errors) > PHONE_POSITION_LIMIT_M,
        metrics,
    )
