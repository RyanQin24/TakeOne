"""Author and review a two-person nighttime rehearsal. No device or model calls."""

import copy
import json
import math
import sys
import urllib.request
import uuid

from takeone.director.cinematic import wire_settings
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import digest, validate_plan
from takeone.director.skills import sample_project
from takeone.director.studio import rehearsal_manifest
from takeone.previs.channels import ramp
from takeone.previs.sequence import build_program
from takeone.previs.templates import defaults_for

BASE = "http://127.0.0.1:8766"
sample = sample_project("cinematic")
doc = copy.deepcopy(sample["document"])
seed = copy.deepcopy(doc["scenes"][0]["shots"][0])
context = dict(
    skill_id="cinematic",
    audience="Tonight’s Waterloo demo audience",
    tone="Nighttime cinematic energy, playful collaboration",
    facts=[],
)
brief = dict(
    title="After Dark — Waterloo / 10-shot two-person demo",
    objective="Two collaborators make a one-minute film outside at Waterloo at night. Ten unique shots; both people visible; a front-facing walking conversation; low-angle rising phone-arm tilt; custom simultaneous cart and arm choreography. Requested cart cruise at least 0.33 m/s, within existing policy. Nighttime background with architecture and practical lights, assumed not measured. No claim of hardware or live-sync qualification.",
    duration_ms=60000,
    aspect_ratio="16:9",
)
doc.update(
    title="After Dark — a moving conversation",
    audience=context["audience"],
    tone=context["tone"],
    logline="Alex calls it a phone on wheels. Maya changes the brief, and the camera answers with a different point of view.",
    questions=[
        "Confirm a level, lit outdoor route with no pedestrians or obstacles before physical filming.",
        "All architecture, lights and placements are assumed visualization, not measured Waterloo geometry.",
        "Camera controls and sync need a fresh live-phone check; simulation is not a qualified robot run.",
        "Platform height is user-reported as about 0.6 m; confirm load-bearing surface, edge clearance and safe access. Cart remains on the lower level.",
    ],
)
doc["actors"] = [
    dict(
        actor_id="actor-a",
        name="Alex",
        appearance=dict(cloth="#245a83", pants="#253040", skin="#cfa783", hair="#30271f", shoe="#eeeeee"),
    ),
    dict(
        actor_id="actor-b",
        name="Maya",
        appearance=dict(cloth="#b46737", pants="#292d35", skin="#cfa783", hair="#30271f", shoe="#eeeeee"),
    ),
]
doc["visual_style"].update(
    palette="Deep blue night, warm practical lights, blue and amber wardrobe.",
    wardrobe="Alex in blue, Maya in amber; maintain through all edits.",
    lighting="Night exterior with motivated warm practical lamps and soft face fill. Preview is illustrative; check actual exposure.",
    sound="Close dialogue, footsteps and evening ambience; no claimed recorded sound.",
    visual_rules="Contrast empty-place inserts, tilted reactions, arm-only reveals and frontal dialogue. Blue/amber identities persist. Let one character challenge the other; the camera answers through a visible change.",
    continuity_locks=["Same cast and wardrobe; independent takes reset outside the 60-second edit."],
)
doc["marks"] = []
doc["scenes"] = []
rows = [
    (
        "tilt_up",
        "The campus wakes — no actors",
        "",
        "Empty courtyard: tilt from the warm pool of light toward the facade. Let the architecture introduce the night.",
        dict(
            radius_m=4.5,
            duration_s=5.4,
            angle_rad=0.20,
            height_start_m=1.40,
            height_end_m=1.40,
            rise_start=0.05,
            rise_end=0.95,
            focal_mm=24,
        ),
    ),
    (
        "track_lead",
        "Walk toward the audience",
        "Alex: It’s just a robot with a phone. How cinematic can it be?",
        "Walk side by side toward the leading camera, speaking to the lens.",
        dict(radius_m=4.5, distance_m=3.2, actor_distance_m=3.2, actor_heading_rad=0, focal_mm=35),
    ),
    (
        "roll_left",
        "Maya tilts the argument",
        "Maya: Maybe you’re looking at it from the wrong angle.",
        "Maya holds her ground, looks at Alex off camera, then gives the lens a dry smile as the horizon rolls.",
        dict(
            radius_m=3.8,
            duration_s=5.4,
            angle_rad=0.16,
            bearing_rad=math.pi / 2,
            height_start_m=1.40,
            height_end_m=1.40,
            focal_mm=48,
        ),
    ),
    (
        "boom_up",
        "From below — platform hero reveal",
        "Alex: Down there, we’re just silhouettes. Now look up.",
        "Both stand on the 0.6 m platform, away from the edge. Hold still as the lower-level cart holds and the phone arm rises, revealing faces from below.",
        dict(
            radius_m=4.5,
            duration_s=7.4,
            bearing_rad=math.pi / 2,
            height_start_m=1.2,
            height_end_m=1.55,
            rise_start=0.05,
            rise_end=0.95,
            focal_mm=24,
        ),
    ),
    (
        "tilt_down",
        "A pool of light — no actors",
        "",
        "A silent insert: tilt down the practical lamp to its pool of light. No performers in this setup.",
        dict(
            radius_m=4.5, duration_s=4.4, angle_rad=0.18, height_start_m=1.40, height_end_m=1.40, focal_mm=48
        ),
    ),
    (
        "pan_left",
        "From intimate reply to shared space",
        "Maya: Better. But can it change the way a moment feels?",
        "Maya turns from Alex to the lens. The cart holds while the phone pans; start tight at 48 mm, then widen to 24 mm to reveal her listener and the night.",
        dict(
            radius_m=4.5,
            duration_s=5.4,
            angle_rad=0.10,
            bearing_rad=math.pi / 2,
            height_start_m=1.40,
            height_end_m=1.40,
            focal_mm=48,
        ),
    ),
    (
        "dolly_zoom_out",
        "The world pulls away",
        "Alex: Keep your eyes on me. Let the whole world change behind us.",
        "Alex holds still while the camera retreats and the lens tightens; Maya holds a silent reaction beside him.",
        dict(
            radius_m=4.5,
            distance_m=2.8,
            bearing_rad=math.pi / 2,
            height_start_m=1.45,
            height_end_m=1.45,
            focal_mm=24,
        ),
    ),
    (
        "truck_right",
        "Architecture in parallax — no actors",
        "",
        "An empty-place cutaway: glide across the lit facade; phone rises while the light lowers independently.",
        dict(
            radius_m=4.5,
            distance_m=2.0,
            height_start_m=1.40,
            height_end_m=1.55,
            rise_start=0.05,
            rise_end=0.95,
            light_height_start_m=1.60,
            light_height_end_m=1.45,
            focal_mm=24,
        ),
    ),
    (
        "track_lead",
        "Maya changes the brief",
        "Maya: Okay. Now follow us. Keep both faces. And don’t lose the light.",
        "Both walk toward the camera; Maya leads the line while Alex looks over, then back to the lens.",
        dict(
            radius_m=4.5,
            distance_m=3.2,
            actor_distance_m=3.2,
            actor_heading_rad=0,
            height_start_m=1.4,
            height_end_m=1.55,
            light_height_start_m=1.65,
            light_height_end_m=1.4,
            focal_mm=24,
        ),
    ),
    (
        "pull_out",
        "Leave room for the next idea",
        "Alex: Your story. Your directions. Maya: One more take?",
        "Face the lens together and hold the invitation as the courtyard is revealed.",
        dict(radius_m=3.8, distance_m=2.8, height_start_m=1.45, height_end_m=1.55, focal_mm=24),
    ),
]
durations = [5, 8, 5, 7, 4, 5, 7, 5, 8, 6]
clock_s = 0
for i, (template, title, line, action, overrides) in enumerate(rows):
    si = [0, 1, 1, 2, 3, 4, 4, 5, 6, 6][i]
    duration = durations[i]
    empty = i in (0, 4, 7)
    speaker = "actor-b" if i in (2, 5, 8) else "actor-a"
    partner = "actor-a" if speaker == "actor-b" else "actor-b"
    scene_id = f"night-{si + 1}"
    mark_id = f"mark-{i + 1}"
    if i in (0, 1, 3, 4, 5, 7, 8):
        scene = copy.deepcopy(sample["document"]["scenes"][0])
        scene.update(
            scene_id=scene_id,
            space_id=scene_id,
            title=title,
            location="Assumed Waterloo outdoor courtyard at night",
            atmosphere="exterior_night",
            location_notes="Proposed open level courtyard. Architecture and practical lamps are visualization only. Allow separate resets between takes; verify real route clearance.",
            cast=[]
            if empty
            else [
                dict(actor_id=actor_id, offset_m=offset, facing_rad=0, motion="with_lead")
                for actor_id, offset in (("actor-a", [0.75, -1.0, 0]), ("actor-b", [-0.75, 1.0, 0]))
            ],
            shots=[],
            objects=[
                dict(
                    object_id="backdrop",
                    asset_id="facade",
                    label="Warm campus facade — assumed",
                    position_m=[-10, 0, 2.5],
                    size_m=[18, 0.3, 5],
                    yaw_rad=math.pi / 2,
                    availability="proposed",
                    production_role="Night background depth",
                ),
                dict(
                    object_id="lamp-left",
                    asset_id="practical_light",
                    label="Warm pool of light",
                    position_m=[-6, -4, 1.1],
                    size_m=[0.4, 0.4, 2.2],
                    yaw_rad=0,
                    availability="proposed",
                    production_role="Motivated evening practical",
                ),
                dict(
                    object_id="lamp-right",
                    asset_id="practical_light",
                    label="Warm rim practical",
                    position_m=[-6, 5, 1.1],
                    size_m=[0.4, 0.4, 2.2],
                    yaw_rad=0,
                    availability="proposed",
                    production_role="Separate the pair from the background",
                ),
                dict(
                    object_id="tree-left",
                    asset_id="tree",
                    label="Courtyard tree",
                    position_m=[-8, -6, 2],
                    size_m=[2, 2, 4],
                    yaw_rad=0,
                    availability="proposed",
                    production_role="Night silhouette",
                ),
                dict(
                    object_id="tree-right",
                    asset_id="tree",
                    label="Courtyard tree",
                    position_m=[-8, 6, 2],
                    size_m=[2, 2, 4],
                    yaw_rad=0,
                    availability="proposed",
                    production_role="Background rhythm",
                ),
            ],
        )
        doc["scenes"].append(scene)
    if i == 3:
        scene["objects"].append(
            dict(
                object_id="platform",
                asset_id="plinth",
                label="0.6 m platform — verify on site",
                position_m=[0, 0, 0.3],
                size_m=[3.5, 3.5, 0.6],
                yaw_rad=0,
                availability="unconfirmed",
                production_role="Elevated standing surface",
            )
        )
        scene["location_notes"] += (
            " Actors stand on a user-reported 0.6 m platform; size is assumed. Cart stays on lower level. Verify safe platform access and edge clearance."
        )
    doc["marks"].append(
        dict(
            mark_id=mark_id,
            scene_id=scene_id,
            description="Assumed origin for this independent take; reset off camera.",
            position_m=[-0.75, 1.0] if speaker == "actor-b" else [0, 0],
            facing_rad=0,
        )
    )
    walk = template in ("track_lead", "side_track", "track_follow")
    params = dict(**overrides)
    if "duration_s" not in params:
        params["speed_m_s"] = 0.40
    if i == 9:
        params["distance_m"] = 2.4
        params["bearing_rad"] = math.pi / 2
    if params.get("sweep_rad") == 0.64:
        params["sweep_rad"] = 0.5
    settings = (
        defaults_for(template) | params | dict(subject_motion="none" if empty else "walk" if walk else "hold")
    )
    if i == 2:
        settings["camera"]["horizon"] = "phone"
    if i == 3:
        settings["channels"].update(
            actor_position_m=ramp([0, 0, 0.6], [0, 0, 0.6]),
            camera_target_m=ramp([0, 0, 0.8], [0, 0, 1.8], 0.1, 0.85),
            light_height_m=ramp(1.65, 1.35, 0.45, 0.95),
            light_target_m=ramp([0, 0, 2.2], [0, 0, 2.2]),
        )
    if i == 5:
        settings["camera"].update(
            zoom="keyframes",
            keyframes=[
                dict(at=0, focal_mm=48, ease="hold"),
                dict(at=0.35, focal_mm=48, ease="smooth"),
                dict(at=1, focal_mm=24, ease="smooth"),
            ],
        )
    shot = copy.deepcopy(seed)
    shot.update(
        shot_id=f"night-shot-{i + 1:02}",
        start_ms=clock_s * 1000,
        end_ms=(clock_s + duration) * 1000,
        actor_id="" if empty else speaker,
        mark_id=mark_id,
        action=action,
        framing="wide" if i in (3, 5) else "medium" if i == 2 else "full",
        primitive="template",
        selected_line=0,
        audio_intent="Night ambience and footsteps off screen; no dialogue."
        if empty
        else "Close conversational dialogue and exterior night ambience.",
        camera_intent=title
        + ". Encoded route at 0.40 m/s requested cruise; inspect achieved speed and framing.",
        light_intent="Motivated practical lamps and soft face fill; confirm actual exposure.",
        edit_intent="Cut after the line on the acting beat; resets excluded.",
        lines=[dict(text=line, tone="Dry, playful conversation", fact_ids=[])] if line else [],
        movement=dict(
            template_id=template,
            subject_motion=settings["subject_motion"],
            parameters=[dict(name=k, value=v) for k, v in params.items()],
            cinematography=wire_settings(settings),
        ),
        transition="cut",
        camera_target=dict(kind="object", target_id="lamp-left" if i == 4 else "backdrop")
        if empty
        else dict(kind="actor", target_id=speaker),
        capture=dict(take_id=f"night-take-{i + 1}", in_s=0),
        performers=[],
        tracking=dict(
            cart="planned",
            phone="planned",
            on_loss="stop_and_hold",
            reason="Scripted two-person rehearsal; no claim of live person tracking.",
        ),
    )
    shot["design"].update(
        purpose=title,
        attention="Architecture and motivated pools of light, no performers."
        if empty
        else "The speaking face and the listener’s response.",
        opening=action,
        ending="Let the line land before cutting.",
        composition="environment" if empty else "single" if i in (2, 5) else "two_shot",
        featured_actor_ids=[] if empty else [speaker] if i in (2, 5) else [speaker, partner],
        angle="low" if i == 3 else "dutch" if i == 2 else "eye_level",
        visibility="by_end" if i == 3 else "intentional_partial" if empty or i in (5, 6) else "throughout",
        lens_policy="authored",
        focus=dict(mode="deep", target="Facade and practical lamp" if empty else "Speaking face"),
        continuity="Same two collaborators; independent off-camera reset between takes.",
        practical_setup="Keep the full route clear of actors, lamps and pedestrians.",
        beats=[
            dict(
                start_s=0,
                end_s=duration,
                actor_id=speaker,
                action=action,
                motivation=title,
                emotion="Curious and confident",
                eyeline="Lens for front-facing dialogue; travel direction while following.",
                delivery="Natural conversational timing.",
            )
        ],
    )
    if empty:
        shot["design"]["beats"][0].update(
            actor_id="", emotion="", eyeline="", delivery="Silent environmental insert."
        )
    elif i == 9:
        shot["design"]["beats"][0]["end_s"] = 3.5
        shot["design"]["beats"].append(
            dict(
                start_s=3.5,
                end_s=duration,
                actor_id="actor-b",
                action="Look to Alex, then back to the lens: One more take?",
                motivation="Turn the ending into an invitation.",
                emotion="Amused",
                eyeline="Alex, then lens",
                delivery="Leave a small beat before the reply.",
            )
        )
    if i in (2, 5):
        shot["performers"] = [
            dict(
                actor_id=speaker,
                body_heading_rad=[],
                gestures=[],
                look_at=[
                    dict(
                        at=at,
                        ease="smooth",
                        kind=kind,
                        target_id=partner if kind == "actor" else "",
                        point_m=[0, 0, 0],
                    )
                    for at, kind in ((0, "actor"), (0.3, "actor"), (0.7, "forward"), (1, "forward"))
                ],
            )
        ]
    # Minimum creative movement targets, not exact full-route distance promises.
    shot["motion_requirements"].update(
        priority="required",
        actor_travel_m=1.5 if walk else 0,
        cart_travel_m=0 if "duration_s" in params else 1.5,
        camera_travel_m=0 if "duration_s" in params else 1.0,
        arm_translation_m=0,
        arm_rotation_rad=0.05 if "duration_s" in params else 0,
        light_translation_m=0,
        light_rotation_rad=0,
        simultaneous_s=0,
        direction="any",
        signed_progress_m=0,
        orbit_rad=0,
    )
    scene["shots"].append(shot)
    clock_s += duration


def dress_reverse_angles(document):
    """A courtyard needs depth on both sides of the actor, not behind one camera."""
    for staged_scene in document["scenes"]:
        if not staged_scene["cast"]:
            continue
        existing = {obj["object_id"] for obj in staged_scene["objects"]}
        for source_id, target_id, position in (
            ("backdrop", "reverse-backdrop", [10, 0, 2.5]),
            ("lamp-left", "reverse-lamp-left", [6, -2.5, 1.1]),
            ("lamp-right", "reverse-lamp-right", [6, 2.5, 1.1]),
        ):
            if target_id in existing:
                continue
            source = next(obj for obj in staged_scene["objects"] if obj["object_id"] == source_id)
            staged_scene["objects"].append(
                copy.deepcopy(source)
                | dict(object_id=target_id, position_m=position, label="Reverse-angle " + source["label"])
            )


dress_reverse_angles(doc)
validate_plan(doc, ProductionBrief.parse(brief), context)
detail = dict(
    session=dict(session_id="night-candidate", revision=0, brief=brief),
    creative=dict(document=doc, digest=digest(doc), context=context),
)
program = build_program(rehearsal_manifest(detail, digest(doc)))
print(
    json.dumps(
        dict(
            blocked=program["blocked_shot_ids"],
            needs_revision=program["needs_revision_shot_ids"],
            shots=[
                dict(
                    id=s["shot_id"],
                    source_s=s.get("filming_s"),
                    diagnostics=s["diagnostics"],
                    issues=s.get("shot_review", {}).get("issues", []),
                )
                for s in program["segments"]
            ],
        )
    ),
    flush=True,
)


def post(path, body):
    request = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.load(urllib.request.urlopen(request))


def envelope():
    r = json.load(urllib.request.urlopen(BASE + "/api/director/runtime"))
    return dict(
        schema_version=1,
        operation_id=str(uuid.uuid4()),
        runtime_epoch=r["runtime_epoch"],
        expires_monotonic_ns=str(int(r["now_monotonic_ns"]) + int(r["command_ttl_ns"])),
    )


if "--save" in sys.argv or "--update" in sys.argv:
    if program["blocked_shot_ids"] or program["needs_revision_shot_ids"]:
        raise SystemExit("Review findings remain; refusing to publish this candidate.")
    if "--update" in sys.argv:
        session_id = str(uuid.UUID(sys.argv[sys.argv.index("--update") + 1]))
        existing = json.load(urllib.request.urlopen(BASE + "/api/director/sessions/" + session_id))
        if existing["session"]["brief"] != brief or existing["creative"]["document"]["title"] != doc["title"]:
            raise SystemExit("The selected production is not this demo; refusing to overwrite it.")
        session = existing["session"]
        action, payload = "save_document", dict(document=doc)
    else:
        session = post("/api/director/sessions", {**envelope(), "brief": brief})["session"]
        action, payload = "start_script", dict(document=doc, context=context)
    saved = post(
        "/api/director/creative",
        {
            **envelope(),
            "scope": dict(
                session_id=session["session_id"],
                expected_revision=session["revision"],
                cancellation_generation=session["cancellation_generation"],
                take_id=None,
                plan_id=None,
            ),
            "action": action,
            "payload": payload,
        },
    )
    print(
        json.dumps(dict(saved=saved["ok"], session_id=session["session_id"], digest=digest(doc))), flush=True
    )
