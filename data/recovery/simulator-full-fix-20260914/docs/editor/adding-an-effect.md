# Adding an effect

Two files for a primitive, one for a look. You should not need to read anything else.

## A primitive

**1. Declare it** in `packages/takeone/editor/effects/primitives.py`:

```python
_spec("light_leak", "Light leak", "film",
      [P("intensity", "unit", False, default=0.3),
       P("angle", "number", False, -180.0, 180.0, default=35.0)],
      "A warm diagonal leak across the frame.", ("film", "texture")),
```

`P` is `ParamSpec(name, kind, required, minimum, maximum, choices=(), default=None)`. Kinds:
`slug` `text` `int` `number` `seconds` `unit` `bool` `enum` `mapping` `list` `curve` `object`.
Give every optional parameter a default; a parameter with neither `required` nor a default is
a parameter that can be absent in ways the compiler has to guess about.

**2. Compile it** in `packages/takeone/editor/render/ffmpeg.py`:

```python
def _f_light_leak(p, ins, out):
    intensity = _number(p.get("intensity", 0.3))
    angle = _number(p.get("angle", 35.0), 2)
    return f"{ins[0]}gradients=...,blend=all_mode=screen:all_opacity={intensity}{out}"

PRIMITIVE_FILTERS["light_leak"] = _f_light_leak
```

A fragment receives the label(s) of its input(s) and the label it must produce, and returns a
complete filter-graph expression. Simple primitives are one statement. A primitive that needs
an internal split and merge returns several statements separated by `;`, using labels derived
from the node id — add its id to `MULTI_STAGE` so it receives that key. Format every number
through `_number`; never interpolate a raw float.

If the filter you reach for is not in `REQUIRED_FILTERS`, add it there too, so a build that
lacks it is reported by name at startup rather than failing mid-render.

**3. That is it.** The registry test will fail if you did step 1 without step 2, or the
reverse. Effects are addressable immediately:

```python
EFFECTS.latest("light_leak").build((upstream_id,), {"intensity": 0.4})
```

## A look

One file: `packages/takeone/editor/effects/looks.py`.

```python
def _golden_hour(intensity, values):
    return [
        ("temperature", {"kelvin": _mix(6500.0, 5100.0, intensity), "mix": 1.0}),
        ("tone_curve", {"shadows": -0.05 * intensity, "highlights": 0.07 * intensity}),
        ("bloom", {"threshold": 0.8, "radius": 18.0, "intensity": 0.2 * intensity}),
        ("film_grain", {"intensity": 5.0 * intensity}),
    ]

LOOKS = (
    ...,
    _look("golden_hour", "Golden hour", "Low warm sun, soft highlights.",
          _golden_hour, ("natural", "warm")),
)
```

`_mix(identity, value, intensity)` interpolates from the no-op value, which is what makes
`intensity: 0` a valid chain. Return steps in the order a colourist would apply them:
technical before creative, texture last.

## Versioning

Changing what an effect *does* means bumping its `version`. Every node id downstream changes,
which invalidates exactly the cached artifacts that are now wrong. Leaving the version alone
while changing the compilation will serve stale frames — this is the one way to do that, so
it is the one rule worth remembering.

Adding a new optional parameter with a default that reproduces the old behaviour does not
need a bump: the compiled output for existing projects is unchanged, and the content address
is computed from the validated parameters, which now include the default.
