# 03 — Script to simulator: design of record

Status: **built on `feat/script-to-simulator`, 14 September 2026.** The outcome, the deviations
from this design and the verification evidence are in
[`implementation/03-timeline-previs.md`](implementation/03-timeline-previs.md); read that
alongside this. Sections 5, 8 and 11 below describe the plan, not in every case the shipped
shape — the implementation record lists the six places they differ and why.

One rule overrides everything in this document where they conflict: **nothing added may refuse a
shot the rig can already perform.** Section 5 marks `duration_mismatch` and `dolly_zoom_invalid`
as errors that block a shot; they ship as advisory. Only refusals the compiler already made
before this package are blocking.

Scope decisions taken with the owner on 14 September 2026:

| Decision | Choice |
|---|---|
| Rehearsal continuity | **One continuous set.** Every script mark has a floor position; the simulator drives a real reposition between shots. Flat floor only — no scene geometry (stairs, street) in this package. |
| Sequence player location | **Extend the existing studio** (`index.html` / `orbit.js`) with a fourth mode. No new page. |
| Bad shots | **Bounded auto-repair.** Failing shots go back to `gpt-5.6-luna` with the exact structured diagnostic, at most two attempts, then deterministic re-validation. |

---

## 1. What already exists

This matters because roughly half of the bridge is already built and the plan must not rebuild it.

### The simulator's parameter space is already canonical

`packages/takeone/previs/templates.py` defines **28 presets across 6 families**, each one a
`route` × `aim` composition:

```
route:  hold  in  out  truck  follow  lead  side  arc
aim:    face  locked  pan  tilt  zoom  dolly_zoom  roll  high  handheld
```

and **19 numeric parameters** in `FIELDS`, each with an SI range, a step and a display scale:

| Parameter | Meaning | Range |
|---|---|---|
| `radius_m` | actor-to-cart distance | 0.8 – 10 m |
| `bearing_rad` | starting position angle around the actor | ±360° |
| `sweep_rad` | arc travelled | 15 – 360° |
| `speed_m_s` | cart pace | 0.14 – 0.35 m/s |
| `distance_m` | cart travel along a straight route | 0.2 – 10 m |
| `duration_s` | shot duration (stationary routes only) | 2 – 120 s |
| `angle_rad` | pan / tilt / roll / high-angle change | 1 – 90° |
| `height_start_m`, `height_end_m` | camera optical height | 0.7 – 1.8 m |
| `rise_start`, `rise_end` | when the change happens, as a fraction of filming time | 0 – 1 |
| `focal_end_mm` | ending focal length | 13 – 360 mm |
| `actor_distance_m`, `actor_heading_rad` | scripted actor walk | 0.2 – 10 m, ±360° |
| `subject_height_m` | actor height | 0.8 – 2.2 m |
| `light_height_start_m`, `light_height_end_m` | light arm height | 0.7 – 1.8 m |
| `hand_amplitude_rad`, `hand_frequency_hz` | handheld drift | 0.1 – 5°, 0.1 – 1 Hz |

plus `focal_mm` (13 – 360) and a `camera` object (`horizon`, `zoom`, `keyframes[]`).

**This is exactly the "constant parameter" vector in the original ask** — distance, angle, speed,
cart travel — and it already exists, already has bounds, and already has a validator.
`catalog()` advertises per template which subset of those parameters is live.

### The translation layer is already written

`packages/takeone/director/studio.py` (written 14 September) has:

- `movement_catalog()` — the live catalog, trimmed, handed to the model as authority
- `movement_schema()` — a **strict JSON Schema generated from the catalog**, so template IDs and
  parameter names are enumerated from the same source the simulator validates against
- `shot_settings(shot)` — the deterministic translator: movement object → validated settings,
  plus the list of parameters that fell back to defaults
- `rehearsal_manifest(detail, digest)` — whole script → per-shot settings

`director/api.py` serves it at `GET /api/director/studio/{session_id}/{document_digest}`.

`director/provider.py` already targets `gpt-5.6-luna` with `reasoning_effort: max`, OpenAI
Responses, `strict: true` structured output, and injects `robot-film-director/SKILL.md` into the
instructions with its digest recorded in provenance.

### What is actually missing

1. **Nothing consumes the manifest.** `director.js` never fetches the studio endpoint and never
   renders the `movement` object. `orbit.js` has no concept of more than one shot.
2. **No sequencer.** One `preview`, one clock, one scrubber. A script is N shots.
3. **No set.** Every shot places its actor at the shot-local origin. `marks` in the script are
   free text with no coordinates, so there is no "where in the room" and no way to drive between
   setups. Package 03's acceptance explicitly requires that *"a shot cut cannot teleport the rig
   to its next setup."*
4. **No feedback path.** A shot that fails `validate_settings`, or that compiles with a 6° aiming
   error, produces a string in a list. Nothing goes back to the model.
5. **`framing` is decorative.** The script schema has `framing: wide | medium | close_up`, and it
   is connected to nothing. A shot can declare `close_up` and produce a 2-metre-wide frame.

---

## 2. The answer to "script or agent?"

**Neither alone. The split is the design, and it is already half right.**

- The model chooses **only** `template_id` and `{name, value}` numbers, inside a JSON Schema
  generated from the live catalog and enforced by the provider with `strict: true`. It is
  structurally incapable of emitting an unknown template or an unknown parameter name.
- A **pure function** translates that to simulator settings. No model in the translation path —
  that is what makes it reproducible, cacheable, unit-testable and instant.
- The **simulator** owns feasibility. `validate_settings` → `compile_template` is the only
  authority on whether a shot is real.

The model returns to the loop in exactly one place: **repair**, when the simulator says no. That
is bounded, cheap, and it is the difference between "the AI sometimes writes a shot that works"
and "a generated script is always rehearsable".

Rule to hold: *creative choice is the model's; translation is arithmetic; physics is the
compiler's.* Any time a number would be invented in the translator, it belongs in the catalog
defaults instead.

---

## 3. Architecture

```
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  BRIEF                     title · objective · duration_ms · aspect        │
 │  CONTEXT                   skill_id · audience · tone · facts[]            │
 └────────────────────────────────────┬──────────────────────────────────────┘
                                      │  director/planning.py  action=request_plan
                                      │  provider.py → gpt-5.6-luna, effort=max
                                      │  instructions = INSTRUCTIONS + SKILL.md
                                      │  text.format = json_schema(plan_schema())   ← strict
                                      │  input      = brief + context + movement_catalog()
                                      ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  ScriptDocument                                               [creative]   │
 │    title logline audience tone                                            │
 │    actors[]   marks[] { mark_id, description, position_m, facing_rad } ←NEW│
 │    scenes[] → shots[] {                                                   │
 │        shot_id start_ms end_ms actor_id mark_id action framing            │
 │        primitive camera_intent light_intent edit_intent lines[]           │
 │        movement { template_id, subject_motion, parameters[{name,value}] } │
 │    }                                                                      │
 │  Human-editable in director.html. Digest-addressed. Approval gates.        │
 └────────────────────────────────────┬──────────────────────────────────────┘
                                      │  director/studio.py  shot_settings()
                                      │  PURE · DETERMINISTIC · NO MODEL
                                      ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  RehearsalManifest                                          [translated]  │
 │    shots[] { shot_id, settings, defaulted_parameters[], stage_transform }  │
 │    manifest_digest                                                        │
 └────────────────────────────────────┬──────────────────────────────────────┘
                                      │  previs/sequence.py
                                      │  per shot: compile_template(settings)   ← cached
                                      │  between shots: reposition.py segment
                                      ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  RehearsalProgram                                            [compiled]   │
 │    segments[] { kind: shot|reposition, t0_s, duration_s, preview,         │
 │                 stage_transform, diagnostics[] }                          │
 │    edit_timeline[]   ← from start_ms/end_ms                               │
 │    rehearsal_timeline[] ← what the rig actually takes                     │
 │    program_digest                                                         │
 └───────────┬───────────────────────────────────────────────┬───────────────┘
             │ diagnostics with severity=error|warn          │ ok
             │                                               │
             ▼                                               ▼
 ┌──────────────────────────────┐              ┌─────────────────────────────┐
 │ director/repair.py           │              │ orbit.js  mode='sequence'   │
 │ failing shots only           │              │ shot rail · one global clock│
 │ + exact diagnostics          │              │ world view + phone view     │
 │ + movement_catalog           │              │ per-shot inspector          │
 │ → gpt-5.6-luna, ≤2 attempts  │              └──────────────┬──────────────┘
 │ → re-validate deterministically│                           │ accepted
 └──────────────┬───────────────┘                             ▼
                │ patched movement objects       ┌─────────────────────────────┐
                └────────► back to ScriptDocument│ motion/studio_plan.py       │
                                                 │ (existing) → robot plan     │
                                                 └─────────────────────────────┘
```

Two properties worth naming, because they are what make this cheap:

- **Every stage is content-addressed.** `document_digest` → `manifest_digest` → per-shot
  `digest(settings)` → `program_digest`. Editing one shot invalidates one compile, not the run.
- **A reposition segment has the same shape as a shot preview** — `frames[]` in the existing
  schema. So the front end renders it with the code it already has. The sequencer is a playlist;
  the renderer never learns what a "transition" is.

---

## 4. The three new concepts

### 4.1 Stage transform — how a shot-local take becomes a set

Each shot's preview is computed with the actor at `(0, 0)`. To put N shots in one room, attach a
2-D rigid transform per shot, derived from its mark:

```python
StageTransform = { "origin_m": [x, y], "heading_rad": float }
```

- `origin_m` = `marks[shot.mark_id].position_m` — where the actor stands in set coordinates.
- `heading_rad` is chosen so the actor's staged facing in the set equals `mark.facing_rad`. The
  studio already stages the actor toward the opening camera
  (`actorFigure.stage(atan2(openingCamera.y, openingCamera.x))` in `orbit.js:compile`), so the
  sequencer computes `heading_rad = mark.facing_rad − staged_local_facing` once per shot, at
  compile time, from the compiled preview. No new solver.

The front end applies this as a single `THREE.Group` transform over the rig root, actor, path and
guides. **No recompilation, no change to any preview's contents.** Shot-local geometry stays the
authority; the set is presentation plus reposition input.

Set bounds: ±6 m, matching the studio's existing set pieces at ±5 m. Marks outside it, or closer
together than `radius_m` allows without the cart route overlapping the neighbouring mark, produce
a `warn` diagnostic — not a hard failure, because a hackathon set is not a validated floor plan.

### 4.2 Reposition — the cut that is not a teleport

Between shot *i* and shot *i+1*:

1. **Park the arms.** Both arms return to their exact calibrated integer midpoints —
   `previs/start_pose.initial_counts(mapping)`, the same pose every take already starts from.
   Timing from the existing `aiming_duration(starts, targets)` (2.0 s floor, ≈ π·span/50 s at
   25 °/s, quantised to `ARM_PERIOD = 0.04`).
2. **Drive the cart** from shot *i*'s final world pose to shot *i+1*'s first world pose, both
   obtained by applying the stage transforms. Differential drive with no strafe primitive, so the
   route is **turn-in-place → straight → turn-in-place**, at `speed_m_s` clamped to the cart's
   configured range.
3. The next shot's own preview already opens with `calibrated_start` + `aiming` frames
   (`orbit_start_s`), so **the sequencer adds no aiming logic at all**.

The reposition segment is emitted with `phase: "reposition"`, `source: "simulated"`, and an
explicit note that physical repositioning is an unqualified kinematic estimate — per
`implementation-rules.md`, a preview may never imply physical readiness. It is deliberately
*not* routed through the calibrated wheel-response planner, because presenting an unmeasured
reposition as a motor-command plan would be exactly the kind of claim the rules forbid.

### 4.3 Two timelines, never conflated

This is the subtlest correctness issue in the whole feature and it must be visible in the UI.

- **Edit timeline** — `start_ms` / `end_ms` from the script. What the cut will be.
- **Rehearsal timeline** — what the rig takes: `orbit_start_s` (calibration + aiming) +
  `orbit_duration_s` (filming) per shot, plus repositions.

For `hold` routes the translator already forces `duration_s = (end_ms − start_ms)/1000`, so
filming time matches by construction. **For every moving route it does not**: filming time is
derived from geometry and speed. A 360° orbit at r = 2.5 m and 0.17 m/s takes 92.4 s of filming
whatever the script says; the fastest the cart may legally do it is 44.9 s at 0.35 m/s.

So the sequencer emits both timelines, the shot rail shows both, and a `duration_mismatch`
diagnostic fires when filming time differs from the edit slot by more than 15 % or 0.5 s. That
diagnostic is the single highest-value input to the repair loop.

---

## 5. Diagnostics — the contract between the simulator and the model

One typed record, produced deterministically, consumed by both the UI and the repair prompt.

```python
@dataclass(frozen=True, slots=True)
class Diagnostic:
    shot_id: str
    code: str        # see table
    severity: str    # "error" | "warn"
    message: str     # plain language, shown to the operator
    parameter: str | None      # which field to change
    observed: float | None
    allowed: tuple[float, float] | None
    suggestion: str            # what a revision must satisfy, not a number to copy
```

| Code | Severity | Raised when | Source |
|---|---|---|---|
| `unresolved_movement` | error | `template_id == "unresolved"` | `shot_settings` |
| `unknown_parameter` | error | parameter not advertised for that template | `shot_settings` |
| `out_of_range` | error | value outside `FIELDS[key]` bounds | `validate_settings` |
| `duration_mismatch` | error | filming time vs edit slot > 15 % or 0.5 s | `sequence.py` |
| `aim_unreachable` | warn | `summary.max_aim_error_deg > 3` | `compile_template` notes |
| `height_unreachable` | warn | achieved vs requested camera height > 0.03 m | `compile_template` notes |
| `framing_mismatch` | warn | declared `framing` disagrees with computed frame height | **new**, §6 |
| `mark_out_of_set` | warn | mark outside ±6 m, or routes overlap | `sequence.py` |
| `reposition_long` | warn | reposition > 8 s | `reposition.py` |
| `dolly_zoom_invalid` | error | actor behind the camera during a Dolly Zoom | `apply_camera` |

`error` blocks rehearsal of that shot and triggers repair. `warn` renders amber in the rail, is
included in the repair payload, and does not block.

---

## 6. Framing becomes load-bearing

The pinhole model in `previs/camera.py` and `orbit-player.js:verticalFov` uses a 35 mm-equivalent
frame with a 16:9 crop, so the vertical frame extent is `36 / (16/9) = 20.25 mm`. Therefore:

> **frame height in metres = distance_m × 20.25 / focal_mm**

Independent of actor height — it is simply how much of the world fills the frame vertically at
that distance. `distance_m` is `radius_m` for `hold` and `arc` routes; for `in`/`out` it runs
between `radius_m` and `radius_m + distance_m`, and a `truck` varies to
`hypot(radius_m, distance_m/2)` at its ends. So the check computes the frame height at **both
ends** and requires the declared `framing` to match at least one of them — a push-in legitimately
starts wide and ends medium.

Bands, in metres of subject filling the frame height:

| `framing` | Frame height | What it reads as |
|---|---|---|
| `wide` | 2.2 – 3.4 m | full body with air above and below |
| `medium` | 1.0 – 1.6 m | roughly waist to head |
| `close_up` | 0.40 – 0.70 m | head and shoulders |

Worked values at the real lens presets (13 / 24 / 48 / 100 / 200 mm):

| distance | 13 mm | 24 mm | 48 mm | 100 mm | 200 mm |
|---|---|---|---|---|---|
| 1.2 m | 1.87 | **1.01** medium | **0.51** close | 0.24 | 0.12 |
| 1.5 m | **2.34** wide | **1.27** medium | **0.63** close | 0.30 | 0.15 |
| 2.0 m | **3.12** wide | 1.69 | 0.84 | **0.41** close | 0.20 |
| 2.5 m | 3.89 | 2.11 | **1.05** medium | **0.51** close | 0.25 |
| 3.0 m | 4.67 | **2.53** wide | **1.27** medium | **0.61** close | 0.30 |

`shot_settings` gains a pure `screen_geometry(settings)` helper returning
`{frame_height_start_m, frame_height_end_m, implied_framing}` and raises a `framing_mismatch`
warning when `implied_framing != shot["framing"]`. Ten lines, and it removes an entire class of
scripts that say "close-up" and deliver a wide.

---

## 7. The repair loop

```
compile → diagnostics(severity=error) → repair round 1 → re-validate → compile
                                      → still failing → repair round 2 → re-validate → compile
                                      → still failing → surface to operator, shot marked
                                        unrehearsable, rest of the program still plays
```

Rules, all enforced server-side:

- **Failing shots only.** The payload is the shot objects that failed, their diagnostics, and the
  movement catalog — not the whole script. A 12-shot script with one bad orbit sends one shot.
- **Same strict schema.** Response is an array of `{shot_id, movement}` under the same generated
  `movement_schema()`. The model cannot widen the parameter space in a repair.
- **Never trusted.** Every returned movement goes back through `shot_settings` →
  `validate_settings` → `compile_template`. A repair that fails is a failed repair, not a new
  contract.
- **Bounded and recorded.** `repair_attempts` is a session column, max 2. Attempts, diagnostics
  sent, and the response ID land in provenance alongside the existing planning record.
- **Budget-gated.** Reuses the existing `budget_consent` / `request_budget_microusd` path in
  `planning.py:_start`. No silent spend.
- **Creative fields are frozen.** The repair returns `movement` only. Dialogue, action, intents
  and timings are not re-generated, so a geometry fix cannot quietly rewrite the script.

---

## 8. File-level plan

### `packages/takeone/previs/`

| File | Change | Contents |
|---|---|---|
| `templates.py` | edit | Export `ROUTE_TIME` (route → filming-time formula), `route_filming_time_s(settings)`, `screen_geometry(settings)`. Pure, no new deps. |
| `sequence.py` | **new** ~260 lines | `build_program(manifest) -> RehearsalProgram`. Per-shot compile via cache, stage transforms, segment stitching, both timelines, diagnostics aggregation. No MuJoCo import of its own — it calls `compile_template`. |
| `reposition.py` | **new** ~140 lines | `reposition_segment(from_pose, to_pose, mappings) -> segment`. Turn-drive-turn kinematics + arm park, emitted in the existing frame schema with `phase="reposition"`. Pure. |
| `diagnostics.py` | **new** ~120 lines | `Diagnostic` dataclass, `collect(settings, preview, shot, program_ctx) -> tuple[Diagnostic, ...]`. Pure. |
| `cache.py` | **new** ~70 lines | Disk cache under `data/previs-cache/<digest>.json`, keyed on `digest(settings) + model_hash + calibration_hashes`. Bounded size, LRU eviction. |

### `packages/takeone/director/`

| File | Change | Contents |
|---|---|---|
| `studio.py` | edit | `shot_settings` raises typed `MovementError` instead of `ValueError`. `movement_catalog()` gains `route_time_formulas` and `framing_bands`. `rehearsal_manifest` gains `stage_transform` per shot from marks. |
| `contracts.py` | edit | `Mark` dataclass with `position_m`, `facing_rad`. `RehearsalProgramRef`. |
| `creative.py` | edit | `PLAN_SCHEMA.marks` items gain `position_m` (array of 2 numbers) and `facing_rad`. `repair_schema()`. |
| `repair.py` | **new** ~180 lines | `RepairLoop(provider, repository)`: build payload, call provider, re-validate, patch document, record provenance. |
| `planning.py` | edit | New action `repair_shots`. Attempt counter. Job kind `creative_repair`. |
| `provider.py` | edit | `kind == "creative_repair"` → `repair_schema()`; repair instructions block. |
| `api.py` | edit | `POST /api/previs/sequence` handler delegation; `GET .../studio/.../program`. |
| `robot-film-director/SKILL.md` | **rewrite** | See §9 and the accompanying file. |

### `apps/rehearsal/`

| File | Change | Contents |
|---|---|---|
| `server.py` | edit | Route `POST /api/previs/sequence` through the existing `compile_lock`; it is the expensive path. |
| `dist/sequence-player.js` | **new** ~140 lines | **Pure, no THREE import.** Segment list, `segmentAt(globalTime)`, `localTime(globalTime)`, `boundaries()`, `seekShot(i)`, `advance()`. Directly unit-testable in `node --test`, like `orbit-player.js`. |
| `dist/sequence-client.js` | **new** ~200 lines | Fetch manifest + program, build the shot rail DOM, status chips, progress during compile, per-shot diagnostics popovers, "Repair with AI" button. |
| `dist/stage-transform.js` | **new** ~60 lines | Applies `{origin_m, heading_rad}` to a `THREE.Group`; converts shot-local route points to set coordinates for the overhead path. |
| `dist/orbit.js` | edit ~120 lines | Fourth mode `sequence`. `preview` becomes "the active segment's preview" — `pose()`, `drawReadings()`, `drawJointReadings()`, `cameraGuides()` are untouched. Scrub bar spans the global clock with shot boundary ticks. Deep link `/?script=<session_id>/<digest>`. |
| `dist/index.html` | edit | Shot rail column in the inspector; script picker; dual timecode readout (edit / rehearsal). |
| `dist/orbit.css` | edit | Rail, chips, boundary ticks. |
| `dist/director.js` | edit ~80 lines | Render `movement` on each shot card (template name, the parameters the model chose, which were defaulted). "Rehearse in studio ↗" opens the deep link. Diagnostics badge. |
| `dist/director.css` | edit | Movement block, badges. |

### Tests

Python tests live flat in `tests/` (only `editor/`, `simulation/`, `support/` are subdirectories),
so these follow that convention:

| File | Covers |
|---|---|
| `tests/test_sequence.py` | Determinism (same manifest → same `program_digest`), stage transforms place the actor at the mark's `position_m` and `facing_rad`, segment `t0_s` values are contiguous, repositions are non-zero between different marks and absent when consecutive shots share one. |
| `tests/test_reposition.py` | Turn-drive-turn endpoint accuracy, arm park reaches the exact calibrated integer midpoints, no lateral translation primitive is ever emitted. |
| `tests/test_shot_diagnostics.py` | Each code in §5 fires on a crafted fixture and does not fire on its neighbour. |
| `tests/test_studio_translation.py` | **The drift guard.** For every template in `catalog()`: its own defaults satisfy `movement_schema()`, and `shot_settings` round-trips them back to the same settings. The simulator half of this already exists — `test_movement_library.py::test_every_default_has_a_complete_calibrated_motor_clock_and_aim` compiles all 28 defaults — so this test closes the *director* half and makes catalog↔schema drift impossible to merge. |
| `tests/test_shot_repair.py` | Attempt bound, re-validation of returned movements, refusal and malformed-response handling, creative fields unchanged by a repair. |
| `tests/test_framing_geometry.py` | `screen_geometry` against the table in §6, both ends of `in`/`out`/`truck` routes. |
| `apps/rehearsal/tests/sequence-player.test.mjs` | Boundary seeks (half-open), last-frame clamping, segment indexing across repositions, `advance` with loop. |

Existing suites must stay green: the 13 `.mjs` suites in `apps/rehearsal/tests/` (run by
`npm test` → `node --test tests/*.test.mjs`), the flat Python suite, and root
`scripts/TakeOne.ps1 -Command test`.

**Do not miss:** `apps/rehearsal/package.json` has a `check` script that runs `node --check` on
every module in `dist/` by name. Each of `sequence-player.js`, `sequence-client.js` and
`stage-transform.js` must be added to it, or they are silently unchecked.

---

## 9. The skill

`packages/takeone/director/robot-film-director/SKILL.md` is rewritten, not replaced by a new
mechanism — it is already loaded by `provider.py:skill_text()` and its digest is already recorded
in provenance. The current version is good prose with four gaps that cause most bad output:

1. **No duration arithmetic.** It says "approximate straight travel as distance/speed" but gives
   one worked example. Scripts that overrun their edit slot are the most common failure.
2. **No framing-to-geometry link.** `framing` and `radius_m`/`focal_mm` are chosen independently.
3. **No worked shot object.** The model is told the shape but never shown one.
4. **No rejection examples.** It is told what to do, never what gets refused and why.

It also contains one outright error: it tells the model to use **`jib_reveal`**, which is not a
template ID. The actual ID is `crane_reveal` (`templates.py`). Because the provider schema
enumerates IDs from the catalog, that instruction can only ever cause a worse choice, never the
intended one.

The rewrite fixes that, adds all four missing pieces plus mark coordinates and continuity rules,
and keeps the existing contract language verbatim where it is already right. Full text in
`03-script-to-simulator-SKILL.md`, ready to drop in at
`packages/takeone/director/robot-film-director/SKILL.md`.

Note that changing this file changes `provenance.filming_skill_digest` and
`CreativePlanning.capabilities_digest()`, which is correct — previously generated scripts should
be attributable to the skill version that produced them.

---

## 10. Performance

`compile_template` runs MuJoCo FK plus a bounded `least_squares` IK per arm per frame, at 25
frames of arm period per second of filming. A 10-second shot is ~250 frames × 2 arms. Measured
cost on this machine should be established before optimising, but expect 1–3 s per shot.

Plan, in order of value:

1. **Disk cache keyed on `digest(settings) + model_hash + calibration_hashes`** (`previs/cache.py`).
   Re-running an unedited script is free. The existing `@lru_cache(maxsize=3)` on `_compile` and
   `_route` stays as the hot in-process layer.
2. **Compile in shot order, stream progress.** The first shot is playable in ~2 s; the rail fills
   in. Reuse the job/worker pattern already in `director/planning.py` rather than inventing one.
3. **Do not parallelise.** `server.py` holds a global `compile_lock` because two studios must not
   fight over the planner, and MuJoCo model load is per-process. A worker pool here buys seconds
   and costs a class of bugs that will surface at the demo.

Target: an 8-shot script cold-compiles in under 25 s with visible progress, warm in under 1 s.

---

## 11. Build order

Each step ends with something demonstrable. Nothing depends on a later step.

| # | Step | Ends with |
|---|---|---|
| 1 | `screen_geometry` + `route_filming_time_s` + `diagnostics.py` + tests | Numbers to put in the skill, and the invariant test from §8 passing against all 28 templates |
| 2 | Rewrite `SKILL.md`; add mark coordinates to `PLAN_SCHEMA` | Generated scripts carry placed marks and timing the arithmetic supports |
| 3 | `previs/cache.py` | Repeat compiles are free |
| 4 | `previs/sequence.py` with **no repositions** (hard cuts), `POST /api/previs/sequence` | A whole script compiles to one program, verifiable from the CLI before any UI work |
| 5 | `sequence-player.js` + tests, then `orbit.js` sequence mode | **The demo exists.** AI script → simulator plays every shot end to end |
| 6 | `reposition.py`, wired into the sequencer | Cuts stop teleporting; the continuous-set decision is delivered |
| 7 | `director.js` movement display + deep link | Round trip is visible in the Director UI |
| 8 | `repair.py` + `repair_shots` action | A generated script is reliably rehearsable |
| 9 | Per-shot inspector edits flowing back into the script | Operator override |

Step 5 is the milestone worth protecting. Steps 6–9 each improve it; none of them is required
for it to be true that a `gpt-5.6-luna` script drives the simulator.

---

## 12. Deliberately out of scope

- **Scene geometry** — stairs, streets, captured or generated sets. The stage transform is
  designed so that adding a scene layer later means giving marks a `z` and a floor mesh, not
  reworking the sequencer. The `stairs` primitive stays a visible `unresolved` movement.
- **A second tracked actor.** One tracked actor per shot; others remain performance directions,
  as `SKILL.md` already states.
- **Physical execution of a reposition.** The reposition segment is a kinematic preview, labelled
  as such. Package 10 owns real robot integration.
- **Phone capture and physical zoom.** Still manual; lens changes remain simulated cues.

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Compile time makes the demo feel slow | Cache + streaming rail + step 4 lands before any UI, so cost is measured early |
| `orbit.js` regression from adding a fourth mode | `sequence-player.js` holds all new logic and is pure; `orbit.js` only swaps which preview is active. The 13 existing `.mjs` suites gate every change |
| Repair loop burns budget | Failing shots only, ≤2 attempts, existing consent gate, attempts recorded |
| Marks placed by the model overlap or leave the set | `warn` diagnostic, not a hard failure; the operator can drag marks in the studio |
| Edit timeline and rehearsal timeline get conflated in the UI | Both shown, always, side by side; `duration_mismatch` is an `error`, not a warning |
| Live provider unavailable at the event | Unchanged from today — the draft is saved, the manifest and sequencer are entirely offline. A hand-written or previously generated script rehearses with no network |
