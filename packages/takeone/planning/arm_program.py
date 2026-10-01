"""General relative-pose programs -> bounded joint curves and sampled FK rehearsal.

No hardware imports, live pose guesses, collision qualification, or execution authority.
"""

import math
from dataclasses import dataclass

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from takeone.calibration import ArmMapping
from takeone.config import provenance
from takeone.motion.limits import ArmTiming, execution_limits
from takeone.motion.plan import digest
from takeone.planning.curve import JointCurve, dispatch_times, quintic
from takeone.planning.kinematics import ArmSolver, task_errors
from takeone.planning.targets import ARMS, ToolTarget
from takeone.simulation.robot import load_model
from takeone.voice.arm_program import prepare_program


@dataclass(frozen=True)
class ArmProgramPlan:
    """Same curve interface used by ArmRunner; not a hardware permission."""

    curve: JointCurve
    period_s: float

    @property
    def duration_s(self):
        return self.curve.duration_s

    def arm_at(self, role, elapsed_s, derivative=0):
        if role not in ("phone", "light"):
            raise ValueError("Unknown arm role")
        start = 0 if role == "phone" else 5
        return self.curve.at(elapsed_s, derivative)[start : start + 5]

    def dispatch_times(self, period_s=None):
        if period_s is not None and period_s != self.period_s:
            raise ValueError("Dispatch policy changed; recompile")
        # Floating segment sums can make ceil(duration / period) one too large.
        # Never dispatch the terminal pose twice or with a near-zero interval.
        ticks = dispatch_times(self.duration_s, self.period_s)
        return tuple(t for t in ticks if t < self.duration_s - 1e-9) + (self.duration_s,)

    @property
    def phone(self):
        return tuple(self.arm_at("phone", t) for t in self.dispatch_times())

    @property
    def light(self):
        return tuple(self.arm_at("light", t) for t in self.dispatch_times())


def target_pose(position, rotation, cart_yaw, segment, targets=None):
    """Vectors are expressed in the frame at segment START, not a moving frame."""
    basis = {
        "world": np.eye(3),
        "chassis": Rotation.from_euler("z", cart_yaw).as_matrix(),
        "optical": rotation,
    }[segment["frame"]]
    p = np.asarray(position) + basis @ np.asarray(segment["translation_m"])
    r = Rotation.from_rotvec(basis @ np.asarray(segment["rotation_rad"])).as_matrix() @ rotation
    label = segment["aim_target"]
    if label:
        if not targets or label not in targets:
            raise ValueError("Selected-person target is unavailable; no location will be guessed")
        point = np.asarray(targets[label], dtype=float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError("Local target requires three finite world coordinates")
        direction = point - p
        if np.linalg.norm(direction) < 1e-6:
            raise ValueError("Aim target coincides with the tool")
        direction /= np.linalg.norm(direction)
        axis = np.cross(r[:, 2], direction)
        sine, cosine = np.linalg.norm(axis), np.clip(r[:, 2] @ direction, -1, 1)
        if sine < 1e-8 and cosine < 0:
            raise ValueError("180-degree aim needs an explicit intermediate direction")
        if sine > 1e-8:
            r = Rotation.from_rotvec(axis / sine * math.atan2(sine, cosine)).as_matrix() @ r
    return p, r


def tool_target(p, r):
    return ToolTarget(tuple(p), tuple(p + r[:, 2]), tuple(r[:, 0]))


def rehearsal_pose():
    """An explicitly synthetic start, NEVER a fallback for unavailable hardware feedback."""
    model = load_model()
    solver = ArmSolver(model)
    q = (solver.lower + solver.upper) / 2
    q[:3] = 0
    for arm in ARMS:
        mapping = ArmMapping.load(arm.role.value, require_motion=False)
        q[arm.qpos_slice] = mapping.from_raw(mapping.to_raw(q[arm.qpos_slice]))
    return q.tolist()


def compile_program(request, qpos, *, pose_source, targets=None):
    prepared = prepare_program(request)
    if pose_source not in ("simulated", "measured_snapshot"):
        raise ValueError("Starting-pose source must be explicit")
    if prepared["program"]["questions"]:
        return prepared
    q = np.asarray(qpos, dtype=float)
    if q.shape != (13,) or not np.isfinite(q).all():
        raise ValueError("All 13 finite starting coordinates are required")
    sources = provenance()
    model, timing = load_model(), ArmTiming.load()
    solver, data = ArmSolver(model), mujoco.MjData(model)
    if np.any(q[3:] < solver.lower[3:]) or np.any(q[3:] > solver.upper[3:]):
        raise ValueError("Start is outside calibrated model bounds")
    initial = q.copy()
    role = request["role"]
    arm = next(a for a in ARMS if a.role.value == role)
    mapping = ArmMapping.load(role, require_motion=False)
    limits = execution_limits(role, "commissioning")
    site = model.site(arm.model_prefix + "_optical").id
    knots, coefficients, segment_reports, frames = [0.0], [], [], []
    faults = []

    def fk(pose):
        data.qpos[:] = pose
        mujoco.mj_forward(model, data)
        return data.site_xpos[site].copy(), data.site_xmat[site].reshape(3, 3).copy()

    desired_p, desired_r = fk(q)
    for index, segment in enumerate(prepared["program"]["segments"]):
        start_p, start_r = desired_p.copy(), desired_r.copy()
        try:
            desired_p, desired_r = target_pose(start_p, start_r, q[2], segment, targets)
        except ValueError as error:
            faults.append(dict(segment=index, reason=str(error)))
            break
        target = tool_target(desired_p, desired_r)
        result = solver.solve(q, arm, target)
        # Refine the existing solve for small relative moves: the shot solver's
        # centimetre corridor must not swallow a millimetre adjustment.
        candidate = q.copy()

        def residual(joints):
            candidate[arm.qpos_slice] = joints
            p, r = fk(candidate)
            angle = Rotation.from_matrix(desired_r @ r.T).as_rotvec()
            return np.r_[(p - desired_p) / 0.003, angle / math.radians(1)]

        refined = least_squares(
            residual,
            result.joints_rad,
            bounds=(solver.lower[arm.qpos_slice], solver.upper[arm.qpos_slice]),
            max_nfev=150,
            ftol=1e-9,
            xtol=1e-9,
            gtol=1e-9,
        )
        candidate[arm.qpos_slice] = refined.x
        delta = np.abs(candidate[arm.qpos_slice] - q[arm.qpos_slice])
        minimum = max(
            0.4,
            float(np.max(1.875 * delta / limits.velocity_rad_s)),
            float(np.max(np.sqrt(5.774 * delta / limits.acceleration_rad_s2))),
            float(np.max(np.cbrt(60 * delta / limits.jerk_rad_s3))),
        )
        supplied = segment["duration_s"]
        duration = (
            supplied
            if supplied is not None
            else math.ceil(max(1.0, minimum * 1.1) / timing.period_s) * timing.period_s
        )
        if duration < minimum - 1e-9:
            faults.append(
                dict(
                    segment=index,
                    reason="Requested duration exceeds joint derivative policy",
                    minimum_duration_s=minimum,
                )
            )
            break
        if knots[-1] + duration > 120:
            faults.append(dict(segment=index, reason="Finite program exceeds 120 seconds"))
            break
        zero = (0.0,) * 10
        coeff = quintic(q[3:], zero, zero, candidate[3:], zero, zero, duration)
        piece = JointCurve((0.0, duration), (coeff,))
        translation = float(np.linalg.norm(desired_p - start_p))
        rotvec = Rotation.from_matrix(desired_r @ start_r.T).as_rotvec()
        angle = float(np.linalg.norm(rotvec))
        position_cap = min(0.003, translation / 4) if translation > 1e-8 else 0.003
        orientation_cap = min(math.radians(1), angle / 4) if angle > 1e-8 else math.radians(1)
        errors = []
        # Include every dispatch and its midpoint, as well as segment endpoints.
        ticks = dispatch_times(duration, timing.period_s)
        samples = sorted(set((*ticks, *((a + b) / 2 for a, b in zip(ticks, ticks[1:])))))
        for t in samples:
            phase = t / duration
            ease = 10 * phase**3 - 15 * phase**4 + 6 * phase**5
            want_p = start_p + (desired_p - start_p) * ease
            want_r = Rotation.from_rotvec(rotvec * ease).as_matrix() @ start_r
            sample = initial.copy()
            sample[3:] = piece.at(t)
            sample[arm.qpos_slice] = mapping.from_raw(mapping.to_raw(sample[arm.qpos_slice]))
            actual_p, actual_r = fk(sample)
            pos, aim, roll = task_errors(actual_p, actual_r, tool_target(want_p, want_r))
            errors.append((pos, aim, roll))
            frames.append(
                dict(
                    time_s=knots[-1] + t,
                    qpos=sample.tolist(),
                    position_m=actual_p.tolist(),
                    desired_position_m=want_p.tolist(),
                    forward=actual_r[:, 2].tolist(),
                )
            )
        maxima = np.max(errors, axis=0)
        passed = bool(
            maxima[0] <= position_cap
            and maxima[1] <= orientation_cap
            and maxima[2] <= max(orientation_cap, math.radians(0.2))
        )
        segment_reports.append(
            dict(
                index=index,
                duration_s=duration,
                duration_proposed=supplied is None,
                maximum_position_error_m=float(maxima[0]),
                maximum_aim_error_deg=math.degrees(maxima[1]),
                maximum_roll_error_deg=math.degrees(maxima[2]),
                position_tolerance_m=position_cap,
                orientation_tolerance_deg=math.degrees(orientation_cap),
                sampled_path_passed=passed,
            )
        )
        coefficients.append(coeff)
        knots.append(knots[-1] + duration)
        q = candidate.copy()
        if not passed:
            faults.append(
                dict(
                    segment=index,
                    reason="Sampled encoded path misses the requested pose corridor; no alternative motion substituted",
                )
            )
            break
    curve = JointCurve(tuple(knots), tuple(coefficients)) if coefficients else None
    if curve:
        try:
            limits.validate_plan(ArmProgramPlan(curve, timing.period_s), role, timing, mapping)
        except ValueError as error:
            faults.append(dict(reason=str(error)))
    complete = not faults and len(segment_reports) == len(request["segments"])
    document = dict(
        schema_version=1,
        kind="arm_pose_program",
        role=role,
        program=prepared["program"],
        pose_source=pose_source,
        initial_qpos=initial.tolist(),
        period_s=timing.period_s,
        curve=curve.to_dict() if curve else None,
        sources=sources,
        segments=segment_reports,
        faults=faults,
        sampled_path_passed=complete,
        collision_checked=False,
        physical_motion_verified=False,
        executable=False,
    )
    document["plan_id"] = digest(document)
    return prepared | dict(
        ok=complete,
        code="arm_rehearsal_ready" if complete else "arm_rehearsal_rejected",
        plan_id=document["plan_id"],
        pose_source=pose_source,
        segments=segment_reports,
        faults=faults,
        document=document,
        frames=frames,
        sampled_path_passed=complete,
        cart_changed=False,
        other_arm_changed=False,
        collision_checked=False,
        message="Simulated joint trajectory computed and screened, not physical execution. "
        "The exact path, loaded response, clearance and selected-person feed still require physical review."
        if complete
        else "Rehearsal rejected; nothing sent to hardware. This does not prove that every possible path is infeasible.",
    )
