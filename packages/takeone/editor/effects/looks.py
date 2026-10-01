"""Creative looks: named compositions of primitives, scaled by one intensity control.

A look is not a new kind of thing. It compiles to the same primitive nodes a colourist
would have chained by hand, which is why the decision inspector can show exactly what a
look did and why the renderer needs no special case for it.
"""

from ..operations import ParamSpec as P
from .registry import EFFECTS
from .spec import EffectSpec

INTENSITY = P("intensity", "unit", False, default=1.0)


def _mix(identity, value, intensity):
    return identity + (value - identity) * intensity


def _chain(inputs, steps, time_range, metadata):
    """Compile an ordered list of `(primitive_id, parameters)` into a linear node chain."""
    nodes = []
    current = inputs[0]
    for primitive_id, parameters in steps:
        spec = EFFECTS.latest(primitive_id)
        built, current = spec.build((current,), parameters, time_range, metadata)
        nodes.extend(built)
    return tuple(nodes), current


def _look(identifier, name, description, steps_for, tags=(), extra=()):
    def compile_look(spec, inputs, values, time_range, metadata):
        intensity = values.get("intensity", 1.0)
        steps = steps_for(intensity, values)
        if not steps:
            raise ValueError(f"Look '{identifier}' produced no steps")
        return _chain(inputs, steps, time_range, {**metadata, "look": identifier})

    return EffectSpec(
        id=identifier,
        version=1,
        name=name,
        category="color",
        parameters=(INTENSITY,) + tuple(extra),
        arity=1,
        primitive=False,
        compile=compile_look,
        description=description,
        tags=("look",) + tuple(tags),
    )


def _luxury_warm(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 5400.0, intensity), "mix": 1.0}),
        ("tone_curve", {"shadows": -0.06 * intensity, "highlights": 0.05 * intensity}),
        ("contrast", {"amount": _mix(1.0, 1.12, intensity)}),
        ("saturation", {"amount": _mix(1.0, 0.94, intensity)}),
        ("bloom", {"threshold": 0.78, "radius": 16.0, "intensity": 0.22 * intensity}),
        ("vignette", {"intensity": 0.30 * intensity}),
        ("film_grain", {"intensity": 6.0 * intensity}),
    ]


def _noir(intensity, values):
    return [
        ("saturation", {"amount": _mix(1.0, 0.08, intensity)}),
        ("contrast", {"amount": _mix(1.0, 1.45, intensity)}),
        ("tone_curve", {"shadows": -0.14 * intensity, "highlights": 0.08 * intensity}),
        ("film_grain", {"intensity": 14.0 * intensity}),
        ("vignette", {"intensity": 0.45 * intensity}),
    ]


def _teal_orange(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 7400.0, intensity), "mix": 0.6}),
        ("tint", {"amount": -0.10 * intensity}),
        ("tone_curve", {"shadows": -0.10 * intensity, "highlights": 0.06 * intensity}),
        ("vibrance", {"amount": 0.45 * intensity}),
        ("contrast", {"amount": _mix(1.0, 1.18, intensity)}),
    ]


def _dream_reveal(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 5200.0, intensity), "mix": 0.8}),
        ("bloom", {"threshold": 0.62, "radius": 26.0, "intensity": 0.55 * intensity}),
        ("glow", {"radius": 14.0, "intensity": 0.28 * intensity}),
        ("lift", {"amount": 0.05 * intensity}),
        ("saturation", {"amount": _mix(1.0, 1.1, intensity)}),
    ]


def _action_impact(intensity, values):
    return [
        ("contrast", {"amount": _mix(1.0, 1.25, intensity)}),
        ("motion_blur", {"frames": 3 if intensity > 0.4 else 2}),
        ("rgb_split", {"amount": 6.0 * intensity, "angle": 0.0}),
        ("camera_shake", {"amplitude": 10.0 * intensity, "frequency": 7.0}),
        ("saturation", {"amount": _mix(1.0, 1.15, intensity)}),
    ]


def _spectrum_entrance(intensity, values):
    return [
        (
            "spectrum_scan",
            {
                "width": 0.14,
                "degrees": 140.0 * intensity,
                "speed": values.get("speed", 1.0),
                "direction": values.get("direction", "left_to_right"),
            },
        ),
        ("rgb_split", {"amount": 5.0 * intensity, "angle": 0.0}),
        ("pixelate", {"size": max(2, int(8 * intensity) + 2)}),
        ("glow", {"radius": 12.0, "intensity": 0.34 * intensity}),
        ("contrast", {"amount": _mix(1.0, 1.1, intensity)}),
    ]


def _clean_natural(intensity, values):
    return [
        ("contrast", {"amount": _mix(1.0, 1.06, intensity)}),
        ("vibrance", {"amount": 0.18 * intensity}),
        ("sharpen", {"amount": 0.5 * intensity}),
    ]


def _mono_film(intensity, values):
    return [
        ("saturation", {"amount": _mix(1.0, 0.0, intensity)}),
        ("tone_curve", {"shadows": -0.08 * intensity, "midtones": 0.04 * intensity}),
        ("film_grain", {"intensity": 18.0 * intensity}),
        ("vignette", {"intensity": 0.38 * intensity}),
    ]


def _night_cool(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 8200.0, intensity), "mix": 0.9}),
        ("lift", {"amount": 0.04 * intensity}),
        ("contrast", {"amount": _mix(1.0, 1.2, intensity)}),
        ("saturation", {"amount": _mix(1.0, 0.85, intensity)}),
        ("halation", {"threshold": 0.8, "radius": 20.0, "intensity": 0.22 * intensity}),
    ]


def _golden_hour(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 4800.0, intensity), "mix": 1.0}),
        ("tone_curve", {"shadows": -0.04 * intensity, "highlights": 0.08 * intensity}),
        ("bloom", {"threshold": 0.7, "radius": 20.0, "intensity": 0.28 * intensity}),
        ("saturation", {"amount": _mix(1.0, 1.08, intensity)}),
        ("vignette", {"intensity": 0.18 * intensity}),
    ]


def _bleach_bypass(intensity, values):
    return [
        ("saturation", {"amount": _mix(1.0, 0.35, intensity)}),
        ("contrast", {"amount": _mix(1.0, 1.4, intensity)}),
        ("sharpen", {"amount": 0.7 * intensity}),
        ("tone_curve", {"shadows": -0.08 * intensity, "highlights": 0.06 * intensity}),
        ("film_grain", {"intensity": 8.0 * intensity}),
    ]


def _vintage(intensity, values):
    return [
        ("sepia", {"amount": 0.7 * intensity}),
        ("vignette", {"intensity": 0.4 * intensity}),
        ("film_grain", {"intensity": 12.0 * intensity}),
        ("tone_curve", {"midtones": 0.05 * intensity, "highlights": -0.04 * intensity}),
    ]


def _cyberpunk(intensity, values):
    return [
        ("hue_shift", {"degrees": 18.0 * intensity}),
        ("contrast", {"amount": _mix(1.0, 1.22, intensity)}),
        ("rgb_split", {"amount": 5.0 * intensity, "angle": 12.0}),
        ("glow", {"radius": 10.0, "intensity": 0.3 * intensity}),
        ("saturation", {"amount": _mix(1.0, 1.2, intensity)}),
    ]


def _kodak_portra(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 5600.0, intensity), "mix": 0.85}),
        ("saturation", {"amount": _mix(1.0, 0.92, intensity)}),
        ("lift", {"amount": 0.03 * intensity}),
        ("tone_curve", {"shadows": 0.03 * intensity, "highlights": 0.04 * intensity}),
        ("film_grain", {"intensity": 5.0 * intensity}),
    ]


def _fuji_eterna(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 7200.0, intensity), "mix": 0.7}),
        ("lift", {"amount": 0.04 * intensity}),
        ("saturation", {"amount": _mix(1.0, 0.88, intensity)}),
        ("contrast", {"amount": _mix(1.0, 0.96, intensity)}),
        ("halation", {"threshold": 0.82, "radius": 16.0, "intensity": 0.16 * intensity}),
    ]


def _vhs_tape(intensity, values):
    return [
        ("scanlines", {"intensity": 0.5 * intensity, "spacing": 3}),
        ("rgb_split", {"amount": 3.0 * intensity, "angle": 0.0}),
        ("hue_shift", {"degrees": -8.0 * intensity}),
        ("saturation", {"amount": _mix(1.0, 0.8, intensity)}),
        ("film_grain", {"intensity": 16.0 * intensity}),
        ("vignette", {"intensity": 0.28 * intensity}),
    ]


def _pastel(intensity, values):
    return [
        ("lift", {"amount": 0.07 * intensity}),
        ("contrast", {"amount": _mix(1.0, 0.9, intensity)}),
        ("saturation", {"amount": _mix(1.0, 0.78, intensity)}),
        ("glow", {"radius": 12.0, "intensity": 0.22 * intensity}),
        ("temperature", {"kelvin": _mix(6500.0, 6000.0, intensity), "mix": 0.5}),
    ]


def _high_key(intensity, values):
    return [
        ("exposure", {"stops": 0.55 * intensity}),
        ("lift", {"amount": 0.08 * intensity}),
        ("contrast", {"amount": _mix(1.0, 0.88, intensity)}),
        ("highlights", {"amount": 0.12 * intensity}),
    ]


LOOKS = (
    _look(
        "luxury_warm",
        "Luxury warm",
        "Restrained warmth, soft bloom, gentle vignette.",
        _luxury_warm,
        ("premium", "commercial"),
    ),
    _look("noir_contrast", "Noir", "Crushed blacks, near-monochrome, heavy grain.", _noir, ("dramatic",)),
    _look(
        "teal_orange",
        "Teal and orange",
        "Cool shadows, warm skin, blockbuster contrast.",
        _teal_orange,
        ("commercial",),
    ),
    _look(
        "dream_reveal",
        "Dream reveal",
        "Lifted blacks, strong bloom, soft highlights.",
        _dream_reveal,
        ("soft", "reveal"),
    ),
    _look(
        "action_impact",
        "Action impact",
        "Contrast, motion blur, split and shake.",
        _action_impact,
        ("action",),
    ),
    _look(
        "spectrum_entrance",
        "Spectrum entrance",
        "A hue band sweeps the frame on entry.",
        _spectrum_entrance,
        ("signature", "entrance"),
        extra=(
            P("speed", "number", False, 0.05, 8.0, default=1.0),
            P(
                "direction",
                "enum",
                False,
                choices=("left_to_right", "right_to_left"),
                default="left_to_right",
            ),
        ),
    ),
    _look(
        "clean_natural", "Clean natural", "Minimal correction, honest colour.", _clean_natural, ("natural",)
    ),
    _look("mono_film", "Mono film", "Black and white with film texture.", _mono_film, ("dramatic",)),
    _look("night_cool", "Night cool", "Cool, lifted, halated night look.", _night_cool, ("night",)),
    _look(
        "golden_hour",
        "Golden hour",
        "Low sun, amber bloom, open highlights.",
        _golden_hour,
        ("warm", "natural"),
    ),
    _look(
        "bleach_bypass",
        "Bleach bypass",
        "Silver retention: hard contrast, thin colour.",
        _bleach_bypass,
        ("dramatic", "action"),
    ),
    _look("vintage", "Vintage", "Sepia print, grain, and a darkened edge.", _vintage, ("retro", "film")),
    _look(
        "cyberpunk", "Cyberpunk", "Hue twist, glow, and a thin RGB split.", _cyberpunk, ("stylise", "night")
    ),
    _look(
        "kodak_portra", "Kodak Portra", "Soft warm skin, gentle grain.", _kodak_portra, ("film", "portrait")
    ),
    _look(
        "fuji_eterna",
        "Fuji Eterna",
        "Cool lift, pastel mids, faint halation.",
        _fuji_eterna,
        ("film", "soft"),
    ),
    _look("vhs_tape", "VHS tape", "Scanlines, drift, and tape grain.", _vhs_tape, ("retro", "glitch")),
    _look("pastel", "Pastel", "Lifted, desaturated, softly glowing.", _pastel, ("soft", "fashion")),
    _look("high_key", "High key", "Bright, open, almost shadowless.", _high_key, ("commercial", "beauty")),
)


def install(registry):
    for spec in LOOKS:
        registry.register(spec)
    return registry
