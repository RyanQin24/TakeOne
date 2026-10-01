"""Scene authoring data, object catalog and follow intent; no device access."""

import copy
import math

OBJECTS = {
    "facade": ("Building facade", [8.0, 0.3, 4.0]),
    "doorway": ("Open doorway", [2.6, 0.25, 3.0]),
    "sign": ("Lettered sign", [2.4, 0.12, 0.55]),
    "wall": ("Wall", [4.0, 0.2, 3.0]),
    "window": ("Window panel", [2.0, 0.12, 1.8]),
    "tree": ("Tree", [1.2, 1.2, 3.4]),
    "bench": ("Bench", [1.6, 0.5, 0.8]),
    "planter": ("Planter", [0.7, 0.7, 0.9]),
    "table": ("Work table", [1.6, 0.8, 0.75]),
    "chair": ("Chair", [0.5, 0.5, 0.85]),
    "laptop": ("Open laptop", [0.36, 0.24, 0.25]),
    "product": ("Product bottle", [0.16, 0.16, 0.3]),
    "plinth": ("Product plinth", [0.6, 0.6, 1.25]),
    "practical_light": ("Practical lamp", [0.4, 0.4, 1.8]),
    "bollard": ("Bollard", [0.2, 0.2, 0.85]),
    "sofa": ("Sofa", [2.0, 0.85, 0.9]),
    "counter": ("Counter / reception desk", [2.4, 0.75, 1.05]),
    "shelf": ("Display shelving", [1.8, 0.45, 2.0]),
    "arch": ("Arch / passage", [3.0, 0.35, 3.4]),
    "screen": ("Freestanding screen", [1.6, 0.15, 2.1]),
    "rock": ("Rock / landscape marker", [1.1, 0.8, 0.7]),
}
ATMOSPHERES = (
    "exterior_day",
    "exterior_dusk",
    "exterior_night",
    "interior_day",
    "interior_warm",
    "interior_cool",
    "studio",
)


def scene_catalog():
    return dict(
        coordinate_frame="scene-local X/Y floor, Z up; positions and sizes in metres",
        objects=[dict(id=k, name=v[0], default_size_m=v[1]) for k, v in OBJECTS.items()],
        atmospheres=list(ATMOSPHERES),
        provenance="Authored staging proxies, not a reconstruction or measured venue",
    )


def scene_properties():
    from .creative import array, obj, string

    coordinate = dict(type="number", minimum=-100, maximum=100)
    position = dict(type="array", items=coordinate, minItems=3, maxItems=3)
    size = dict(type="array", items=dict(type="number", minimum=0.02, maximum=30), minItems=3, maxItems=3)
    return dict(
        space_id=string(40),
        atmosphere=dict(type="string", enum=list(ATMOSPHERES)),
        location_notes=string(1200),
        objects=array(
            obj(
                object_id=string(40),
                asset_id=dict(type="string", enum=list(OBJECTS)),
                label=dict(type="string", minLength=0, maxLength=120),
                position_m=position,
                size_m=size,
                yaw_rad=dict(type="number", minimum=-math.tau, maximum=math.tau),
            ),
            0,
            30,
        ),
        cast=array(
            obj(
                actor_id=string(40),
                offset_m=position,
                facing_rad=dict(type="number", minimum=-math.tau, maximum=math.tau),
                motion=dict(type="string", enum=["hold", "with_lead"]),
            ),
            0,
            5,
        ),
    )


def shot_properties():
    from .creative import obj, string

    return dict(
        transition=dict(type="string", enum=["cut", "reposition"]),
        camera_target=obj(kind=dict(type="string", enum=["actor", "object"]), target_id=string(40)),
        tracking=obj(
            cart=dict(type="string", enum=["planned", "follow_actor"]),
            phone=dict(type="string", enum=["planned", "follow_head"]),
            on_loss=dict(type="string", enum=["stop_and_hold"]),
            reason=string(400),
        ),
        audio_intent=string(800),
        capture=obj(
            take_id=dict(type="string", minLength=0, maxLength=40),
            in_s=dict(type="number", minimum=0, maximum=600),
        ),
    )


def tracking_intent(shot):
    """Infer old-script intent from structured movement, never from loose prose."""
    from takeone.previs.templates import BY_ID

    movement = shot.get("movement", {})
    template = BY_ID.get(movement.get("template_id"), {})
    actor_target = shot.get("camera_target", {}).get("kind", "actor") == "actor"
    positions = movement.get("cinematography", {}).get("channels", {}).get("actor_position_m", [])
    walking = movement.get("subject_motion") == "walk" or any(
        a["value"] != b["value"] for a, b in zip(positions, positions[1:])
    )
    cart = actor_target and walking and template.get("route") in ("follow", "lead", "side")
    phone = actor_target and walking and template.get("aim") in ("face", "dolly_zoom")
    intent = shot.get("tracking") or dict(
        cart="follow_actor" if cart else "planned",
        phone="follow_head" if phone else "planned",
        on_loss="stop_and_hold",
        reason="Follow the selected walking actor."
        if cart or phone
        else "Play the authored camera movement.",
    )
    return copy.deepcopy(intent)


def tracking_status(intent, actor_id):
    requested = [
        name
        for name, mode in (("cart", "follow_actor"), ("phone", "follow_head"))
        if intent.get(name) == mode
    ]
    return dict(
        **intent,
        actor_id=actor_id,
        preview_source="scripted_actor",
        requested_controllers=requested,
        hooks={
            name: "takeone.director.following.start_" + ("cart_follow" if name == "cart" else "head_follow")
            for name in requested
        },
        live_available=False,
        live_state="integration_required" if requested else "not_requested",
        message="Follow mode selected; rehearsal uses the scripted actor. Live controller connection is pending."
        if requested
        else "Authored camera path and aim.",
    )


def validate_scene_links(document):
    """Reject ambiguous actor/object/space references before they lose their meaning."""
    actors = {a["actor_id"] for a in document["actors"]}
    marks = {m["mark_id"]: m for m in document["marks"]}
    scene_ids = {s["scene_id"] for s in document["scenes"]}
    for mark in marks.values():
        if mark.get("scene_id") and mark["scene_id"] not in scene_ids:
            raise ValueError("A mark references an unknown scene")
    for scene in document["scenes"]:
        objects = {o["object_id"] for o in scene.get("objects", [])}
        if len(objects) != len(scene.get("objects", [])):
            raise ValueError("Object IDs must be unique within a scene")
        cast = [c["actor_id"] for c in scene.get("cast", [])]
        if len(cast) != len(set(cast)) or not set(cast) <= actors:
            raise ValueError("Scene cast must reference distinct named actors")
        for shot in scene["shots"]:
            mark = marks.get(shot["mark_id"], {})
            if mark.get("scene_id") and mark["scene_id"] != scene["scene_id"]:
                raise ValueError("A shot must use a mark in its own scene")
            target = shot.get("camera_target")
            if target:
                if target["kind"] == "object" and target["target_id"] not in objects:
                    raise ValueError("Camera target must reference an object in this scene")
                if target["kind"] == "actor" and target["target_id"] != shot["actor_id"]:
                    raise ValueError("The tracked camera actor must match the shot actor")
            intent = tracking_intent(shot)
            if (
                target
                and target["kind"] == "object"
                and (intent["cart"] == "follow_actor" or intent["phone"] == "follow_head")
            ):
                raise ValueError("Object reveals cannot enable actor or head following")
            if intent["cart"] == "follow_actor" and shot.get("movement", {}).get("subject_motion") != "walk":
                raise ValueError("Cart following requires a walking actor")
