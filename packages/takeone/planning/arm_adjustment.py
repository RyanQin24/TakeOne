"""Offline arm endpoint geometry using existing FK, bounded IK and encoder mapping.

Not a trajectory, live-state reader, collision proof, or executable artifact.
"""

import math

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from takeone.calibration import ArmMapping
from takeone.planning.kinematics import ArmSolver, task_errors
from takeone.planning.targets import ARMS, ToolTarget
from takeone.simulation.robot import load_model
from takeone.voice.arm_intent import prepare_arm_intent


def resolve_target(position, rotation, cart_yaw, prepared, targets=None):
    """Compose ordered translations/rotations in explicit right-handed frames.

    Optical axes are right +X, down +Y, forward +Z. Chassis travel forward is -X,
    right +Y, up +Z. Targets are supplied by trusted local context, never by the LLM.
    """
    if prepared["questions"]:
        raise ValueError("Resolve all clarification questions before geometric evaluation")
    p, r = np.array(position, dtype=float), np.array(rotation, dtype=float)
    if p.shape != (3,) or r.shape != (3, 3) or not np.isfinite(p).all() or not np.isfinite(r).all():
        raise ValueError("Finite position and rotation required")
    if not np.allclose(r.T @ r, np.eye(3), atol=1e-8) or not np.isclose(np.linalg.det(r), 1):
        raise ValueError("Expected a proper rotation matrix")
    if not math.isfinite(cart_yaw):
        raise ValueError("Finite chassis yaw required")
    chassis = Rotation.from_euler("z", cart_yaw).as_matrix()
    for operation in prepared["intent"]["operations"]:
        action, amount, frame = (operation[k] for k in ("action", "amount", "frame"))
        right, up, forward = r[:, 0], -r[:, 1], r[:, 2]
        if action == "face_target":
            label = operation["target"]
            if not targets or label not in targets:
                raise ValueError(f"Target {label!r} has no locally supplied position")
            target = np.asarray(targets[label], dtype=float)
            if target.shape != (3,) or not np.isfinite(target).all():
                raise ValueError("Target needs three finite world coordinates")
            direction = target - p
            length = np.linalg.norm(direction)
            if length < 1e-6:
                raise ValueError("Target coincides with the camera")
            direction /= length
            # Shortest optical rotation retains roll continuity; antipodal aim is ambiguous.
            axis = np.cross(forward, direction)
            sine, cosine = np.linalg.norm(axis), np.clip(forward @ direction, -1, 1)
            if sine < 1e-8 and cosine < 0:
                raise ValueError("180-degree aim is ambiguous; choose an intermediate direction")
            if sine > 1e-8:
                r = Rotation.from_rotvec(axis / sine * math.atan2(sine, cosine)).as_matrix() @ r
        elif action.startswith(("pan_", "tilt_", "roll_")):
            axis = up if action.startswith("pan_") else right if action.startswith("tilt_") else forward
            sign = 1 if action in ("pan_left", "tilt_up", "roll_right") else -1
            r = Rotation.from_rotvec(axis * sign * amount).as_matrix() @ r
        else:
            if frame == "tool":
                axes = dict(
                    raise_=up, lower=-up, left=-right, right=right, forward=forward, backward=-forward
                )
            else:
                axes = dict(
                    raise_=np.array([0.0, 0.0, 1.0]),
                    lower=np.array([0.0, 0.0, -1.0]),
                    left=-chassis[:, 1],
                    right=chassis[:, 1],
                    forward=-chassis[:, 0],
                    backward=chassis[:, 0],
                )
            p += amount * axes["raise_" if action == "raise" else action]
    return ToolTarget(tuple(p), tuple(p + r[:, 2]), tuple(r[:, 0]))


def preview_adjustment(request, qpos, *, targets=None, light_type="ring"):
    """Explicit caller-supplied model pose; never impersonates measured live state."""
    prepared = prepare_arm_intent(request)
    q = np.asarray(qpos, dtype=float)
    if q.shape != (13,) or not np.isfinite(q).all():
        raise ValueError("Provide all 13 finite model coordinates; no assumed current pose")
    if prepared["questions"]:
        return prepared
    model = load_model(light_type)
    solver = ArmSolver(model)
    if np.any(q[3:] < solver.lower[3:]) or np.any(q[3:] > solver.upper[3:]):
        raise ValueError("Initial arm pose is outside calibrated model limits")
    arm = next(a for a in ARMS if a.role.value == request["role"])
    data = mujoco.MjData(model)
    data.qpos[:] = q
    mujoco.mj_forward(model, data)
    site = model.site(arm.model_prefix + "_optical").id
    initial_position = data.site_xpos[site].copy()
    initial_rotation = data.site_xmat[site].reshape(3, 3).copy()
    # Retain intermediate geometric endpoints, even when a later aim supersedes a tilt.
    # These are not validated intermediate joint paths or permission to skip a clause.
    steps = []
    for count in range(1, len(prepared["intent"]["operations"]) + 1):
        prefix = prepared | {
            "intent": prepared["intent"] | {"operations": prepared["intent"]["operations"][:count]}
        }
        step = resolve_target(initial_position, initial_rotation, q[2], prefix, targets)
        steps.append(
            dict(
                position_m=list(step.position_m),
                look_at_m=list(step.look_at_m),
                right_axis=list(step.right_axis),
            )
        )
    target = step
    result = solver.solve(q, arm, target)
    candidate = q.copy()
    candidate[arm.qpos_slice] = result.joints_rad
    mapping = ArmMapping.load(arm.role.value, require_motion=False)
    # Exact encoder conversion; no clipping a failed solution into validity.
    raw = mapping.to_raw(result.joints_rad)
    candidate[arm.qpos_slice] = mapping.from_raw(raw)
    data.qpos[:] = candidate
    mujoco.mj_forward(model, data)
    position_error, aim_error, roll_error = task_errors(
        data.site_xpos[site], data.site_xmat[site].reshape(3, 3), target
    )
    # Tighter relative endpoint screen than full-shot corridor: do not accept 'lower'
    # when a loose 2-cm solver tolerance swallowed a 2-cm requested change.
    requested_translation = float(np.linalg.norm(np.asarray(target.position_m) - initial_position))
    position_tolerance = min(0.003, requested_translation * 0.25) if requested_translation > 1e-9 else 0.003
    feasible = bool(
        result.converged
        and position_error <= position_tolerance
        and aim_error <= math.radians(1)
        and roll_error <= math.radians(2)
    )
    return prepared | dict(
        ok=feasible,
        code="offline_endpoint_preview" if feasible else "endpoint_infeasible",
        endpoint_feasible=feasible,
        pose_source="caller_supplied_model_coordinates_not_live_feedback",
        requested_position_m=list(target.position_m),
        requested_forward=np.subtract(target.look_at_m, target.position_m).tolist(),
        achieved_position_m=data.site_xpos[site].tolist(),
        position_error_m=float(position_error),
        position_tolerance_m=position_tolerance,
        ordered_geometric_endpoints=steps,
        intermediate_endpoints_solved=False,
        aim_error_deg=math.degrees(aim_error),
        roll_error_deg=math.degrees(roll_error),
        candidate_model_qpos=candidate.tolist(),
        cart_changed=False,
        other_arm_changed=False,
        trajectory_validated=False,
        collision_checked=False,
    )
