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
            "track_lead",
            5,
            "Walking reveal",
            "Exterior walkway",
            "Both presenters walk forward together. The cart leads them in the same travel direction, with the camera looking back. Start on their lower bodies and tilt smoothly toward their heads over five seconds.",
            "Presenter A: Every great demo starts with a good shot.",
            dict(distance_m=1.0, actor_distance_m=1.0, radius_m=3.5),
        ),
        (
            "truck_left",
            5,
            "Truck left, then zoom",
            "Exterior open space",
            "Presenters hold their marks. The cart travels camera-left throughout. Hold 24 mm for the first two seconds, then zoom smoothly to 7.5x (180 mm equivalent relative to 24 mm) at five seconds. Finish on Presenter A; Presenter B may leave the tight frame.",
            "Presenter A: And sometimes, a closer look.",
            dict(distance_m=1.0, radius_m=4.5, bearing_rad=math.pi / 2),
        ),
        (
            "track_lead",
            11,
            "The deadline",
            "Interior building entrance",
            "Robot starts inside facing the entrance, opposite its forward travel. Record while parked for 0–3 s as presenters open the door and enter. Move forward into the building with them at 3–5 s. Park at 5 s and hold the arm pose. At 5–10 s presenters freeze while the background appears to rush past in the edit. Snap at 10 s, return to normal, deliver the line, and stop recording at 11 s.",
            "Presenter B: Wait—the hackathon is ending!",
            dict(distance_m=0.32, actor_distance_m=0.37125, radius_m=3.5),
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
                description="Presenter A's starting mark; robot leads at positive X for walking takes.",
                position_m=[0, 0],
                facing_rad=0,
            )
        )
        params = dict(
            speed_m_s=0.2,
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
        settings["subject_motion"] = "hold" if i == 2 else "walk"
        settings["scene"]["filming_side"] = "direction"
        settings["channels"]["tilt_rad"] = ramp(LOWER_RAD, LOWER_RAD)
        settings["camera"].update(zoom="fixed", horizon="level", keyframes=[])
        if i == 1:
            settings["channels"]["camera_target_m"] = ramp([0, 0, 0.75], [1, 0, 1.591])
        elif i == 2:
            settings["camera"].update(
                zoom="keyframes",
                keyframes=[
                    dict(at=0, focal_mm=24, ease="hold"),
                    dict(at=0.4, focal_mm=24, ease="smooth"),
                    dict(at=1, focal_mm=180, ease="smooth"),
                ],
            )
        else:
            settings["breath"].update(pre_hold_s=3, post_hold_s=5.8)
            # The planner adds a final 0.2 s zero-command interval before the
            # explicit hold: 0.2 + 5.8 = 6 s parked, with motion ending at 5 s.
            route_settings = path_settings(settings)
            route_settings["breath"] = settings["breath"]
            route = predict_route(route_settings)
            boundaries = (
                [0]
                + [
                    round(index * CART_PERIOD, 8)
                    for index, (a, b) in enumerate(zip(route["rows"], route["rows"][1:]), 1)
                    if a["commands"] != b["commands"]
                ]
                + [11]
            )
            blocking = [
                (t, round(route["poses"][round(t / CART_PERIOD)][0] - route["poses"][0][0], 6))
                for t in boundaries
            ]
            # Fixed target height avoids gait-bob-driven arm tracking. Target and
            # performers translate together only during the two-second travel.
            for channel, height in (
                ("actor_position_m", 0),
                ("camera_target_m", 1.3),
                ("light_target_m", 1.3),
            ):
                settings["channels"][channel] = [
                    dict(at=round(t / 11, 8), value=[x, 0, height], ease="linear") for t, x in blocking
                ]
            # Translate the optical/emitter positions rigidly with the cart.
            # Target-only IK can otherwise drift by a few counts while moving.
            # This is a simulated pose, never a measured hardware snapshot.
            preview = compile_template(settings)["preview"]
            opening = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8)
            for channel, role in (("camera_position_m", "camera"), ("light_position_m", "light")):
                pos = opening[role]["pos"]
                settings["channels"][channel] = [
                    dict(
                        at=round(t / 11, 8),
                        value=[round(v, 6) for v in (pos[0] + x, pos[1], pos[2])],
                        ease="linear",
                    )
                    for t, x in blocking
                ]
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
            camera_intent=action + " Camera pitch offset: -5 degrees throughout; keep the horizon level.",
            light_intent="Maintain consistent face illumination.",
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
                reason="Authored take; no live face tracking. Shot 3 requests a fixed arm pose.",
            ),
            movement=dict(
                template_id=template,
                subject_motion=settings["subject_motion"],
                parameters=[dict(name=k, value=v) for k, v in params.items()],
                cinematography=wire_settings(settings),
            ),
        )
        shot["motion_requirements"].update(
            actor_travel_m=0 if i == 2 else values["actor_distance_m"] * 0.8,
            cart_travel_m=values["distance_m"] * 0.8,
            camera_travel_m=0,
            arm_translation_m=0,
            arm_rotation_rad=0,
            simultaneous_s=0,
        )
        shot["design"].update(
            purpose=name,
            attention="Presenter A at the end of the zoom."
            if i == 2
            else "Both presenters and their performance.",
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
