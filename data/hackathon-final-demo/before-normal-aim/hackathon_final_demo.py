"""Author the three HackTheNorth takes. Offline by default; never drives hardware."""

import argparse
import copy
import json
import math
import urllib.request
import uuid
from pathlib import Path

from takeone.director.cinematic import wire_settings
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import digest, validate_plan
from takeone.director.skills import sample_project
from takeone.director.studio import rehearsal_manifest
from takeone.motion.studio_plan import CART_PERIOD
from takeone.previs.channels import ramp
from takeone.previs.path import predict_route
from takeone.previs.sequence import build_program
from takeone.previs.templates import catalog, compile_template, defaults_for, path_settings

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/hackathon-final-demo"
LOWER_RAD = -math.radians(5)
NECK_HEIGHT_M = 1.5


def hold_arms_on_cart(settings, duration, aim_height=None):
    """Author a fixed arm pose along the cart route, independent of any person."""
    route_settings = path_settings(settings)
    route_settings["breath"] = settings["breath"]
    route_settings["channels"] = settings["channels"]
    route = predict_route(route_settings)
    boundaries = (
        [0]
        + [
            round(index * CART_PERIOD, 8)
            for index, (a, b) in enumerate(zip(route["rows"], route["rows"][1:]), 1)
            if a["commands"] != b["commands"]
        ]
        + [duration]
    )
    moves = [
        (t, [route["poses"][round(t / CART_PERIOD)][j] - route["poses"][0][j] for j in (0, 1)])
        for t in boundaries
    ]
    for name in ("camera_target_m", "light_target_m"):
        settings["channels"][name] = [
            dict(at=round(t / duration, 8), value=[round(x, 6), round(y, 6), 1.3], ease="linear")
            for t, (x, y) in moves
        ]
    preview = compile_template(settings)["preview"]
    opening = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8)
    for name, role in (("camera_position_m", "camera"), ("light_position_m", "light")):
        pos = opening[role]["pos"]
        settings["channels"][name] = [
            dict(
                at=round(t / duration, 8),
                value=[round(pos[0] + x, 6), round(pos[1] + y, 6), round(pos[2], 6)],
                ease="linear",
            )
            for t, (x, y) in moves
        ]

    if aim_height is not None:
        pos = settings["channels"]["camera_position_m"][0]["value"]
        distance = math.hypot(pos[0], pos[1])
        # Establish the baseline above the final aim, then retain the requested
        # five-degree downward offset. The resulting optical ray hits the neck.
        baseline = pos[2] + distance * math.tan(math.atan2(aim_height - pos[2], distance) - LOWER_RAD)
        for key in settings["channels"]["camera_target_m"]:
            key["value"][2] = baseline
        # Re-anchor the optical positions to the achieved pose at the new aim.
        # This avoids a one-count IK settling adjustment during the fixed take.
        settled = compile_template(settings)["preview"]["frames"][-1]
        for channel, role in (("camera_position_m", "camera"), ("light_position_m", "light")):
            keys = settings["channels"][channel]
            delta = [settled[role]["pos"][j] - keys[-1]["value"][j] for j in range(3)]
            for key in keys:
                key["value"] = [v + delta[j] for j, v in enumerate(key["value"])]
    return moves


def author():
    sample = sample_project("cinematic")
    doc = copy.deepcopy(sample["document"])
    seed_scene = copy.deepcopy(doc["scenes"][0])
    seed_shot = copy.deepcopy(seed_scene["shots"][0])
    title = "HackTheNorth final demo — three camera takes"
    brief = dict(
        title=title,
        objective="Film only the requested 5 s walking reveal, 5 s truck-left zoom, and 11 s doorway/time-freeze finale. All camera aim is 5 degrees lower. These are 21 seconds of source takes for the final demo.",
        duration_ms=21000,
        aspect_ratio="16:9",
    )
    context = dict(
        skill_id="cinematic",
        audience="HackTheNorth final demo audience",
        tone="Cinematic opening, playful deadline punchline",
        facts=[],
    )
    doc.update(
        title=title,
        logline="Our camera follows the idea, changes perspective, and catches us losing track of time.",
        audience=context["audience"],
        tone=context["tone"],
        marks=[],
        scenes=[],
        questions=[],
    )
    doc["actors"][0]["name"] = "Presenter A"
    partner = copy.deepcopy(doc["actors"][0])
    partner.update(actor_id="actor-b", name="Presenter B")
    partner["appearance"]["cloth"] = "#245a83"
    doc["actors"].append(partner)
    doc["visual_style"].update(
        palette="Natural campus colors; consistent wardrobe across all three takes.",
        visual_rules="Three independent takes. Apply minus 5 degrees of pitch relative to the authored aim throughout. No extra product-demo shots.",
        lighting="Available exterior and lobby light; keep faces readable.",
        sound="Footsteps, door opening, a rising time-rush sound, a dry finger snap and the final line.",
        continuity_locks=[
            "Same two presenters and wardrobe.",
            "Reset the robot between takes, outside recording.",
            "All geometry and travel distances are illustrative staging assumptions.",
        ],
    )
    rows = [
        (
            "track_follow",
            5,
            "Walking reveal",
            "Exterior walkway",
            "Both presenters walk ahead of the robot, facing forward; the robot follows behind and films their backs. Travel 0.55 m during 0–4 s, then hold for 4–5 s while completing the lower-body-to-head reveal. Average speed over the five-second take is 0.11 m/s; moving speed is approximately 0.1375 m/s, the current motor model's minimum. Camera movement is scripted, with no live person tracking.",
            "Presenter A: Every great demo starts with a good shot.",
            dict(distance_m=0.56, actor_distance_m=0.55, radius_m=3.5),
        ),
        (
            "truck_right",
            5,
            "Left-side camera, then zoom",
            "Exterior open space",
            "Initialize the camera facing the presenters on the robot's left, aimed at neck level (1.50 m in the illustrative scene) after the five-degree downward offset. Hold both arm poses relative to the cart; do not turn toward or track any person. Keep the cart's original forward travel direction. Hold 24 mm for 0–2 seconds, zoom to 180 mm during 2–3 seconds, then hold 180 mm until the five-second take ends.",
            "Presenter A: And sometimes, a closer look.",
            dict(distance_m=1.0, radius_m=4.5, bearing_rad=-math.pi / 2),
        ),
        (
            "track_lead",
            11,
            "The deadline",
            "Interior building entrance",
            "Robot starts inside facing the entrance, opposite its forward travel. Record while parked for 0–3 s as presenters open the door and enter. Move forward into the building with them at 3–5 s, requesting 0.30 m/s cruise with a 0.275 m/s pace cap to preserve the two-second ramped move. Park at 5 s and hold the arm pose. At 5–10 s presenters freeze while the background appears to rush past in the edit. Snap at 10 s, return to normal, deliver the line, and stop recording at 11 s.",
            "Presenter B: Wait—the hackathon is ending!",
            dict(distance_m=0.26, actor_distance_m=0.26, radius_m=3.5),
        ),
    ]
    clock = 0
    for i, (template, duration, name, location, action, line, values) in enumerate(rows, 1):
        scene_id, shot_id, mark_id = f"htn-scene-{i}", f"htn-shot-{i}", f"htn-mark-{i}"
        scene = copy.deepcopy(seed_scene)
        scene.update(
            scene_id=scene_id,
            space_id=scene_id,
            title=name,
            location=location,
            atmosphere="interior_day" if i == 3 else "exterior_day",
            shots=[],
            objects=[],
            location_notes="Illustrative staging, not measured venue geometry. Door opens clear of the robot route."
            if i == 3
            else "Illustrative open level walkway; reset between takes.",
            cast=[dict(actor_id="actor-b", offset_m=[0, 0.7, 0], facing_rad=0, motion="with_lead")],
        )
        # The entrance is behind the actor's starting mark; robot begins inside at +X.
        if i == 3:
            for side, y in (("left", -2), ("right", 2)):
                scene["objects"].append(
                    dict(
                        object_id=f"entrance-{side}",
                        asset_id="wall",
                        label=f"Entrance {side} wall — assumed",
                        position_m=[-0.6, y, 1.5],
                        size_m=[0.15, 2.2, 3],
                        yaw_rad=0,
                        availability="proposed",
                        production_role="Entrance frame; perform door action.",
                    )
                )
        else:
            scene["objects"].append(
                dict(
                    object_id="campus-background",
                    asset_id="facade",
                    label="Campus facade — assumed",
                    position_m=[-10, 0, 2.5],
                    size_m=[0.3, 12, 5],
                    yaw_rad=0,
                    availability="proposed",
                    production_role="Background context and parallax.",
                )
            )
        doc["marks"].append(
            dict(
                mark_id=mark_id,
                scene_id=scene_id,
                description="Presenter A's interior mark; robot follows at negative X in shot 1 and leads at positive X in shot 3.",
                position_m=[0, 0],
                facing_rad=0,
            )
        )
        params = dict(
            speed_m_s=0.3 if i == 3 else 0.14 if i == 1 else 0.2,
            duration_s=duration,
            actor_heading_rad=0,
            height_start_m=1.3,
            height_end_m=1.3,
            light_height_start_m=1.5,
            light_height_end_m=1.5,
            focal_mm=24,
            **values,
        )
        settings = defaults_for(template) | params
        # Cast remains in the storyboard only. Explicit arm target channels
        # below are independent of those illustrative people and their marks.
        settings["subject_motion"] = "hold"
        settings["scene"]["filming_side"] = "direction"
        settings["channels"]["tilt_rad"] = ramp(LOWER_RAD, LOWER_RAD)
        settings["camera"].update(zoom="fixed", horizon="level", keyframes=[])
        if i == 1:
            settings["breath"].update(post_hold_s=0.8)
            settings["channels"]["actor_position_m"] = [
                dict(at=0, value=[0, 0, 0], ease="linear"),
                dict(at=0.8, value=[0.55, 0, 0], ease="linear"),
                dict(at=1, value=[0.55, 0, 0], ease="linear"),
            ]
            settings["channels"]["actor_heading_rad"] = ramp(0, 0)
            settings["channels"]["camera_target_m"] = [
                dict(at=0, value=[0, 0, 0.75], ease="linear"),
                dict(at=0.8, value=[0.55, 0, 1.4228], ease="linear"),
                dict(at=1, value=[0.55, 0, 1.591], ease="linear"),
            ]
            settings["channels"]["light_target_m"] = [
                dict(at=k["at"], value=[*k["value"][:2], 1.3], ease="linear")
                for k in settings["channels"]["actor_position_m"]
            ]
        elif i == 2:
            settings["camera"].update(
                zoom="keyframes",
                keyframes=[
                    dict(at=0, focal_mm=24, ease="hold"),
                    dict(at=0.4, focal_mm=24, ease="smooth"),
                    dict(at=0.6, focal_mm=180, ease="hold"),
                    dict(at=1, focal_mm=180, ease="hold"),
                ],
            )
            hold_arms_on_cart(settings, duration, aim_height=NECK_HEIGHT_M)
        else:
            settings["breath"].update(pre_hold_s=3, post_hold_s=5.8)
            settings["channels"]["pace_m_s"] = ramp(0.275, 0.275)
            # The planner adds a final 0.2 s zero-command interval before the
            # explicit hold: 0.2 + 5.8 = 6 s parked, with motion ending at 5 s.
            moves = hold_arms_on_cart(settings, duration)
            # Performance blocking is independent of the fixed arm tracks.
            # Open the door for one second, enter by 3 s, walk with the cart
            # until 5 s, then freeze through the snap and final line.
            settings["channels"]["actor_position_m"] = [
                dict(at=0, value=[-1.4, 0, 0], ease="linear"),
                dict(at=1 / duration, value=[-1.4, 0, 0], ease="linear"),
            ] + [
                dict(at=round(t / duration, 8), value=[x, y, 0], ease="linear")
                for t, (x, y) in moves
                if t >= 3
            ]
            settings["channels"]["actor_heading_rad"] = ramp(0, 0)
        allowed = set(next(t for t in catalog()["templates"] if t["id"] == template)["parameters"]) | {
            "focal_mm"
        }
        params = {k: v for k, v in params.items() if k in allowed}
        shot = copy.deepcopy(seed_shot)
        shot.update(
            shot_id=shot_id,
            start_ms=clock * 1000,
            end_ms=(clock + duration) * 1000,
            mark_id=mark_id,
            action=action,
            framing="extreme_close_up" if i == 2 else "medium_full" if i == 1 else "wide",
            primitive="template",
            camera_intent="Initialize the arms, then execute the authored camera movement. No human detection, centering, or tracking. Camera pitch offset: -5 degrees throughout; keep the horizon level.",
            light_intent="Execute the authored light-arm pose without tracking people.",
            edit_intent="Time-rush background is a masked post-production effect at 5–10 s. Snap at 10 s; dry dialogue to 11 s."
            if i == 3
            else "Cut at five seconds. No reset footage in the edit.",
            audio_intent="Record the final line live; opening lines may be voiceover. Snap is the effect transition cue.",
            lines=[dict(text=line, tone=context["tone"], fact_ids=[])],
            selected_line=0,
            capture=dict(take_id=f"htn-take-{i}", in_s=0),
            performers=[],
            tracking=dict(
                cart="planned",
                phone="planned",
                on_loss="stop_and_hold",
                reason="Initialize arms and play the script. No person is required. Shots 2 and 3 hold their arm pose relative to the cart.",
            ),
            movement=dict(
                template_id=template,
                subject_motion=settings["subject_motion"],
                parameters=[dict(name=k, value=v) for k, v in params.items()],
                cinematography=wire_settings(settings),
            ),
        )
        shot["motion_requirements"].update(
            actor_travel_m=1.4 if i == 3 else 0.55 if i == 1 else 0,
            cart_travel_m=values["distance_m"] * 0.8,
            camera_travel_m=0,
            arm_translation_m=0,
            arm_rotation_rad=0,
            simultaneous_s=0,
        )
        shot["design"].update(
            purpose=name,
            attention="Execute the scripted movement; people are not camera or light control targets.",
            opening=action,
            ending="Cut at the authored recording endpoint.",
            angle="low",
            composition="single" if i == 2 else "two_shot",
            featured_actor_ids=["actor-a"] if i == 2 else ["actor-a", "actor-b"],
            visibility="intentional_partial" if i == 2 else "by_end" if i == 1 else "throughout",
            continuity="Same presenters and wardrobe; independent takes.",
            practical_setup="Stage and check the requested framing before recording.",
            beats=[
                dict(
                    start_s=0,
                    end_s=duration,
                    actor_id="actor-a",
                    action=action,
                    motivation=name,
                    emotion="Playful confidence",
                    eyeline="Toward the lens",
                    delivery="Final line is quick and urgent; begin on the snap.",
                )
            ],
        )
        scene["shots"].append(shot)
        doc["scenes"].append(scene)
        clock += duration
    validate_plan(doc, ProductionBrief.parse(brief), context)
    return dict(brief=brief, context=context, document=doc)


def request(base, path, body=None):
    req = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def save_draft(base, candidate, session_id=None):
    def envelope():
        runtime = request(base, "/api/director/runtime")
        return dict(
            schema_version=1,
            operation_id=str(uuid.uuid4()),
            runtime_epoch=runtime["runtime_epoch"],
            expires_monotonic_ns=str(int(runtime["now_monotonic_ns"]) + int(runtime["command_ttl_ns"])),
        )

    if session_id:
        existing = request(base, "/api/director/sessions/" + str(uuid.UUID(session_id)))
        if existing["session"]["brief"] != candidate["brief"]:
            raise ValueError("The selected production is not this demo.")
        session = existing["session"]
        action, payload = "save_document", dict(document=candidate["document"])
    else:
        session = request(base, "/api/director/sessions", envelope() | dict(brief=candidate["brief"]))[
            "session"
        ]
        action, payload = "start_script", dict(document=candidate["document"], context=candidate["context"])
    saved = request(
        base,
        "/api/director/creative",
        envelope()
        | dict(
            scope=dict(
                session_id=session["session_id"],
                expected_revision=session["revision"],
                cancellation_generation=session["cancellation_generation"],
                take_id=None,
                plan_id=None,
            ),
            action=action,
            payload=payload,
        ),
    )
    if not saved.get("ok"):
        raise RuntimeError(saved)
    return dict(session_id=session["session_id"], url=f"{base}/director.html?session={session['session_id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save as a new local Director draft, without approval or execution.",
    )
    parser.add_argument("--base", default="http://127.0.0.1:8766")
    parser.add_argument("--update", help="Update this demo's existing draft by session ID.")
    args = parser.parse_args()
    candidate = author()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "production.json").write_text(
        json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    doc = candidate["document"]
    detail = dict(
        session=dict(session_id="htn-candidate", revision=0, brief=candidate["brief"]),
        creative=dict(document=doc, digest=digest(doc), context=candidate["context"]),
    )
    manifest = rehearsal_manifest(detail, digest(doc))
    (OUTPUT / "rehearsal.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    program = build_program(manifest)
    report = dict(
        blocked=program["blocked_shot_ids"],
        needs_revision=program["needs_revision_shot_ids"],
        shots=[
            dict(
                id=s["shot_id"],
                filming_s=s.get("filming_s"),
                diagnostics=s["diagnostics"],
                review=s.get("shot_review"),
            )
            for s in program["segments"]
        ],
    )
    (OUTPUT / "review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.save or args.update:
        report["saved"] = save_draft(args.base, candidate, args.update)
        (OUTPUT / "saved.json").write_text(json.dumps(report["saved"], indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "shots"}, indent=2))
    for shot in report["shots"]:
        print(
            json.dumps(
                dict(
                    id=shot["id"],
                    filming_s=shot["filming_s"],
                    diagnostics=shot["diagnostics"],
                    issues=(shot["review"] or {}).get("issues"),
                )
            )
        )


if __name__ == "__main__":
    main()
