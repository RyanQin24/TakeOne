"""Evidence from rendered pinhole geometry, never a verdict on recorded footage."""

import math

import numpy as np
from scipy.spatial.transform import Rotation

from takeone.director.shot_design import FRAMINGS

from .camera import MAX_FOCAL_MM, MIN_FOCAL_MM, PROFILE
from .motion_review import optical_height, review_motion

# The part of a standing actor that a shot promises to keep visible.
REGIONS = {
    "extreme_wide": (0, 1),
    "wide": (0, 1),
    "full": (0, 1),
    # Include the proxy's knee (~0.24 stature) and mid-thigh (~0.35),
    # with a little room below the landmark rather than cutting through it.
    "medium_full": (0.23, 1),
    "cowboy": (0.34, 1),
    "medium": (0.52, 1),
    "medium_close_up": (0.67, 1),
    "close_up": (0.84, 1),
    "extreme_close_up": (0.90, 0.95),
}


def lens_cue(focal):
    presets = {
        13: "Ultra Wide",
        24: "Main",
        48: "Main sensor crop",
        100: "Telephoto",
        200: "Telephoto sensor crop",
    }
    exact = next((name for mm, name in presets.items() if abs(mm - focal) < 0.05), None)
    return dict(
        equivalent_mm=round(focal, 2),
        choice=exact or "Equivalent framing / digital crop; match in the phone app",
        control="manual_phone_app",
        physical_lens=exact in ("Ultra Wide", "Main", "Telephoto"),
    )


def subject_points(shot, settings, scene, mark, frame):
    """Shot-local points. Supporting cast uses the same placement as the renderer."""
    target = shot.get("camera_target", {})
    if target.get("kind") == "object":
        obj = next(o for o in scene["objects"] if o["object_id"] == target["target_id"])
        origin = mark.get("position_m", [0, 0])
        centre = np.array(
            [obj["position_m"][0] - origin[0], obj["position_m"][1] - origin[1], obj["position_m"][2]]
        )
        yaw = obj["yaw_rad"]
        rotation = np.array(
            [[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]]
        )
        return np.array(
            [
                centre + rotation @ (np.array(obj["size_m"]) * [x, y, z] / 2)
                for x in (-1, 1)
                for y in (-1, 1)
                for z in (-1, 1)
            ]
        )
    h = settings["subject_height_m"]
    low, high = REGIONS[shot["framing"]]
    width = h * (
        0.025 if shot["framing"] == "extreme_close_up" else 0.07 if shot["framing"] == "close_up" else 0.16
    )
    positions = [frame["actor"]["position_m"]]
    design = shot.get("design") or {}
    featured = set(design.get("featured_actor_ids", [])) - {shot.get("actor_id")}
    for member in scene.get("cast", []):
        if member["actor_id"] in featured:
            base = frame["actor"]["position_m"] if member["motion"] == "with_lead" else [0, 0, 0]
            positions.append([a + b for a, b in zip(base, member["offset_m"])])
    return np.array(
        [
            [p[0] + x, p[1] + y, p[2] + h * z]
            for p in positions
            for x in (-width, width)
            for y in (-width / 2, width / 2)
            for z in (low, high)
        ]
    )


def projection(frame, points):
    camera = frame.get("camera_view", frame["camera"])
    local = (points - np.asarray(camera["pos"])) @ Rotation.from_quat(camera["quat"]).as_matrix()
    depths = local[:, 2]
    safe = np.maximum(depths, 1e-8)
    # Signed screen coordinates: left/top=-1, right/bottom=+1.
    xy = local[:, :2] / safe[:, None] * frame["focal_mm"] / np.array([18.0, 10.125])
    return xy, depths


def fit_opening(shot, settings, scene, mark):
    """An explicitly requested lens suggestion from solved FK, without moving marks."""
    from .cache import compile_preview

    preview = compile_preview(settings)
    first = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8)
    if shot.get("design", {}).get("visibility") == "by_end":
        first = preview["frames"][-1]
    points = subject_points(shot, settings, scene, mark, first)
    xy, depths = projection(first, points)
    if min(depths) <= 0:
        return dict(
            applied=False, reason="The requested subject is behind the solved camera; revise placement."
        )
    target = first.get("camera_target_m", first["face"])
    _, depth = projection(first, np.array([target]))
    if shot.get("camera_target", {}).get("kind") == "object":
        desired_height = max(np.ptp(points[:, 2]) * 1.2, 0.05)
    else:
        desired_height = FRAMINGS[shot["framing"]][2] * settings["subject_height_m"]
    nominal = float(depth[0]) * 20.25 / desired_height
    fit = first["focal_mm"] * 0.92 / max(float(np.max(np.abs(xy))), 1e-8)
    requested = min(nominal, fit)
    selected = round(max(MIN_FOCAL_MM, min(MAX_FOCAL_MM, requested)), 2)
    before = settings["focal_mm"]
    settings["focal_mm"] = selected
    settings["camera"] = dict(horizon=settings["camera"]["horizon"], zoom="fixed", keyframes=[])
    return dict(
        applied=True,
        before_mm=before,
        selected_mm=selected,
        required_mm=round(requested, 2),
        clamped=bool(requested < MIN_FOCAL_MM or requested > MAX_FOCAL_MM),
        reference="ending" if shot.get("design", {}).get("visibility") == "by_end" else "opening",
        reason="Fit the requested region at its declared reference frame using the solved camera pose. "
        "The full take is checked again for cropping.",
    )


def review(shot, settings, scene, mark, preview):
    start = preview["orbit_start_s"]
    frames = [f for f in preview["frames"] if f["time_s"] >= start - 1e-8]
    design = shot.get("design") or {}
    visibility = design.get("visibility", "throughout")
    coverage_frames = frames[-1:] if visibility == "by_end" else frames
    motion = review_motion(shot, settings, preview)
    issues = list(motion["issues"]) if motion else []
    if motion and (not frames or any(optical_height(f) is None for f in frames)):
        return dict(
            source="simulated_geometry", status="needs_revision", motion=motion,
            samples_examined=0, coverage_samples_examined=0,
            timebase="seconds of this shot's filmed source, excluding setup", issues=issues,
            lens_start=None, lens_end=None, phone_profile=PROFILE["name"], capture_aspect="16:9",
            camera_height_range_m=None,
            unchecked=["Camera geometry: achieved raw optical samples are incomplete",
                       "Actual recorded footage and hardware qualification"],
        )
    cropped, behind = [], []
    minimum_margin = 1.0
    for frame in coverage_frames:
        points = subject_points(shot, settings, scene, mark, frame)
        xy, depths = projection(frame, points)
        margin = 1 - float(np.max(np.abs(xy)))
        minimum_margin = min(minimum_margin, margin)
        time = round(frame["time_s"] - start, 4)
        if min(depths) <= 0:
            behind.append(time)
        elif margin < -0.03:
            cropped.append(time)
    if cropped or behind:
        times = behind or cropped
        issues.append(
            dict(
                code="subject_behind_camera" if behind else "promised_region_cropped",
                severity="revision" if design and visibility != "intentional_partial" else "manual",
                time_range_s=[times[0], times[-1]],
                observation="The promised subject region leaves the camera view at one or more filmed samples.",
                evidence=dict(
                    affected_samples=len(times),
                    examined_samples=len(coverage_frames),
                    visibility=visibility if design else "unspecified_legacy",
                    minimum_screen_margin=round(minimum_margin, 4),
                ),
                recommendation="Widen the lens, move the camera back, or revise the aim and blocking. "
                "For an intentional partial view, change the shot size or featured people.",
            )
        )
    angle = design.get("angle")
    from .templates import BY_ID

    if (
        shot.get("tracking", {}).get("phone") == "follow_head"
        and BY_ID[settings["template_id"]]["aim"] == "locked"
    ):
        issues.append(
            dict(
                code="locked_follow_conflict",
                severity="revision",
                time_range_s=[0, preview["orbit_duration_s"]],
                observation="Head-follow is requested but this template locks the camera's opening aim.",
                evidence=dict(template_id=settings["template_id"], requested_controller="follow_head"),
                recommendation="Choose a subject-aiming movement or keep authored locked aim for this shot.",
            )
        )
    if design and shot.get("camera_target", {}).get("kind", "actor") == "actor":
        if angle in ("low", "high", "eye_level"):
            heights = [f["camera"]["pos"][2] - f["face"][2] for f in frames]
            disagrees = (
                (angle == "low" and min(heights) > -0.10)
                or (angle == "high" and max(heights) < 0.10)
                or (angle == "eye_level" and min(abs(v) for v in heights) > 0.25)
            )
            if disagrees:
                issues.append(
                    dict(
                        code="angle_intent",
                        severity="revision",
                        time_range_s=[0, preview["orbit_duration_s"]],
                        observation="The achieved camera height does not establish the requested "
                        + angle.replace("_", " ")
                        + " viewpoint.",
                        evidence=dict(
                            camera_minus_face_height_m=[round(min(heights), 3), round(max(heights), 3)]
                        ),
                        recommendation="Adjust camera height within reach, or revise the angle description after inspecting the phone view.",
                    )
                )
    if angle in ("aerial", "overhead"):
        issues.append(
            dict(
                code="equipment_required",
                severity="manual",
                time_range_s=[0, preview["orbit_duration_s"]],
                observation=f"{angle.capitalize()} direction needs a suitable measured camera position; "
                "the current floor cart and arm cannot be assumed to provide it.",
                evidence=dict(requested_angle=angle),
                recommendation="Use separate equipment or explicitly redesign the viewpoint.",
            )
        )
    if design.get("composition") in ("over_shoulder", "pov"):
        issues.append(
            dict(
                code="perspective_review",
                severity="manual",
                time_range_s=[0, preview["orbit_duration_s"]],
                observation="Subject coverage alone does not establish the requested viewpoint.",
                evidence=dict(composition=design["composition"]),
                recommendation="Inspect the phone view and place the camera at the stated eyeline or behind the foreground shoulder.",
            )
        )
    if design.get("focus", {}).get("mode") in ("rack", "selective"):
        issues.append(
            dict(
                code="focus_manual",
                severity="manual",
                time_range_s=[0, preview["orbit_duration_s"]],
                observation="Focus and depth of field are directing instructions; this preview uses a pinhole camera.",
                evidence=dict(focus=design["focus"]),
                recommendation="Rehearse the focus change in the recording app and check the actual footage.",
            )
        )
    elapsed = (shot["end_ms"] - shot["start_ms"]) / 1000
    for beat in design.get("beats", []):
        if beat["end_s"] > preview["orbit_duration_s"] + 0.04:
            issues.append(
                dict(
                    code="performance_coverage",
                    severity="revision",
                    time_range_s=[beat["start_s"], beat["end_s"]],
                    observation="This performance beat extends beyond the available filmed movement.",
                    evidence=dict(filmed_s=preview["orbit_duration_s"], edit_s=elapsed),
                    recommendation="Extend the take or adjust this beat; a held preview frame supplies no new performance.",
                )
            )
    return dict(
        source="simulated_geometry",
        status="needs_revision"
        if any(i["severity"] == "revision" for i in issues) or (motion and motion["status"] == "unverified")
        else "reviewable",
        motion=motion,
        samples_examined=len(frames),
        coverage_samples_examined=len(coverage_frames),
        timebase="seconds of this shot's filmed source, excluding setup",
        issues=issues,
        lens_start=lens_cue(frames[0]["focal_mm"]),
        lens_end=lens_cue(frames[-1]["focal_mm"]),
        phone_profile=PROFILE["name"],
        capture_aspect="16:9",
        camera_height_range_m=[
            round(min(f["camera"]["pos"][2] for f in frames), 3),
            round(max(f["camera"]["pos"][2] for f in frames), 3),
        ],
        unchecked=[
            "Actual focus / exposure / stabilization crop",
            "Facial performance and recorded sound",
            "Measured location, occlusion and full rig clearance",
            "Live tracking and physical repeatability",
        ],
    )
