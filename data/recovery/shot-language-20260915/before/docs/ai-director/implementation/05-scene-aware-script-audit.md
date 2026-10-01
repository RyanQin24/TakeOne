# Script-to-rehearsal audit — 14 September 2026

## Reproduction and preserved inputs

Audited the running root simulator on port 8766 and saved production
`4a77df58-57af-4739-83ee-d4c2b8e35f58`, document
`48df5811db893f50da61edfc453c7af0cdb5b7b3f420aded5f4c07710a8e77ae`.
Original session, manifest and compiled program are preserved under
`data/director-audit-20260914/`. The original is six shots, five repositions,
114.04 seconds of rehearsal and a proposed 30-second edit.

## Findings before changes

1. **Scene identity disappears.** `rehearsal_manifest` flattens scenes; the
   sequence always connects consecutive takes by a cart route. Different places
   cannot have independent coordinates, atmosphere or set dressing.
2. **Placement changes the story's direction.** `stage_for` rotates every shot
   using camera bearing rather than actor heading. The side-track's scripted
   +Y approach becomes a walk near -X (3.284 radians).
3. **The sign has neither geometry nor an aim target.** Tilt up ends at the
   actor's face. The world contains four generic columns for every story.
4. **Tracking distances disagree.** Arrival requests 2.3 m of actor walking
   against 0.6 m of cart travel. Side approach asks 1.6 m against 0.9 m. No
   follow-controller intent survives the script handoff.
5. **The cinematic profile dictates movements.** Python profile text asks for a
   rise, walk and Dolly Zoom irrespective of the story. The actual shared
   instruction is already Markdown, duplicated under docs and product code.
6. **Readouts are stale across shots.** The sequence summary retains the final
   shot's lens-to-face distance and camera height for the entire rehearsal.
7. **Framing checks use nominal cart radius.** They ignore actual optical
   depth, actor drift and Dolly Zoom lens compensation.
8. **Poor aim/reach is presented as an ordinary playable shot.** This production
   has 4.8, 15.0, 10.8 and 27.8 degree requested-aim errors and unachieved low
   camera heights. Aim residuals already exclude intentional tilt offsets;
   however the wording incorrectly describes every residual as face drift.
9. **Silence is dialogue.** Five shots store “No spoken line…” as a line to say.
10. **There is no edited playback.** Setup and relocations dominate the only
    clock; shot numbers count reposition segments as shots. Concatenation can
    interpolate across discontinuous cuts.

## Intended correction

Keep creative skills in Markdown with a small Python loader. Carry scenes,
location scouting directions, simulated objects, actor blocking, target and
follow intent through the strict schema, saved document, manifest and playback.
Use scene-local coordinates and explicit cut/reposition semantics. Continue to
use the existing cart prediction, calibrated arm solver and camera pipeline.
Expose both the edit and rehearsal clocks. Keep unmet geometry and missing live
controllers visible; a viewable simulation is not hardware qualification.

## Source mapping / recovery

- `director/skills.py` profile records → `director/filming-skills/*/SKILL.md`;
  the module remains the loader and owns existing editorial sample construction.
- `docs/ai-director/03-script-to-simulator-SKILL.md` → pointer to the packaged
  `director/robot-film-director/SKILL.md`, the provider's authoritative source.
- Existing template/path/sequence modules are extended in place. No calibration,
  hardware driver, authored dist directory or LeRobot content is removed.
- Original source is recoverable from clean starting Git revision
  `0ddd15d48ef8462a5a3eac1c3a5b954831db9c95`; original
  saved production is also exported before any changes.

## Implemented changes

- Scene/space IDs, scene-owned marks, atmosphere, scouting directions, supporting
  cast, set objects, camera targets and follow requests survive schema validation,
  saving, manifest translation, compilation and browser playback.
- Separate places use cuts and explicit off-camera location resets. A same-space
  reposition is an authored choice. Rehearsal remains setup plus filming; the
  story edit omits setup and trims extra coverage without changing source speed.
  Unavailable shots and timeline gaps cannot silently disappear from the edit.
- The reusable scene library contains facade, doorway, sign, wall, window, tree,
  bench, planter, table, chair, laptop, practical lamp and bollard. Object labels,
  transforms and dimensions are editable. Atmosphere changes the environment.
- Actor heading no longer rotates to camera bearing. A sign can be the actual
  camera aim target. Actor framing uses a composition offset, so a wide shot
  includes the body instead of centring on the face and clipping the feet.
- Framing checks use the solved camera depth and per-frame lens compensation.
  Current-shot readouts update lens, camera height, target distance and follow
  mode. The edit's travel excludes jumps between unrelated locations.
- Aim/reach errors and mismatched following distances mark shots for revision.
  A nominal cart-footprint screen reports intersecting props and leaves the
  centre of an open doorway traversable. This is an advisory geometry screen.
- Director instructions and four editorial profiles live in Markdown. Python
  loads the files and retains the existing explicit offline examples. Cinematic
  guidance chooses a story before choosing movements.
- `director/following.py` provides `start_cart_follow`, `start_head_follow` and
  a dispatcher. These are deliberately pending, side-effect-free placeholders
  requested by the user; manifest requests carry the selected actor, loss
  behaviour, hook names and head-relative composition offset.

### Additional failures found in the browser

1. The timeline's range input intercepted shot-segment buttons. Separate hit
   areas now select exact cut times (including shot 2 at 5.00 seconds).
2. The world camera could view a scene from behind a large facade and hide the
   actors and rig. The initial view now approaches from the staged camera side.
3. Two Windows listeners on port 8766 could accept requests for different
   Director owners, causing intermittent HTTP 409 on saving. The server now
   claims the socket exclusively; a second listener is rejected in a regression
   test. Built-in source reload left one healthy listener.
4. Shared form defaults rejected negative object positions and required blank
   object labels and dialogue. Scene coordinates now allow signed values;
   labels and spoken lines are optional, with valid dimension bounds.
5. Adding a scene copied a mark owned by the previous scene. A new scene now
   creates its own local mark and actor target. A browser save of a new silent
   scene was verified, then the five-scene delivery was restored.

## Revised arrival production

The edited draft is a separate saved production, preserving the original:

`5cf67270-9841-4587-98f4-f2f1b464b40e/a537943c9165524b36521620d494f672a10cbced0e3e43971d0e7183b1a3b809`.

| Edit interval | Scene | Camera choice | Follow selection |
| --- | --- | --- | --- |
| 0–5 s | Exterior arrival | Wide locked frame, slow actor movement | Authored |
| 5–10 s | Sign discovery | Tilt up to the sign object | Authored |
| 10–18 s | Approach beside E7 | Medium side tracking | Cart + head |
| 18–24 s | Level doorway | Wide lead tracking | Cart + head |
| 24–30 s | Interior build area | Held purposeful medium frame | Authored |

The live local API compiled all five shots with no current diagnostic advisories.
Maximum requested-aim residuals are 0.195, 0.274, 0.282, 0.231 and 0.141 degrees.
Maximum camera-height residual is 3.41 mm. The edit is exactly 30.00 seconds;
rehearsal is 58.92 seconds, excluding four location resets of unknown duration.
These are model predictions. The original reached 27.8 degrees of aim residual.

Source fixture: `tests/fixtures/director_arrival.json`. Saved session, manifest,
compiled program, editor QA evidence and verification logs are under
`data/director-audit-20260914/`. This draft was authored and tested locally;
it is not represented as a fresh provider-generated response.

## Verification

The required root command was run from `C:\TakeOne`:

```powershell
& C:\TakeOne\scripts\TakeOne.ps1 -Command test
```

It completed the simulation, browser, syntax, integrity and lint checks. Its
product suite found one outdated expectation of the mark schema, and formatting
identified `previs/path.py`. Both were corrected. The original root logs remain
in `data/director-audit-20260914/root-verification/`.

One intermediate product rerun was invalidated by a concurrent formatting
change: the existing stale-source guard rejected compilation. That log is
preserved as `product-verification-stale-source.txt`. The final rerun holds
Python sources steady and writes `product-verification-final.txt`.

- Product suite rerun: 647 passed. A final follow-metadata change restricts hook
  selection to the cart/phone fields (an explanation cannot enable a controller);
  its scene/translation regression rerun passed all 23 tests afterward.
- Simulation regressions: 29 passed.
- Browser unit tests: 203 passed; JavaScript syntax checks passed.
- Scene/translation focused tests: 23 passed.
- Ruff lint and formatting: passed across 209 Python files.
- All five Markdown skill folders passed the skill validator.
- Browser checks: all five scenes, visible props and two actors, full-body wide
  framing, sign reveal, play/pause, exact cut selection, scrub, edit/rehearsal
  switching, current-shot metrics, signed scene-coordinate saving, silent-line
  saving, new-scene saving and retained follow selections. No browser console
  warnings/errors appeared during final playback inspection.
- Runtime: one loopback listener; health OK, local rehearsal, hardware
  disconnected and robot playback idle. Calibration/asset preservation passed.

## Limits and remaining integration

- The friend's live cart/head controllers are not on this computer. The stubs
  report `implementation_pending` and `active: false`. They must be replaced
  and connected to a supervised runtime start; simulation does not call them.
- Scene meshes, actor blocking and atmosphere are authored proxies. Venue
  measurements, floor surfaces, clearances and exact gestures are not measured
  or fully animated by this work. Audio intent is descriptive; no score or
  location recording is synthesized.
- Obstacle screening checks the nominal cart footprint against staged objects;
  it is not full arm swept-volume, actor collision or physical qualification.
- Fresh paid AI generation and real robot execution were not exercised. The
  tests verify structured contract handling and the compiled local workflow;
  they cannot establish perfect interpretation of every future brief.
- Existing stationary-shot duration bounds still apply (2–120 seconds). The
  editor reports a validation error if a new stationary slot is too short.
