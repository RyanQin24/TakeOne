"""Optional, explicit motion requirements; no movement is inferred from prose."""

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class MotionRequirements:
    priority: Literal["required", "preferred", "intentionally_static"] = "preferred"
    actor_travel_m: float = 0.0
    cart_travel_m: float = 0.0
    camera_travel_m: float = 0.0
    arm_translation_m: float = 0.0
    arm_rotation_rad: float = 0.0
    simultaneous_s: float = 0.0
    direction: Literal["any", "approach", "retreat", "left", "right", "orbit_ccw", "orbit_cw"] = "any"
    signed_progress_m: float = 0.0
    orbit_rad: float = 0.0
    max_position_error_m: float = 0.03


def defaults():
    return asdict(MotionRequirements())


def schema():
    from .creative import obj

    properties = {key: dict(type="number", minimum=0, maximum=65) for key in defaults()
                  if key not in ("priority", "direction")}
    properties["simultaneous_s"]["maximum"] = 600
    properties["orbit_rad"]["maximum"] = 12.5663706144
    properties["arm_rotation_rad"]["maximum"] = 3.1415926536
    properties["max_position_error_m"].update(minimum=0.001, maximum=0.5)
    return obj(priority=dict(type="string", enum=["required", "preferred", "intentionally_static"]),
               direction=dict(type="string", enum=["any", "approach", "retreat", "left", "right", "orbit_ccw", "orbit_cw"]),
               **properties)


def validate_links(document):
    for scene in document["scenes"]:
        for shot in scene["shots"]:
            value = shot.get("motion_requirements")
            if value is None:
                continue
            requested = any(value[k] > 0 for k in ("actor_travel_m", "cart_travel_m", "camera_travel_m",
                            "arm_translation_m", "arm_rotation_rad", "simultaneous_s", "signed_progress_m", "orbit_rad"))
            camera_requested = any(value[k] > 0 for k in ("cart_travel_m", "camera_travel_m", "arm_translation_m", "arm_rotation_rad", "simultaneous_s", "signed_progress_m", "orbit_rad"))
            if value["priority"] == "intentionally_static" and camera_requested:
                raise ValueError("An intentionally static camera contract cannot require movement. Author a moving revision instead.")
            if value["priority"] == "required" and not requested:
                raise ValueError("Required movement needs at least one numerical movement threshold.")
            if value["signed_progress_m"] > 0 and value["direction"] not in ("approach", "retreat", "left", "right"):
                raise ValueError("Signed travel requires an approach, retreat, left or right direction.")
            if value["orbit_rad"] > 0 and value["direction"] not in ("orbit_ccw", "orbit_cw"):
                raise ValueError("Orbital travel requires an explicit clockwise or counterclockwise direction.")
            if value["simultaneous_s"] and not shot["actor_id"]:
                raise ValueError("Simultaneous actor/cart/arm motion needs a named actor.")
            if value["simultaneous_s"] > (shot["end_ms"] - shot["start_ms"]) / 1000:
                raise ValueError("Required simultaneous movement must fit the edited shot.")


def catalog():
    return dict(defaults=defaults(), schema=schema(),
                coordinates="Travel is measured in the fixed shot/scene frame; arm pose is relative to the chassis.",
                timing="Requirements apply inside this edit's retained source window, never setup or discarded footage.",
                policy="Required failures remain needs_revision; preferred goals are advisory. No automatic actor, lens or timing changes.",
                simultaneity="Actor locomotion, powered-axle travel and relative phone optical motion overlap in sampled 0.4 s bins. "
                "Independent total excursions reject tiny jitter. Eye/facial quality, dynamics and live tracking are not established.")
