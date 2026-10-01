"""Filmmaking intent and actor call sheets; positions remain compiler-owned."""

import copy

# Height is a suggested vertical field at the subject plane, relative to stature.
# These are editorial starting points, not universal anatomical measurements.
FRAMINGS = {
    "extreme_wide": ("Extreme wide · environment", 0.5, 3.0, "Place the person within the wider location."),
    "wide": ("Wide · person and place", 0.5, 1.6, "Keep the whole person and useful surroundings visible."),
    "full": ("Full body · head to feet", 0.5, 1.12, "Keep the head, hands and feet inside the frame."),
    "medium_full": (
        "Medium full · knees up",
        0.62,
        0.84,
        "Keep the head visible and leave a little room below the knees.",
    ),
    "cowboy": ("Cowboy · mid-thigh up", 0.67, 0.72, "Keep the hands and upper legs readable."),
    "medium": ("Medium · waist up", 0.75, 0.60, "Keep gestures near the torso and leave the face clear."),
    "medium_close_up": (
        "Medium close-up · chest up",
        0.83,
        0.43,
        "Let the face and shoulders carry the change.",
    ),
    "close_up": ("Close-up · face", 0.925, 0.28, "Hold the eyeline; use small changes in expression."),
    "extreme_close_up": (
        "Extreme close-up · detail",
        0.925,
        0.12,
        "Hold the chosen detail steady; confirm focus on the phone.",
    ),
}
COMPOSITIONS = {
    "single": "Single subject",
    "two_shot": "Two people",
    "group": "Group",
    "over_shoulder": "Over the shoulder",
    "pov": "Point of view",
    "insert": "Object / detail insert",
    "environment": "Environment",
}
ANGLES = {
    "eye_level": "Eye level",
    "low": "Low angle",
    "high": "High angle",
    "dutch": "Dutch / tilted horizon",
    "overhead": "Overhead",
    "aerial": "Aerial",
}


def catalog():
    return dict(
        sizes=[
            dict(id=k, name=v[0], actor_instruction=v[3], centre_ratio=v[1], suggested_height_ratio=v[2])
            for k, v in FRAMINGS.items()
        ],
        compositions=COMPOSITIONS,
        angles=ANGLES,
        lens_policies={"authored": "Keep chosen lens", "fit_subject": "Fit subject in its required frame"},
        scope="Shot size, composition, angle, movement and focus are separate choices. "
        "Aerial/overhead requests still need suitable equipment and a reachable setup.",
    )


def style_schema():
    from .creative import array, obj, string

    return obj(
        visual_rules=string(1000),
        palette=string(400),
        lighting=string(800),
        wardrobe=string(800),
        sound=string(800),
        continuity_locks=array(string(400), 0, 12),
    )


def schema(require_visibility=False):
    from .creative import array, obj, string

    note = dict(type="string", minLength=0, maxLength=400)
    time = dict(type="number", minimum=0, maximum=600)
    result = obj(
        purpose=string(400),
        attention=string(400),
        composition=dict(type="string", enum=list(COMPOSITIONS)),
        angle=dict(type="string", enum=list(ANGLES)),
        lens_policy=dict(type="string", enum=["authored", "fit_subject"]),
        visibility=dict(type="string", enum=["throughout", "by_end", "intentional_partial"]),
        featured_actor_ids=array(string(40), 0, 6),
        focus=obj(mode=dict(type="string", enum=["deep", "selective", "rack", "manual"]), target=string(400)),
        opening=string(600),
        ending=string(600),
        continuity=string(800),
        practical_setup=string(1000),
        beats=array(
            obj(
                start_s=time,
                end_s=time,
                actor_id=dict(type="string", minLength=0, maxLength=40),
                action=string(600),
                motivation=note,
                emotion=note,
                eyeline=note,
                delivery=note,
            ),
            1,
            16,
        ),
    )
    if not require_visibility:
        result["required"].remove("visibility")
    return result


def defaults(shot):
    """Legacy/manual drafts retain their authored movement and wording."""
    actor = shot.get("actor_id", "")
    return dict(
        purpose=shot.get("edit_intent", "Choose what this shot adds to the story."),
        attention=shot.get("camera_intent", "Keep the intended subject clear."),
        composition="single" if actor else "insert",
        angle="eye_level",
        lens_policy="authored",
        visibility="throughout",
        featured_actor_ids=[actor] if actor else [],
        focus=dict(mode="manual", target="Confirm the intended subject on the recording phone."),
        opening=shot["action"],
        ending="Hold the final action until the cut.",
        continuity="Check the eyeline, prop hand and screen direction across the cut.",
        practical_setup="Use the scene directions and marked camera route.",
        beats=[
            dict(
                start_s=0.0,
                end_s=(shot["end_ms"] - shot["start_ms"]) / 1000,
                actor_id=actor,
                action=shot["action"],
                motivation="",
                emotion="",
                eyeline="",
                delivery="",
            )
        ],
    )


def validate_links(document):
    actors = {a["actor_id"] for a in document["actors"]}
    for scene in document["scenes"]:
        staged = {m["actor_id"] for m in scene.get("cast", [])}
        for shot in scene["shots"]:
            design = shot.get("design")
            if not design:
                continue
            featured = design["featured_actor_ids"]
            available = staged | {shot["actor_id"]}
            if len(featured) != len(set(featured)) or not set(featured) <= actors & available:
                raise ValueError("Featured people must be distinct actors staged in this scene.")
            required = {"two_shot": 2, "over_shoulder": 2, "group": 3}.get(design["composition"], 0)
            if len(featured) < required:
                raise ValueError("This composition needs its featured people placed in the scene cast.")
            end = 0.0
            duration = (shot["end_ms"] - shot["start_ms"]) / 1000
            for beat in design["beats"]:
                if not end <= beat["start_s"] < beat["end_s"] <= duration + 1e-8:
                    raise ValueError(
                        "Performance beats must be ordered, non-overlapping and inside this shot's edit time."
                    )
                if beat["actor_id"] and beat["actor_id"] not in actors & available:
                    raise ValueError("A performance beat must name an actor staged in this scene.")
                end = beat["end_s"]
            if design["lens_policy"] == "fit_subject" and shot.get("movement", {}).get("template_id") not in (
                None,
                "unresolved",
            ):
                from .studio import shot_settings

                settings = shot_settings(shot)[0]
                from takeone.previs.templates import BY_ID

                if settings["camera"]["zoom"] not in ("preset", "fixed") or BY_ID[settings["template_id"]][
                    "aim"
                ] in ("zoom", "dolly_zoom"):
                    raise ValueError(
                        "Fit shot size uses a fixed lens. Keep chosen lens for an authored zoom."
                    )


def shot_card(shot):
    design = copy.deepcopy(shot.get("design") or defaults(shot))
    object_target = shot.get("camera_target", {}).get("kind") == "object"
    return dict(
        **design,
        shot_size=shot["framing"],
        size_label="Object · " + shot["framing"].replace("_", " ")
        if object_target
        else FRAMINGS[shot["framing"]][0],
        actor_instruction="Keep the object in its stated position; confirm the intended detail and focus on the phone."
        if object_target
        else FRAMINGS[shot["framing"]][3],
        source="authored_direction" if "design" in shot else "legacy_direction",
        timing="Seconds from this edit shot's first filmed frame. Setup is excluded.",
    )
