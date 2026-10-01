"""Install a clearly labelled authored exercise; no AI call or hardware action."""

import argparse
import copy
import json
import math
from pathlib import Path

from cinematic_upgrade_demo import envelope, request
from takeone.director.cinematic import wire_settings
from takeone.previs.channels import ramp
from takeone.previs.templates import defaults_for

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data/shot-language-20260915"


def project():
    """Test data exercises one reusable compiler; it is not a brief-to-story generator."""
    title = "A small discovery · shot-language exercise"
    brief = dict(
        title=title,
        duration_ms=30000,
        aspect_ratio="16:9",
        objective="Authored verification exercise: a visitor notices a handmade object, shares the discovery, and decides to build something of their own.",
    )
    context = dict(
        skill_id="cinematic",
        audience="Director workflow review",
        tone="Quiet observation grows into a shared decision.",
        facts=[],
    )
    actors = [dict(actor_id="visitor", name="Visitor"), dict(actor_id="maker", name="Maker")]
    style = dict(
        visual_rules="Begin with visible space around the visitor. Narrow attention only after the discovery; return to a readable body gesture at the finish.",
        palette="Muted stone and sage outside; warm wood in the room; one teal object gives the eye a destination.",
        lighting="Soft side daylight outside; warm practical light by the shelf; keep the object highlight on the same side.",
        wardrobe="Visitor keeps a plain rust overshirt. Maker keeps a dark top. Keep the object in the same position through its inserts.",
        sound="Let footsteps introduce the film. The room becomes quiet at recognition. Finish on a deliberate breath and the table touch.",
        continuity_locks=[
            "The visitor notices the shelf before turning to the maker.",
            "The object remains on its plinth.",
            "Carry the eyeline into the object insert.",
        ],
    )

    def prop(id, asset, label, position, size):
        return dict(object_id=id, asset_id=asset, label=label, position_m=position, size_m=size, yaw_rad=0)

    scenes = [
        dict(
            scene_id="courtyard",
            space_id="courtyard",
            title="Room to arrive",
            location="A quiet level courtyard",
            atmosphere="exterior_day",
            location_notes="Find a level paved opening with a wall or doorway behind the performer. Keep three metres clear in front for the camera and a clear exit at frame right.",
            objects=[
                prop("entry", "arch", "Workshop", [0, 3, 1.7], [3, 0.35, 3.4]),
                prop("seat", "bench", "Resting place", [2.5, 2, 0.4], [1.6, 0.5, 0.8]),
            ],
            cast=[],
            shots=[],
        ),
        dict(
            scene_id="room",
            space_id="room",
            title="Someone else sees it too",
            location="A room with a display and warm practical light",
            atmosphere="interior_warm",
            location_notes="Find a display against a quiet wall. Leave the foreground open for the visitor and maker. The camera stays on this side of their conversation.",
            objects=[
                prop("display", "shelf", "Handmade display", [0, 2.5, 1], [1.8, 0.45, 2]),
                prop("sofa", "sofa", "Seating", [-2, 3, 0.45], [2, 0.85, 0.9]),
                prop("lamp", "practical_light", "Warm practical", [2, 2, 0.9], [0.4, 0.4, 1.8]),
            ],
            cast=[dict(actor_id="maker", offset_m=[0.9, 0, 0], facing_rad=-math.pi / 2, motion="hold")],
            shots=[],
        ),
        dict(
            scene_id="workbench",
            space_id="workbench",
            title="Choose to begin",
            location="A clear work surface",
            atmosphere="interior_cool",
            location_notes="Use a quiet work area with a real handmade object on a stable plinth. Keep labels readable and leave the cart lane in front clear.",
            objects=[
                prop("object", "product", "Handmade object proxy", [0, 0, 1.4], [0.16, 0.16, 0.3]),
                prop("stand", "plinth", "Object stand", [0, 0, 0.625], [0.6, 0.6, 1.25]),
                prop("counter", "counter", "Work surface", [2.5, 1.5, 0.525], [2.4, 0.75, 1.05]),
            ],
            cast=[],
            shots=[],
        ),
    ]
    data = [
        (
            0,
            5,
            0,
            "full",
            "static",
            "Arrive without hurry.",
            "Keep the whole body in the place.",
            "Wait on the mark with shoulders loose.",
            "Let the eyes settle on the doorway.",
            [
                (
                    "Keep your weight evenly placed; hear the footsteps fade.",
                    "Settle into the place.",
                    "Calm and observant.",
                    "Past the camera toward the doorway.",
                ),
                (
                    "Lift your gaze slightly, without moving your feet.",
                    "A new detail has caught your attention.",
                    "Interest begins.",
                    "The doorway, then the shelf beyond.",
                ),
            ],
        ),
        (
            5,
            9,
            1,
            "medium_close_up",
            "boom_up",
            "Make recognition visible.",
            "Notice the look before the turn.",
            "Look past the lens toward the display.",
            "Turn the head only after the eyes have settled.",
            [
                (
                    "Hold the eyeline for one breath.",
                    "Make sure you have seen it.",
                    "Uncertain interest.",
                    "Toward the shelf.",
                ),
                (
                    "Turn your head a little toward the maker.",
                    "Share the discovery.",
                    "Recognition.",
                    "Maker's eyes.",
                ),
            ],
        ),
        (
            9,
            15,
            1,
            "medium",
            "static",
            "Show a shared decision.",
            "See both people in the same frame.",
            "Visitor holds the maker's eyeline.",
            "Both look toward the workbench.",
            [
                (
                    "Give the maker time to meet your look.",
                    "Check that they understand.",
                    "Tentative agreement.",
                    "Each other.",
                ),
                (
                    "Nod once, then let the gaze travel toward the workbench.",
                    "Invite the next action.",
                    "Quiet confidence.",
                    "Workbench at frame right.",
                ),
            ],
        ),
        (
            15,
            19,
            2,
            "close_up",
            "product_highlight",
            "Show what caught their attention.",
            "Read the object's shape and surface.",
            "Hold the object still on the plinth.",
            "Let the highlight complete its pass.",
            [
                (
                    "Leave the object untouched while the light travels.",
                    "Show the surface honestly.",
                    "",
                    "Object surface.",
                ),
                (
                    "Hold the final highlight without cutting too soon.",
                    "Give the viewer time to recognize the detail.",
                    "",
                    "Lit edge.",
                ),
            ],
        ),
        (
            19,
            24,
            1,
            "close_up",
            "static",
            "Let the choice register.",
            "Read the face after the object insert.",
            "Visitor looks toward the display.",
            "Release a breath and hold the decision.",
            [
                (
                    "Keep the mouth relaxed; allow one small inhale.",
                    "You have found a starting point.",
                    "A decision forms.",
                    "Display.",
                ),
                (
                    "Exhale; let the shoulders settle.",
                    "Commit without a spoken slogan.",
                    "Resolved.",
                    "Toward the workbench.",
                ),
            ],
        ),
        (
            24,
            30,
            0,
            "medium_full",
            "boom_up",
            "Finish on purposeful movement.",
            "Read the body turn toward the next task.",
            "Hold the starting mark.",
            "Turn and settle, ready to begin.",
            [
                (
                    "Hold the eyes on the next task for a moment.",
                    "Know where you are going.",
                    "Confidence.",
                    "Frame right.",
                ),
                (
                    "Turn the body a little and hold the finish.",
                    "The next action belongs beyond this film.",
                    "Ready.",
                    "Keep looking toward the next task.",
                ),
            ],
        ),
    ]
    marks = []
    for i, (start, end, scene_index, size, template, purpose, attention, opening, ending, beats) in enumerate(
        data
    ):
        scene = scenes[scene_index]
        actor = "" if template.startswith("product_") else "visitor"
        settings = defaults_for(template) | dict(
            duration_s=end - start, radius_m=3, height_start_m=1.55, height_end_m=1.55
        )
        if template == "boom_up":
            settings["height_start_m"] = 1.50
        if i == 1:
            settings["channels"].update(gaze_yaw_rad=ramp(0, 0.3, 0.35, 0.8), gaze_pitch_rad=ramp(0, 0.08))
        if i == 5:
            settings["channels"].update(actor_heading_rad=ramp(-math.pi / 2, -math.pi / 2 + 0.35, 0.35, 0.85))
        mark_id = "mark-" + str(i + 1)
        marks.append(
            dict(
                mark_id=mark_id,
                scene_id=scene["scene_id"],
                description="Starting floor mark for this take.",
                position_m=[0, 0],
                facing_rad=-math.pi / 2,
            )
        )
        duration = end - start
        timed = [
            dict(
                start_s=j * duration / 2,
                end_s=(j + 1) * duration / 2,
                actor_id=actor,
                action=b[0],
                motivation=b[1],
                emotion=b[2],
                eyeline=b[3],
                delivery="",
            )
            for j, b in enumerate(beats)
        ]
        shot = dict(
            shot_id="shot-" + str(i + 1),
            start_ms=start * 1000,
            end_ms=end * 1000,
            actor_id=actor,
            mark_id=mark_id,
            action=opening + " " + ending,
            framing=size,
            primitive="template",
            camera_intent=attention,
            light_intent=style["lighting"],
            edit_intent=purpose,
            lines=[],
            selected_line=0,
            audio_intent="Natural room sound and one unforced breath.",
            movement=dict(
                template_id=template,
                subject_motion="hold" if actor else "none",
                parameters=[
                    dict(name="radius_m", value=3),
                    dict(name="height_start_m", value=settings["height_start_m"]),
                    dict(name="height_end_m", value=settings["height_end_m"]),
                ]
                if template == "boom_up"
                else [dict(name="radius_m", value=3)],
                cinematography=wire_settings(settings),
            ),
            transition="cut",
            camera_target=dict(kind="actor" if actor else "object", target_id=actor or "object"),
            tracking=dict(
                cart="planned",
                phone="planned",
                on_loss="stop_and_hold",
                reason="Rehearse the authored camera path and blocking.",
            ),
            capture=dict(take_id="", in_s=0),
            design=dict(
                purpose=purpose,
                attention=attention,
                composition="two_shot" if i == 2 else "single" if actor else "insert",
                angle="eye_level",
                lens_policy="fit_subject",
                featured_actor_ids=["visitor", "maker"] if i == 2 else [actor] if actor else [],
                focus=dict(mode="manual", target="Eyes" if actor else "The lit edge of the object"),
                opening=opening,
                ending=ending,
                continuity="Keep the stated eyeline through the cut.",
                practical_setup=scene["location_notes"],
                beats=timed,
            ),
        )
        scene["shots"].append(shot)
    # Scene arrays must preserve edit order even when returning to the same physical space.
    ordered = []
    for scene in scenes:
        for shot in scene["shots"]:
            ordered.append((shot["start_ms"], scene, shot))
    result_scenes = []
    for index, (_, scene, shot) in enumerate(sorted(ordered, key=lambda row: row[0])):
        stage = copy.deepcopy(scene)
        stage["scene_id"] = scene["scene_id"] + "-beat-" + str(index + 1)
        stage["shots"] = [shot]
        next(m for m in marks if m["mark_id"] == shot["mark_id"])["scene_id"] = stage["scene_id"]
        result_scenes.append(stage)
    return dict(
        brief=brief,
        context=context,
        document=dict(
            title=title,
            logline=brief["objective"],
            audience=context["audience"],
            tone=context["tone"],
            actors=actors,
            marks=marks,
            questions=[],
            visual_style=style,
            scenes=result_scenes,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    DESTINATION.mkdir(parents=True, exist_ok=True)
    sample = project()
    (DESTINATION / "authored-exercise.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    if not args.install:
        return
    installed = DESTINATION / "installed-exercise.json"
    if installed.exists():
        raise ValueError("This exercise was already installed. Preserve the saved draft.")
    existing = [s for s in request("/api/director/sessions")["sessions"] if s["brief"] == sample["brief"]]
    if existing:
        session = existing[0]
    else:
        result = request("/api/director/sessions", envelope() | dict(brief=sample["brief"]))
        session = result["session"]
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
            | dict(
                scope=scope, action="start_script", payload={k: sample[k] for k in ("document", "context")}
            ),
        )
    detail = request("/api/director/sessions/" + session["session_id"])
    ref = session["session_id"] + "/" + detail["creative"]["digest"]
    manifest = request("/api/director/studio/" + ref)
    program = request("/api/previs/sequence", manifest)
    installed.write_text(json.dumps(dict(reference=ref, program=program), indent=2), encoding="utf-8")
    print("http://127.0.0.1:8766/?script=" + ref)


if __name__ == "__main__":
    main()
