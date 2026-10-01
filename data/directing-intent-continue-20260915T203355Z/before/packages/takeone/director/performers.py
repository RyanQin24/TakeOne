"""Explicit actor appearance and attention. No inference from prose or device IO."""

import math
import re

PALETTE = dict(cloth="#c07b54", pants="#334945", skin="#cfa783", hair="#382f27", shoe="#e2dcc7")
GESTURES = ("idle", "invite", "reach")
TARGET_KINDS = ("actor", "object", "point", "forward")


def appearance_schema():
    from .creative import obj, string

    return obj(**{name: string(7) for name in PALETTE})


def performance_schema():
    from .creative import array, obj, string

    at = dict(type="number", minimum=0, maximum=1)
    angle = dict(type="number", minimum=-math.tau, maximum=math.tau)
    ease = dict(type="string", enum=["smooth", "linear", "hold"])
    point = array(dict(type="number", minimum=-100, maximum=100), 3, 3)
    target = dict(
        kind=dict(type="string", enum=list(TARGET_KINDS)),
        target_id=dict(type="string", minLength=0, maxLength=40),
        point_m=point,
    )
    return array(
        obj(
            actor_id=string(40),
            body_heading_rad=array(obj(at=at, value=angle, ease=ease), 0, 32),
            look_at=array(obj(at=at, ease=ease, **target), 0, 32),
            gestures=array(
                obj(at=at, ease=ease, name=dict(type="string", enum=list(GESTURES)),
                    weight=dict(type="number", minimum=0, maximum=1), **target),
                0, 32,
            ),
        ),
        0, 6,
    )


def ordered(keys, label):
    if not keys:
        return
    if len(keys) < 2 or keys[0]["at"] != 0 or keys[-1]["at"] != 1:
        raise ValueError(f"{label} needs keys at full-take 0 and 1.")
    if any(b["at"] <= a["at"] for a, b in zip(keys, keys[1:])):
        raise ValueError(f"{label} key times must increase strictly.")


def validate_links(document):
    """Called after the existing schema boundary validates shapes and finite values."""
    for actor in document["actors"]:
        for color in actor.get("appearance", {}).values():
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Actor appearance colors must be six-digit #RRGGBB values.")
    takes = {}
    for scene in document["scenes"]:
        objects = {o["object_id"] for o in scene.get("objects", [])}
        cast = {m["actor_id"] for m in scene.get("cast", [])}
        for shot in scene["shots"]:
            tracks = shot.get("performers", [])
            if not tracks:
                continue
            if "space_id" not in scene:
                raise ValueError("Named attention needs an explicit scene-local coordinate frame.")
            available = cast | ({shot["actor_id"]} if shot["actor_id"] else set())
            ids = [t["actor_id"] for t in tracks]
            if len(ids) != len(set(ids)) or not set(ids) <= available:
                raise ValueError("Performer tracks must name distinct people staged in this shot.")
            for track in tracks:
                for field in ("body_heading_rad", "look_at", "gestures"):
                    ordered(track[field], field)
                for key in track["look_at"] + track["gestures"]:
                    kind, target = key["kind"], key["target_id"]
                    if kind == "actor" and (target not in available or target == track["actor_id"]):
                        raise ValueError("Look targets must name another actor staged in this shot.")
                    if kind == "object" and target not in objects:
                        raise ValueError("Look targets must name an object in this scene.")
                    if kind in ("point", "forward") and target:
                        raise ValueError("Point/forward targets use an empty target_id.")
                for key in track["gestures"]:
                    if key["name"] == "reach" and key["kind"] not in ("object", "point"):
                        raise ValueError("A reach needs an object or a scene-local point target.")
            take_id = shot.get("capture", {}).get("take_id")
            if take_id:
                if take_id in takes and takes[take_id] != tracks:
                    raise ValueError("Shared-take clips must preserve the same full-take performer tracks.")
                takes[take_id] = tracks


def catalog():
    return dict(
        coordinate_frame="Targets use scene-local XYZ metres, Z up. Body headings use scene axes.",
        timebase="Full-take filming fraction 0..1, excluding setup; never renormalized per edit clip.",
        gestures=list(GESTURES),
        target_kinds=list(TARGET_KINDS),
        scope="Persistent authored wardrobe and independent body/head direction on staging proxies. "
              "Eyes move with the head; facial acting and eye-only saccades are not simulated. "
              "A reach moves an arm proxy, not an object. No prop transfer or grasp is implied.",
    )
