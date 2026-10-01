"""Curated, versioned filmmaking knowledge. These records grant no tool authority."""

import copy
import json
import math
from pathlib import Path


def load_skills():
    """Load versioned editorial instructions from packaged Markdown, with JSON/YAML metadata."""
    result = {}
    for path in sorted((Path(__file__).parent / "filming-skills").glob("*/SKILL.md")):
        _, frontmatter, body = path.read_text(encoding="utf-8").split("---", 2)
        meta = json.loads(frontmatter)
        profile = meta["metadata"]
        result[profile["id"]] = profile | {"instructions": body.strip()}
    if not result:
        raise RuntimeError("No packaged filming skills are installed")
    return result


SKILLS = load_skills()


def stage_sample(result):
    """Examples use the current scene contract without implying a surveyed location."""
    from .cinematic import wire_settings
    from .scenes import tracking_intent
    from .studio import shot_settings

    document = result["document"]
    marks = {m["mark_id"]: m for m in document["marks"]}
    for scene in document["scenes"]:
        scene.update(
            space_id=scene["scene_id"],
            atmosphere="studio",
            objects=[],
            cast=[],
            location_notes="Find a clear level rehearsal area with space for the illustrated camera path.",
        )
        for shot in scene["shots"]:
            # A sample may have changed movement after an earlier staging pass.
            inferred_tracking = tracking_intent(
                {key: value for key, value in shot.items() if key != "tracking"}
            )
            shot.update(
                transition="cut",
                camera_target=dict(kind="actor", target_id=shot["actor_id"]),
                tracking=inferred_tracking,
                audio_intent="Dialogue and natural room sound.",
                capture=dict(take_id="", in_s=0.0),
            )
            if shot.get("movement", {}).get("template_id") not in (None, "unresolved"):
                shot["movement"]["cinematography"] = wire_settings(shot_settings(shot)[0])
            marks[shot["mark_id"]].setdefault("scene_id", scene["scene_id"])
    for mark in marks.values():
        mark.setdefault("scene_id", document["scenes"][0]["scene_id"])
        mark.setdefault("position_m", [0.0, 0.0])
        mark.setdefault("facing_rad", 0.0)
    return result


def sample_project(skill_id):
    """Explicit editorial examples, independent of custom briefs and provider failures."""
    if skill_id == "cinematic":
        return cinematic_sample()
    skill = SKILLS[skill_id]
    dialogue = skill_id == "dialogue"
    product = skill_id == "product"
    title = {
        "product": "An introduction worth watching",
        "dialogue": "Astra, Claude & a second opinion",
        "reaction": "The look says everything",
    }[skill_id]
    context = {"skill_id": skill_id, "audience": skill["audience"], "tone": skill["tone"], "facts": []}
    brief = {
        "title": title,
        "objective": (
            "Introduce a product naturally. Product name and features have not been supplied."
            if product
            else "A fictional disagreement: one person prefers Astra, the other prefers Claude. No benchmark claims."
            if dialogue
            else "An actor notices a surprising detail just off camera, then gives a restrained reaction."
        ),
        "duration_ms": 18000,
        "aspect_ratio": "9:16",
    }
    lines = {
        "product": [
            [
                "Meet [product name]. Let me show you one detail.",
                "Here's [product name], up close.",
                "A quick look at [product name].",
            ],
            ["This is [verified feature].", "Take a look at [verified feature].", "Here's the detail."],
            ["Want a closer look?", "What would you like to see next?", "Let's take a closer look."],
        ],
        "dialogue": [
            ["I asked Astra for a second opinion.", "Astra and I have a plan.", "I have a plan. Mostly."],
            ["Funny. I asked Claude for a third.", "Claude would like a word.", "I brought a second plan."],
            ["Maybe we should ask each other.", "Shall we try our own idea?", "Fine. Your turn."],
        ],
        "reaction": [
            ["Wait a second.", "Hang on.", "Oh."],
            ["That was not the plan.", "Well, that's new.", "I did not see that coming."],
            ["Let's try that again.", "One more take?", "You saw that too, right?"],
        ],
    }[skill_id]
    actions = (
        [
            "Hold the product at chest height; look into the lens.",
            "Turn the product slowly to show the verified feature; leave room around it.",
            "Return your eyes to the lens and hold a relaxed finish.",
        ]
        if product
        else [
            "Actor A at mark A looks toward actor B at mark B.",
            "Actor B at mark B pauses, then replies toward mark A.",
            "Actor A holds the eyeline, then lets a small smile appear.",
        ]
        if dialogue
        else [
            "Look toward mark B, a fixed eyeline target just off camera.",
            "Hold for one beat, then let the eyebrows lift slightly.",
            "Look back to the lens and give a small, dry smile.",
        ]
    )
    shots = []
    for index, alternatives in enumerate(lines):
        shots.append(
            {
                "shot_id": f"shot-{index + 1}",
                "start_ms": index * 6000,
                "end_ms": (index + 1) * 6000,
                "actor_id": "actor-b" if dialogue and index == 1 else "actor-a",
                "mark_id": "B" if dialogue and index == 1 else "A",
                "action": actions[index],
                "framing": "close_up" if index == 1 else "medium",
                "primitive": "static",
                "camera_intent": "Hold a fixed frame. Reposition between takes for the closer view.",
                "light_intent": "Soft key from the rear light arm, clear of the phone view; placement unverified.",
                "edit_intent": "Cut on the response; keep a short pause."
                if dialogue
                else "Straight cut on the beat.",
                "lines": [
                    {"text": line, "tone": tone, "fact_ids": []}
                    for line, tone in zip(alternatives, ("Natural", "Shorter", "Playful"), strict=True)
                ],
                "selected_line": 0,
            }
        )
    document = {
        "title": title,
        "logline": brief["objective"],
        "audience": context["audience"],
        "tone": context["tone"],
        "actors": [{"actor_id": "actor-a", "name": "Presenter" if product else "Actor A"}]
        + ([{"actor_id": "actor-b", "name": "Actor B"}] if dialogue else []),
        "marks": [
            {"mark_id": "A", "description": "Actor's starting position; place and measure in Step 3."},
            {"mark_id": "B", "description": "Other actor or eyeline target; position not yet measured."},
        ],
        "questions": ["What is the product name and one verified feature?"]
        if product
        else ["Where should marks A and B be placed in the room?"],
        "scenes": [
            {
                "scene_id": "scene-1",
                "title": "The introduction" if product else "The exchange",
                "location": "Interior · level floor · room to be confirmed",
                "shots": shots,
            }
        ],
    }
    return stage_sample(copy.deepcopy({"brief": brief, "context": context, "document": document}))


def cinematic_sample():
    """A labelled offline example of the same contract requested from Luna."""
    result = sample_project("reaction")
    skill = SKILLS["cinematic"]
    result["context"].update(skill_id="cinematic", audience=skill["audience"], tone=skill["tone"])
    result["brief"].update(
        title=skill["name"],
        duration_ms=32000,
        aspect_ratio="16:9",
        objective="Introduce a serious character with a rising orbit, follow their walk, then reveal a realization with a Dolly Zoom.",
    )
    doc = result["document"]
    doc.update(
        title=skill["name"],
        logline=result["brief"]["objective"],
        audience=skill["audience"],
        tone=skill["tone"],
        questions=[],
        marks=[
            dict(
                mark_id="A",
                description="Opening mark on the level studio floor.",
                position_m=[0, 0],
                facing_rad=0,
            ),
            dict(
                mark_id="B",
                description="Final take's setup mark, 0.8 m along the set's X axis from A.",
                position_m=[0.8, 0],
                facing_rad=0,
            ),
        ],
    )
    scene = doc["scenes"][0]
    scene.update(title="The decision", location="Interior · level studio floor")
    choices = [
        (
            "hero_orbit",
            0,
            12000,
            "A",
            "hold",
            "Hold a steady gaze as the camera rises from chest height toward the face.",
            "Begin low to give the character presence. Rise while orbiting through 30 degrees; face aim relaxes toward level.",
            "I know what comes next.",
            dict(
                radius_m=2.5,
                sweep_rad=math.pi / 6,
                speed_m_s=0.17,
                height_start_m=1.25,
                height_end_m=1.59,
                rise_start=0.1,
                rise_end=0.85,
                light_height_start_m=1.5,
                light_height_end_m=1.65,
                focal_mm=35,
            ),
        ),
        (
            "side_track",
            12000,
            22000,
            "A",
            "walk",
            "Walk slowly 0.8 m across the shot while the cart tracks alongside. Reset to B between takes.",
            "Travel alongside the walking actor, retaining face aim and an eye-level camera.",
            "One step at a time.",
            dict(
                radius_m=2.5,
                distance_m=0.8,
                actor_distance_m=0.8,
                actor_heading_rad=0,
                speed_m_s=0.17,
                focal_mm=35,
            ),
        ),
        (
            "dolly_zoom_out",
            22000,
            32000,
            "B",
            "hold",
            "Begin the final take at B, look toward the camera and hold for the realization.",
            "Retreat 0.6 m while the lens tightens to keep the actor's image size steady.",
            "Now I see it.",
            dict(radius_m=2.5, distance_m=0.6, speed_m_s=0.17, focal_mm=35),
        ),
    ]
    for shot, (template, start, end, mark, motion, action, camera, line, values) in zip(
        scene["shots"], choices, strict=True
    ):
        shot.update(
            start_ms=start,
            end_ms=end,
            mark_id=mark,
            primitive="template",
            action=action,
            camera_intent=camera,
            framing="medium",
            light_intent="The independent light arm follows the actor; rise with the opening reveal.",
            edit_intent="Cut after the held beat; reposition between takes is excluded from the edit.",
            lines=[dict(text=line, tone=skill["tone"], fact_ids=[])],
            selected_line=0,
            movement=dict(
                template_id=template,
                subject_motion=motion,
                parameters=[dict(name=name, value=value) for name, value in values.items()],
            ),
        )
    return stage_sample(result)
