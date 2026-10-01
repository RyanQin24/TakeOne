"""Authored moving-camera productions through ordinary Director/Studio APIs.

No model generation, device endpoint or hardware action is performed. Existing
scripts are never replaced. --install creates a new revision-scoped production.
"""

import argparse
import copy
import json
import math
import urllib.request
from pathlib import Path
from uuid import uuid4

from takeone.director.cinematic import wire_settings
from takeone.director.motion_contract import defaults as motion_defaults
from takeone.director.performers import PALETTE
from takeone.director.shot_design import defaults as design_defaults
from takeone.previs.channels import ramp
from takeone.previs.templates import BY_ID, catalog, defaults_for

ROOT = Path(__file__).resolve().parents[1]


def staged_object(object_id, asset_id, position, size, label=""):
    return dict(
        object_id=object_id, asset_id=asset_id, position_m=position, size_m=size, yaw_rad=0, label=label
    )


def shot_from_settings(shot_id, settings, duration, start, purpose, framing="medium"):
    entry = next(t for t in catalog()["templates"] if t["id"] == settings["template_id"])
    actor = "visitor" if settings["subject_motion"] != "none" else ""
    shot = dict(
        shot_id=shot_id,
        start_ms=round(start * 1000),
        end_ms=round((start + duration) * 1000),
        actor_id=actor,
        mark_id="workshop-origin",
        action=purpose,
        framing=framing,
        primitive="template",
        camera_intent=purpose,
        light_intent="Independent arm maintains the subject light; brightness and colour are manual.",
        edit_intent="Keep the actual source timing and finish the visible action before cutting.",
        lines=[],
        selected_line=0,
        transition="cut",
        performers=[],
        camera_target=dict(kind="actor" if actor else "object", target_id=actor or "workpiece"),
        tracking=dict(
            cart="planned",
            phone="planned",
            on_loss="stop_and_hold",
            reason="Scripted simultaneous choreography; no live tracking is claimed.",
        ),
        capture=dict(take_id="", in_s=0),
        audio_intent="Workshop room tone suggested; no recorded or generated sound in this simulation.",
        movement=dict(
            template_id=settings["template_id"],
            subject_motion=settings["subject_motion"],
            parameters=[
                dict(name=k, value=settings[k])
                for k in entry["parameters"] + ["focal_mm"]
                if not (k == "duration_s" and BY_ID[settings["template_id"]]["route"] != "hold")
            ],
            cinematography=wire_settings(settings),
        ),
    )
    shot["motion_requirements"] = motion_defaults()
    shot["design"] = design_defaults(shot) | dict(screen_targets=[], lens_policy="authored")
    shot["design"]["focus"] = dict(mode="deep", target="The actor and workshop depth cues.")
    return shot


def joint_settings():
    settings = copy.deepcopy(defaults_for("side_track"))
    settings.update(
        radius_m=2.3,
        distance_m=1.4,
        actor_distance_m=1.4,
        actor_heading_rad=0,
        speed_m_s=0.17,
        height_start_m=1.51,
        height_end_m=1.58,
        light_height_start_m=1.6,
        light_height_end_m=1.55,
        focal_mm=30,
    )
    settings["camera"] = dict(horizon="level", zoom="fixed", keyframes=[])
    settings["breath"] = dict(pre_hold_s=0.6, post_hold_s=1, entry_s=1.4, exit_s=1.4)
    settings["channels"] = dict(
        camera_height_m=ramp(1.51, 1.58, 0.15, 0.8),
        actor_position_m=ramp([0, 0, 0], [1.4, 0, 0], 0.06, 0.90),
        actor_heading_rad=ramp(0, 0.9, 0.82, 0.96),
        gaze_yaw_rad=ramp(0, 0.3, 0.82, 0.96),
    )
    return settings


def project():
    settings = joint_settings()
    purpose = "Walk from the entrance toward the workbench. The cart tracks alongside as the phone rises, then both settle."
    shot = shot_from_settings("joint-walk", settings, 11, 0, purpose)
    shot["motion_requirements"].update(
        priority="required",
        actor_travel_m=1.3,
        cart_travel_m=1.3,
        camera_travel_m=1.2,
        arm_translation_m=0.05,
        simultaneous_s=3.0,
    )
    shot["design"].update(
        opening="Visitor starts beside the entrance.",
        ending="Visitor reaches the bench end of the lane and stops; camera finishes its rise.",
        continuity="One uninterrupted source take. No moved world or hidden cut.",
    )
    scene = dict(
        scene_id="workshop",
        space_id="workshop",
        title="An invitation to begin",
        location="Authored level workshop, not a measured venue",
        atmosphere="interior_warm",
        location_notes="Keep the actor lane at Y=0 and the cart lane at Y=-2.3 clear. All coordinates are authored metres.",
        cast=[],
        objects=[
            staged_object("entrance", "doorway", [-1.1, 1.0, 1.4], [1.3, 0.15, 2.8], "WORKSHOP"),
            staged_object("bench", "table", [1.8, 0.8, 0.45], [1.5, 0.7, 0.9]),
            staged_object("workpiece", "product", [1.8, 0.8, 1.1], [0.2, 0.2, 0.4]),
            staged_object("shelf", "shelf", [0.2, 2.0, 1.0], [1.3, 0.3, 2.0]),
        ],
        shots=[shot],
    )
    shot["design"]["screen_targets"] = [
        dict(
            kind="actor",
            target_id="visitor",
            region="face",
            start_at=0,
            end_at=1,
            center_uv=[0.5, 0.24],
            tolerance_uv=[0.25, 0.22],
            height_range=[0.1, 0.45],
            min_visible_s=9,
            allow_occlusion=False,
            allow_crop=False,
            allowed_foreground_actor_ids=[],
        )
    ]
    title = "Moving Camera - actor, cart and phone arm together"
    context = dict(
        skill_id="cinematic",
        audience="A solo filmmaker",
        tone="A clear, purposeful workshop arrival",
        facts=[],
    )
    style = dict(
        visual_rules="Let performance and camera move together. Preserve static depth references.",
        palette="Rust outfit and warm neutral workshop",
        lighting="Independent subject-facing light arm; qualify real light separately.",
        wardrobe="The visitor keeps the rust outfit in every shot.",
        sound="Silent simulated preview; room tone is a later recording decision.",
        continuity_locks=["Actor travels along the marked lane.", "Set objects never move to fake parallax."],
    )
    return dict(
        brief=dict(title=title, objective=purpose, duration_ms=11000, aspect_ratio="16:9"),
        context=context,
        document=dict(
            title=title,
            logline=purpose,
            audience=context["audience"],
            tone=context["tone"],
            actors=[dict(actor_id="visitor", name="Visitor", appearance=PALETTE | dict(cloth="#b95f3e"))],
            marks=[
                dict(
                    mark_id="workshop-origin",
                    scene_id="workshop",
                    description="Actor opening floor mark",
                    position_m=[0, 0],
                    facing_rad=0,
                )
            ],
            questions=[],
            visual_style=style,
            scenes=[scene],
        ),
    )


def showcase_project():
    from takeone.previs.templates import compile_template

    sample = project()
    base_scene = copy.deepcopy(sample["document"]["scenes"][0])
    specs = [
        (
            "joint-walk",
            joint_settings(),
            "Walk into the workshop while the cart tracks and the phone rises.",
            dict(
                actor_travel_m=1.3,
                cart_travel_m=1.3,
                camera_travel_m=1.2,
                arm_translation_m=0.05,
                simultaneous_s=3,
            ),
        ),
        (
            "push-decision",
            copy.deepcopy(defaults_for("push_in")) | dict(radius_m=2.3, distance_m=0.75, focal_mm=30),
            "Approach a stationary visitor to emphasize the decision to begin.",
            dict(cart_travel_m=0.6, camera_travel_m=0.5, direction="approach", signed_progress_m=0.5),
        ),
        (
            "truck-reveal",
            copy.deepcopy(defaults_for("truck_right")) | dict(radius_m=2.5, distance_m=1.0, focal_mm=30),
            "Pass the foreground marker to reveal the visitor and workshop depth.",
            dict(cart_travel_m=0.8, camera_travel_m=0.6),
        ),
        (
            "arc-perspective",
            copy.deepcopy(defaults_for("arc_left"))
            | dict(radius_m=2.5, sweep_rad=math.radians(30), focal_mm=30),
            "Change perspective around the visitor while the camera gently rises.",
            dict(
                cart_travel_m=0.8,
                camera_travel_m=0.8,
                direction="orbit_ccw",
                orbit_rad=math.radians(25),
                arm_translation_m=0.05,
            ),
        ),
        (
            "arm-lens-rise",
            copy.deepcopy(defaults_for("boom_up"))
            | dict(radius_m=2.5, duration_s=10, height_start_m=1.51, height_end_m=1.58, focal_mm=30),
            "Keep the cart parked and move the optical centre upward; not a tilt-only effect.",
            dict(arm_translation_m=0.05, camera_travel_m=0.05),
        ),
        (
            "compound-discover",
            copy.deepcopy(defaults_for("arc_push"))
            | dict(radius_m=2.5, distance_m=0.65, sweep_rad=math.radians(25), focal_mm=30),
            "One uncut arc flows into an approaching change of perspective, then settles.",
            dict(cart_travel_m=1.0, camera_travel_m=1.0),
        ),
    ]
    scenes, marks, clock = [], [], 0.0
    for index, (name, settings, purpose, requirements) in enumerate(specs):
        if index:
            settings["subject_motion"] = "hold"
            settings["camera"] = dict(horizon="level", zoom="fixed", keyframes=[])
            settings["breath"] = dict(pre_hold_s=0.6, post_hold_s=1, entry_s=1.4, exit_s=1.4)
            settings.update(height_start_m=1.51, height_end_m=1.58 if index in (3, 4, 5) else 1.51)
            settings["channels"] = dict(
                camera_height_m=ramp(settings["height_start_m"], settings["height_end_m"], 0.15, 0.8)
            )
        # Duration follows the existing command predictor, not an equal edit slot.
        duration = compile_template(settings)["preview"]["orbit_duration_s"]
        shot = shot_from_settings(name, settings, duration, clock, purpose)
        shot["motion_requirements"].update(priority="required", **requirements)
        scene = copy.deepcopy(base_scene)
        scene["scene_id"] = name
        scene["title"] = purpose
        scene["shots"] = [shot]
        if index == 2:
            scene["objects"].append(
                staged_object("foreground-post", "wall", [-0.4, -0.9, 1.3], [0.20, 0.12, 0.8])
            )
            shot["design"]["visibility"] = "by_end"
        shot["design"]["continuity"] = (
            "Isolated capability take; reset the actor and rig between demonstrations. Static set landmarks do not move."
        )
        shot["mark_id"] = name + "-mark"
        marks.append(
            dict(
                mark_id=shot["mark_id"],
                scene_id=name,
                position_m=[0, 0],
                facing_rad=0,
                description="Independent demonstration opening mark",
            )
        )
        scenes.append(scene)
        clock += duration
    sample["document"].update(
        title="Moving Camera Showcase - six achieved robot takes", scenes=scenes, marks=marks
    )
    sample["brief"].update(
        title=sample["document"]["title"],
        duration_ms=round(clock * 1000),
        objective="Demonstrate script-driven actor/cart/phone overlap, approach, reveal, arc, arm translation and an uncut compound move.",
    )
    return sample


def story_project():
    from takeone.previs.templates import compile_template

    sample = project()
    scene = sample["document"]["scenes"][0]
    # The same arrival take must survive into the story, not only the test gallery.
    scene["shots"][0]["design"]["beats"] = [
        dict(
            start_s=a,
            end_s=b,
            actor_id="visitor",
            action=text,
            motivation="Arrive ready to work",
            emotion="Quiet anticipation",
            eyeline="Along the workbench lane",
            delivery="No dialogue",
        )
        for a, b, text in (
            (0, 0.66, "Wait at the entrance."),
            (0.66, 9.9, "Walk to the workbench as the camera tracks alongside."),
            (9.9, 11, "Stop at the destination and look toward the workpiece."),
        )
    ]
    clock = 11.0
    settings = copy.deepcopy(defaults_for("push_in")) | dict(
        radius_m=2.3, distance_m=0.65, focal_mm=38, height_start_m=1.51, height_end_m=1.51
    )
    settings["camera"] = dict(horizon="level", zoom="fixed", keyframes=[])
    settings["breath"] = dict(pre_hold_s=0.6, post_hold_s=1, entry_s=1.4, exit_s=1.4)
    duration = compile_template(settings)["preview"]["orbit_duration_s"]
    shot = shot_from_settings(
        "decision-push",
        settings,
        duration,
        clock,
        "The visitor turns toward the waiting workpiece while the camera moves closer.",
    )
    shot["motion_requirements"].update(
        priority="required",
        cart_travel_m=0.5,
        camera_travel_m=0.5,
        direction="approach",
        signed_progress_m=0.5,
    )
    shot["mark_id"] = "arrival-end"
    shot["movement"]["cinematography"]["channels"]["actor_heading_rad"] = ramp(0.9, math.pi / 2, 0.05, 0.6)
    shot["movement"]["cinematography"]["channels"]["gaze_yaw_rad"] = ramp(0.3, -0.414, 0.05, 0.6)
    shot["design"]["ending"] = "Visitor faces the workpiece; hold that decision before the cut."
    scene["shots"].append(shot)
    clock += duration
    settings = copy.deepcopy(defaults_for("boom_up")) | dict(
        radius_m=2.3, duration_s=8, focal_mm=30, height_start_m=1.51, height_end_m=1.58
    )
    settings["camera"] = dict(horizon="level", zoom="fixed", keyframes=[])
    shot = shot_from_settings(
        "begin-reach",
        settings,
        8,
        clock,
        "The visitor reaches a stationary workpiece and holds contact; no grasp or transfer is simulated.",
    )
    shot["mark_id"] = "arrival-end"
    shot["motion_requirements"].update(priority="required", arm_translation_m=0.05, camera_travel_m=0.05)
    shot["movement"]["cinematography"]["channels"]["actor_heading_rad"] = ramp(math.pi / 2, math.pi / 2)
    shot["performers"] = [
        dict(
            actor_id="visitor",
            body_heading_rad=[],
            look_at=[
                dict(at=t, ease="smooth", kind="object", target_id="workpiece", point_m=[0, 0, 0])
                for t in (0, 1)
            ],
            gestures=[
                dict(
                    at=t,
                    ease="smooth",
                    kind="point",
                    target_id="",
                    point_m=[1.62, 0.4, 1.12],
                    name="reach",
                    weight=w,
                )
                for t, w in ((0, 0), (0.2, 0), (0.75, 1), (1, 1))
            ],
        )
    ]
    shot["design"].update(
        ending="Hand meets the fixed contact point; hold before the cut.",
        continuity="Same visitor, outfit, workshop and fixed workpiece. No ownership transfer.",
    )
    scene["shots"].append(shot)
    clock += 8
    # Move the prop/bench once in this authored story, not dynamically during the shot.
    for obj in scene["objects"]:
        if obj["object_id"] == "bench":
            obj["position_m"] = [1.8, 0.75, 0.45]
        if obj["object_id"] == "workpiece":
            obj["position_m"] = [1.62, 0.5, 1.12]
    sample["document"]["marks"].append(
        dict(
            mark_id="arrival-end",
            scene_id="workshop",
            position_m=[1.4, 0],
            facing_rad=0,
            description="Visitor destination; matches the arrival take's ending",
        )
    )
    sample["document"].update(
        title="Begin - a moving performance filmed by a moving robot",
        logline="A visitor arrives, considers the workpiece, then reaches it to begin.",
    )
    sample["brief"].update(
        title=sample["document"]["title"],
        objective=sample["document"]["logline"],
        duration_ms=round(clock * 1000),
    )
    return sample


def install(sample, destination, base_url):
    destination.mkdir(parents=True, exist_ok=False)

    def request(path, body=None):
        raw = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base_url + path, raw, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as response:
            value = json.load(response)
        if value.get("ok") is False:
            raise ValueError(str(value.get("message", value)))
        return value

    def envelope():
        runtime = request("/api/director/runtime")
        return dict(
            schema_version=1,
            operation_id=str(uuid4()),
            runtime_epoch=runtime["runtime_epoch"],
            expires_monotonic_ns=str(int(runtime["now_monotonic_ns"]) + int(runtime["command_ttl_ns"])),
        )

    (destination / "authored.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    session = request("/api/director/sessions", envelope() | dict(brief=sample["brief"]))["session"]
    scope = dict(
        session_id=session["session_id"],
        expected_revision=session["revision"],
        cancellation_generation=session["cancellation_generation"],
        take_id=session["take_id"],
        plan_id=None,
    )
    request(
        "/api/director/creative",
        envelope()
        | dict(scope=scope, action="start_script", payload={k: sample[k] for k in ("document", "context")}),
    )
    detail = request("/api/director/sessions/" + session["session_id"])
    ref = session["session_id"] + "/" + detail["creative"]["digest"]
    manifest = request("/api/director/studio/" + ref)
    program = request("/api/previs/sequence", manifest)
    for name, value in (("detail", detail), ("manifest", manifest), ("program", program)):
        (destination / (name + ".json")).write_text(json.dumps(value, indent=2), encoding="utf-8")
    result = dict(
        reference=ref,
        url=base_url + "/?script=" + ref,
        provenance="authored_not_model_generated",
        document_digest=program["document_digest"],
        needs_revision=program["needs_revision_shot_ids"],
    )
    (destination / "installed.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--kind", choices=("joint", "showcase", "story"), default="joint")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a local unprivileged port.")
    sample = {"joint": project, "showcase": showcase_project, "story": story_project}[args.kind]()
    if args.install:
        install(sample, args.output, f"http://127.0.0.1:{args.port}")
    else:
        args.output.write_text(json.dumps(sample, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
