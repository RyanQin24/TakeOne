# The effect system

A **primitive** is the smallest unit the render backend knows how to execute. A **look** is a
named composition of primitives with one intensity control. A **transition** is an effect
with two inputs — a whip, a flash and a crossfade are all "consume N inputs over a time
range, emit one output". `EffectSpec.arity` is `1` or `2`; that is the whole difference.

These are compiled to FFmpeg filters the editor owns. They are not wrappers around another
AI video product.

## The primitives

| Category | Primitives |
| --- | --- |
| Tone and colour | `exposure` `contrast` `saturation` `temperature` `tint` `lift` `tone_curve` `lut3d` `hue_shift` `vibrance` `brightness` `gamma` `shadows` `highlights` |
| Film | `bloom` `glow` `film_grain` `vignette` `halation` `letterbox` `fade` `light_leak` `analog` |
| Dynamic | `rgb_split` `chromatic_aberration` `pixelate` `spectrum_scan` `motion_blur` `camera_shake` `ghost` `prism` |
| Transform | `flip_horizontal` `flip_vertical` `rotate` `zoom` `mirror` |
| Stylise | `sharpen` `gaussian_blur` `invert` `sepia` `colorize` `posterize` `edge_detect` `scanlines` `denoise` `box_blur` `chroma_key` |

Each declares an id, a version, a category, and a typed parameter schema with ranges and
defaults. `EffectSpec.validate` fills defaults and refuses unknown or out-of-range
parameters — it never silently clamps, because a clamped parameter is a decision nobody
made.

## The looks

`luxury_warm` · `noir_contrast` · `teal_orange` · `dream_reveal` · `action_impact` ·
`spectrum_entrance` · `clean_natural` · `mono_film` · `night_cool` · `golden_hour` ·
`bleach_bypass` · `vintage` · `cyberpunk` · `kodak_portra` · `fuji_eterna` · `vhs_tape` ·
`pastel` · `high_key`

A look compiles to the same primitive chain a colourist would have built by hand. Intensity
interpolates each parameter from identity toward its full value, so `intensity: 0` is a
valid no-op chain and `intensity: 1` is the look as designed.

## The transitions

Crossfade, dip to black, flash, whip, match cut, directional wipes and slides, iris open
and close, pixelize, radial, zoom through, smooth wipes, cover and reveal, diagonal,
squeeze, fade through grey, distance, and barn-door opens.

The compiler computes each transition's `offset_s` from the accumulated programme duration,
so `xfade` lands on the exact frames the timeline says. The mode is checked against an
allowlist; an unknown mode is refused rather than passed through.

## The registry

One `EffectRegistry`, populated by explicit `install(registry)` calls at import of the
library modules. Registering a duplicate `(id, version)` raises immediately.

Two tests keep the registry and the backend honest:

- every registered primitive has an FFmpeg fragment,
- every FFmpeg fragment belongs to a registered primitive,
- default fragments stay inside the filter-graph character allowlist.

## Local media

Each project owns `data/editor/library/{project_id}/media/`. Dropping a clip in the
interface uploads it there, probes it, and places it on the timeline. The same bytes are
the same media; a second drop of that file reuses the import and can still place another
clip.
