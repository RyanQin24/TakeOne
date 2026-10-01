# 03 — Timeline and previs: implementation record

Branch `feat/script-to-simulator`. 14 September 2026. Design of record:
[`../03-script-to-simulator-design.md`](../03-script-to-simulator-design.md).

## Outcome

**14 September cinematic follow-up:** [Independent channels and compound routes](06-cinematic-channels.md)
adds per-channel timing, shared takes, product targets and explicit lower-bound
reposition timing. The earlier turn-in-place description below is historical;
it is an idealized diagram requiring unavailable reverse travel, not an
executable cart move. Work package 03's software workflow is extended by this
follow-up; physical commissioning remains separate.

A Director script drives the existing simulator end to end. Every shot is compiled from the
movement parameters the model chose, placed on its script mark, and played on one clock with
arm setup and labelled reposition estimates where the scene and transition permit them. The Director shows the movement behind each shot and
links straight into the rehearsal; blocked shots can be sent back to the model for a bounded
repair.

## The constraint that shaped it

**Nothing added here may refuse a shot the rig can already perform.** The only hard gates remain
the ones that existed before: `validate_settings` range checks, which describe the supported envelope and configured policy, not measured loaded-motion limits.
Every new observation is an advisory diagnostic attached to a segment. A 360° orbit in a
four-second edit slot still rehearses in full — it is annotated, not rejected. A script whose
marks carry no coordinates rehearses exactly as it did before this package.

This is enforced structurally: `previs/diagnostics.CODES` maps each code to `blocking` or
`advisory`, and only the four codes that correspond to a refusal the compiler already makes are
`blocking`. `tests/test_shot_diagnostics.py` asserts that set exactly.

## New modules

| Path | Lines | What |
| --- | --- | --- |
| `packages/takeone/previs/sequence.py` | ~190 | `build_program(manifest)` → one rehearsal clock. Compiles each shot through the cache, places it on its mark, inserts a reposition between takes, returns a ~7 KB outline carrying timing, placement, settings and diagnostics — no frames. |
| `packages/takeone/previs/reposition.py` | ~210 | Turn-in-place → drive → turn-in-place, with both arms easing back to their calibrated integer midpoints. Frames in the existing schema. |
| `packages/takeone/previs/diagnostics.py` | ~150 | The `Diagnostic` record and the ten codes. Severity is the contract. |
| `packages/takeone/previs/cache.py` | ~60 | Content-addressed previews under `data/previs-cache/`, keyed on the settings plus the existing `provenance()` snapshot. |
| `apps/rehearsal/dist/sequence-player.js` | ~120 | Pure: stage transform over a preview, concatenation onto one clock, half-open segment lookup, timeline boundaries. No DOM, no THREE. |

## Contract changes

- `marks[]` gain `position_m` and `facing_rad`. **Required in the provider schema** (a new
  proposal places its marks), **optional everywhere else** — existing scripts stay valid and
  produce identity stages.
- `shot_settings` raises a typed `MovementError` carrying `code`, `parameter`, `observed`,
  `allowed` and `suggestion`, instead of a bare `ValueError` string. Bounds are pre-checked
  against `FIELDS` so a refusal can name the field; `validate_settings` remains the authority.
- `validate_plan(..., refused=[])` marks a shot whose movement the rig cannot take as
  `unresolved` and collects the reason, instead of discarding the whole document. Without the
  argument, behaviour is unchanged. **This was not in the design and turned out to be required:**
  `_finish` validated proposals strictly, so one out-of-range number from the model threw away an
  entire generated script — and a blocked shot could therefore never reach the database for a
  repair to fix.
- `plan_schema(require_movement, require_marks)` — generation asks for placed marks; accepting a
  proposal does not refuse one that arrived without them.
- New creative action `repair_shots`; new job kind `creative_repair`; `repair_schema()`.
- `POST /api/previs/sequence` and `POST /api/previs/reposition`.
- `movement_schema()` now states `minItems`, so the shared validator can check a repair.

## What differs from the design, and why

1. **The program carries no frames.** The design had `RehearsalProgram.segments[].preview`. A
   six-shot script is 10–20 MB of frames; the outline is 7 KB and the studio fetches each
   segment's frames from `/api/previs/templates` (a cache hit) and `/api/previs/reposition`.
2. **The studio plays one concatenated preview, not a swapped active one.** `concatenate()`
   joins every segment's frames onto a single `time_s` axis, so `pose()`, `framePair`, the
   scrubber and every readout in `orbit.js` work on a whole script unchanged. The renderer never
   learns what a segment is.
3. **`sequence-client.js` and `stage-transform.js` were not created.** The stage transform is a
   pure function in `sequence-player.js`; the rail and segment-bar DOM is ~60 lines in
   `orbit.js`. Two more module files would have been indirection, not a boundary.
4. **`duration_mismatch` is advisory, not an error.** The design made it blocking. Blocking it
   would refuse a shot the rig performs correctly.
5. **Repositions run at the movement library's maximum pace** (`FIELDS["speed_m_s"]["max"]`,
   0.35 m/s), sourced from the catalog rather than hardcoded — the same ceiling any truck or
   dolly shot may already command. They are dead time between takes.
6. **Tests are flat in `tests/`**, matching the existing convention, and `test_reposition` and
   `test_framing_geometry` are folded into `tests/test_sequence.py`.

## Verification

| Suite | Result |
| --- | --- |
| `tests/test_sequence.py` | 14 pass — contiguous clock, determinism, placement, no lateral translation, arms reach exact midpoints, route arithmetic, the published framing table |
| `tests/test_studio_translation.py` | 10 pass — the drift guard: every one of the 28 templates round-trips its own defaults through `movement_schema()` and `shot_settings`; every `FIELDS` bound refuses out-of-range on both sides |
| `tests/test_shot_diagnostics.py` | 10 pass — each code fires on its own case and stays silent on its neighbour; only compiler refusals are blocking |
| `tests/test_shot_repair.py` | 9 pass — failing shots only, budget gate, attempt limit, re-validation, creative fields frozen, one bad number does not discard a proposal |
| `apps/rehearsal/tests/sequence-player.test.mjs` | 7 pass |
| Existing Python and `.mjs` suites | Failure sets **identical** to a baseline of the same tree with these changes reverted |

End to end over HTTP, four shots on two marks:

```
program cold 6.6s -> warm 0.25s · deterministic True
7 segments · rehearsal 173.8s vs edit 18.0s · blocked []
  shot        Static · locked frame     121f dur   9.48
  reposition  Move to the next mark     210f dur   8.36  reposition_long/advisory
  shot        Hero reveal · rising orbit 164f dur  13.04  duration_mismatch, aim_reach, height_reach
  reposition  Move to the next mark     282f dur  11.24  reposition_long/advisory
  shot        Dolly in · push in        121f dur   9.60  framing_mismatch/advisory
  reposition  Move to the next mark     316f dur  12.60  reposition_long/advisory
  shot        Orbit · full 360°        1371f dur 109.48  duration_mismatch/advisory
durations match: True · every diagnostic advisory: True
```

The 360° orbit asked for a four-second slot and rehearses its full 109.48 s. That is the
constraint working.

Cache: 2.06 s cold, 0.040 s warm for one shot; a changed parameter misses correctly.
`sequence-player.js` was also executed in a real browser on the target machine — placement and
boundary lookup correct.

## Measured versus untested

- **Measured here:** compile timing, cache hit/miss, determinism of the program digest, frame
  counts, segment contiguity, arm park endpoints, the absence of any lateral cart translation.
- **Not tested:** live `gpt-5.6-luna` access. The repair loop is exercised with an offline
  `ProviderResult` fixture, exactly like package 02's planning tests. No credential was used.
- **Not claimed:** the reposition is a kinematic estimate. It is labelled
  `physical_path_verified: false` and carries a note saying so. It is deliberately not routed
  through the calibrated wheel-response planner, because presenting unmeasured travel as a motor
  plan is the claim `implementation-rules.md` forbids. Physical execution belongs to package 10.

## Blockers and follow-ups

- **Live provider access** remains the package 02 blocker and now also gates repair-loop
  integration acceptance.
- **Per-shot inspector edits flowing back into the script** (design build order step 9) are not
  built. The rail is read-and-seek; editing a shot still happens in the Director.
- **Scene geometry** is out of scope by decision. The stage transform is shaped so a later scene
  layer means giving marks a `z` and a floor mesh, not reworking the sequencer.
- **Unrelated:** `tests/test_movement_library.py` fails on `tilt_up`, `tilt_down` and
  `high_angle` on Linux. `tilt_down` and `high_angle` pre-date this work; `tilt_up` appeared with
  the concurrent `previs/path.py` change made outside this package and reproduces with these
  changes reverted. Not investigated here.

Restart the simulator after pulling this branch: `config.provenance()` hashes every source file
at import, so a running planner refuses to plan until it is restarted.

---

## Addendum — two geometry errors found from a screenshot

Reported against a `truck_left` shot: the ring light was sitting in the middle of the phone's
frame, and the actor had its back to the lens.

### The light stood in the shot

Measured on the reported settings (radius 2.5 m, travel 1.5 m, 0.17 m/s, bearing 180°, 35 mm):
the light's optical point lay **between** the phone and the actor at every frame, and its
perpendicular offset from the lens axis collapsed **0.204 m → 0.099 m → 0.016 m** over the move.

The mounts were not the problem — `cam_base` is at cart-local **+0.23 Y**, `light_base` at
**−0.23 Y**, and the actor is on the phone's side at a constant **83.8°** for every bearing (all
eight checked). The problem was that `AimingSolver` is **under-constrained**: five joints against
four constraints (2 direction + 1 roll + 1 height). A whole family of poses satisfies it, and
nothing told the solver to prefer one, so it arbitrarily chose a light pose reaching across the
camera's sight line.

`solve()` now takes `clear` — the camera's optical point — and adds one residual term: the
penetration of the light's optical point into the phone's frame cone, measured against the
**13 mm** lens so every longer one is clear too, plus the ring fixture's radius. It is a soft
term, so a pose that has no alternative is still chosen; nothing the rig can do was removed.

| shot | clearance at 13 mm | clearance at 35 mm | aim error |
| --- | --- | --- | --- |
| `truck_left` | −0.742 → **−0.028 m** | **−0.326 → +0.154 m** | 0.28° unchanged |
| `hero_orbit` | +0.029 → +0.046 m | unchanged | 2.17° unchanged |
| `orbit_360` | +0.017 → +0.044 m | unchanged | 1.52° → **1.19°** |
| `push_in`, `static` | unchanged | unchanged | unchanged |

Achieved camera height is unchanged to 1 mm everywhere. Sweeping the weight from 12 to 40 moves
the result by under 0.02 m, so the term has converged; 12 is used.

**Honest limit:** on `truck_left` at the ultra-wide 13 mm the light is still 0.028 m inside the
cone. Two arms 0.46 m apart cannot clear a 108° field of view. At the shot's actual 35 mm it is
clear by 0.154 m.

### The actor faced away

`stage()` set the actor's heading once, from the **opening** camera, and held it for the take.
Over the reported 1.5 m truck the error grew **0° → 14.7° → 30.2°**; on a longer travel or an arc
it reaches 180°, which is the back of the head the phone view was showing. The studio now
re-evaluates that heading every frame from the live camera position, so the actor presents to the
lens for the whole take. Walking actors keep using their walk heading, unchanged. This is a
rendering choice only — no motor output changes.

### The actor, and with them the rig, can be placed anywhere

New **Where the actor stands** controls in the studio: actor X and Y in feet, plus a set rotation.
They apply the same stage transform the sequencer uses (`placePreview`), so the cart keeps its
exact geometry and moves with the actor. No recompile and no new parameter — the shot maths is
relative to the actor, so placing the actor places the whole setup. Hidden in Director-script
mode, where each shot takes its placement from its script mark.

### Verification

`tests/test_light_clearance.py` — 6 tests: the light is outside the frame cone for every frame of
six templates; the truck that exposed this clears by more than 0.10 m; aim and height are not paid
for clearance; a wider lens demands more room than a longer one; `optical()` reports the pose it
is given. Existing suites: failure sets **identical** to a baseline with both changes reverted.

The earlier note about a `tilt_up` regression was wrong — it came from a stale baseline pairing an
old `path.py` with a new `compiler.py`. With both current, `test_movement_library` passes.

---

## Addendum — the planner now restarts itself

`config.provenance()` refuses to plan when any file whose constants the process captured at import
has changed on disk (`_is_process_input`: everything under `packages/takeone` except `director`,
`editor`, `recording` and `voice`). The guard is right — geometry constants really are captured at
import, and attaching current disk hashes to a plan made with older constants would be a lie.

The cost was that every commit touching `previs/` or `planning/` left a running simulator serving
`Planner process has stale code or drive settings` until a human restarted it, with no way to do
that from the UI.

- `config.current_process_inputs()` now hashes that exact file set on demand; `_PROCESS_INPUTS` is
  one call to it, so there is a single definition of what the process captured.
- `apps/rehearsal/server.py` runs a watcher thread that compares the two once a second and
  `os.execv`s into the new code when they differ — **never while `robot.status()["active"]`, and
  never while `compile_lock` is held**, so a robot run or an in-flight compile is not interrupted.
  `--no-reload` disables it. The guard itself is untouched: the new process re-captures its inputs
  the normal way.
- `orbit.js` wraps every planner call in `withRestart()`, which waits out that second and retries
  rather than leaving the red failure panel on screen.

Verified by editing `previs/templates.py` under a live server: the log shows
`Sources changed. Restarting the planner…` followed by a second `TAKE ONE ready`, and the next
compile succeeds with no human action. `test_movement_library` and `test_orbit_previs` pass
identically on a baseline with these changes reverted.
