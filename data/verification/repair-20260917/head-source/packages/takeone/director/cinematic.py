"""Provider/editor wire contract for the simulator's independent channels."""

import copy

from takeone.previs.camera import validate_camera
from takeone.previs.channels import CHANNELS, validate_breath, validate_channels, validate_texture


def wire_settings(value):
    """Fill the strict provider shape; empty tracks retain legacy/preset behavior."""
    from takeone.previs.templates import validate_settings

    s = validate_settings(value)
    return dict(
        channels={name: copy.deepcopy(s["channels"].get(name, [])) for name in CHANNELS},
        texture=s["texture"],
        breath=s["breath"],
        camera=s["camera"],
    )


def schema(require_performance=False):
    from .creative import array, obj

    ease = dict(type="string", enum=["smooth", "linear", "hold"])
    at = dict(type="number", minimum=0, maximum=1)
    channels = {}
    for name, spec in CHANNELS.items():
        scalar = dict(type="number", minimum=spec.minimum, maximum=spec.maximum)
        value = scalar if spec.dimensions == 1 else array(scalar, 3, 3)
        channels[name] = array(obj(at=at, value=value, ease=ease), 0, 32)
    tracks = obj(**channels)
    if not require_performance:
        tracks["required"] = [
            name
            for name in channels
            if name not in (
                "actor_position_m", "actor_heading_rad", "gaze_yaw_rad", "gaze_pitch_rad",
                "camera_position_m", "light_position_m"
            )
        ]
    return obj(
        channels=tracks,
        texture=obj(
            enabled=dict(type="boolean"),
            amplitude_rad=dict(type="number", minimum=0, maximum=0.0872664626),
            frequency_hz=dict(type="number", minimum=0.1, maximum=1),
        ),
        breath=obj(
            **{
                k: dict(type="number", minimum=0, maximum=10)
                for k in ("pre_hold_s", "post_hold_s", "entry_s", "exit_s")
            }
        ),
        camera=obj(
            horizon=dict(type="string", enum=["auto", "level", "phone"]),
            zoom=dict(type="string", enum=["preset", "fixed", "keyframes", "dolly"]),
            keyframes=array(
                obj(at=at, focal_mm=dict(type="number", minimum=13, maximum=360), ease=ease), 0, 32
            ),
        ),
    )


def settings(value):
    from .creative import validate

    validate(value, schema(), "cinematography")
    value = copy.deepcopy(value)
    return dict(
        channels=validate_channels({k: v for k, v in value["channels"].items() if v}),
        texture=validate_texture(value["texture"]),
        breath=validate_breath(value["breath"]),
        camera=validate_camera(value["camera"]),
    )
