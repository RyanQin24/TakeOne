"""One validated boundary between the web request and the motion planner."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from takeone.config import LIGHT_TYPES, finite, rig_config, shot_defaults

NUMERIC_LIMITS = MappingProxyType(
    {
        "radius": (0.8, 2.5),
        "orbit": (10, 70),
        "duration": (2, 60),
        "dollyOffset": (-2.0, 2.0),
        "actorHeight": (1.3, 1.95),
        "turn": (20, 120),
        "cameraHeight": (0.6, 1.8),
        "trackWidth": (0.52, 0.9),
        "minimumSpeed": (0.02, 0.5),
        "responseTime": (0.0, 2.0),
        "brakeTime": (0.0, 3.0),
        "armTravel": (0.0, 0.3),
        "armLift": (0.0, 0.12),
        "lightTravel": (0.0, 0.3),
        "lightLift": (0.0, 0.12),
    }
)
CHOICES = MappingProxyType({"lightType": LIGHT_TYPES, "driveProfile": ("arms", "smooth", "constant")})


def _defaults() -> dict:
    settings = shot_defaults()
    cart = rig_config()["cart"]
    settings.update(trackWidth=cart["track_width_m"], minimumSpeed=cart["minimum_speed_m_s"])
    return settings


DEFAULTS = MappingProxyType(_defaults())
LEGACY_SETTINGS = MappingProxyType(
    dict(
        duration=16.0,
        driveProfile="smooth",
        armTravel=0.0,
        armLift=0.0,
        lightTravel=0.0,
        lightLift=0.0,
    )
)


@dataclass(frozen=True, slots=True)
class ShotSettings:
    """Immutable validated values; units follow the request schema in the docs."""

    values: Mapping[str, float | str]

    def __post_init__(self) -> None:
        expected = set(NUMERIC_LIMITS) | set(CHOICES)
        if set(self.values) != expected:
            raise ValueError("Shot settings must contain exactly the documented fields")
        checked = {}
        for name, value in self.values.items():
            if name in CHOICES:
                if not isinstance(value, str) or value not in CHOICES[name]:
                    raise ValueError(f"{name} must be one of {CHOICES[name]}")
                checked[name] = value
            else:
                number = finite(value, name)
                lower, upper = NUMERIC_LIMITS[name]
                if not lower <= number <= upper:
                    raise ValueError(f"{name} must be between {lower} and {upper}")
                checked[name] = float(number)
        object.__setattr__(self, "values", MappingProxyType(checked))

    @classmethod
    def from_request(cls, request: dict) -> "ShotSettings":
        if not isinstance(request, dict):
            raise ValueError("Shot settings must be an object")
        unknown = set(request) - set(DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown shot settings: {sorted(unknown)}")
        return cls(dict(DEFAULTS) | request)

    def to_dict(self) -> dict:
        return dict(self.values)


def parameters(request: dict) -> dict:
    """HTTP boundary: validate the request and serialize the accepted settings."""
    return ShotSettings.from_request(request).to_dict()
