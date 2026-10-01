# Simulator recovery checkpoint — 14 September 2026

The root simulator is running at http://127.0.0.1:8766. This checkpoint repairs
loading and restart recovery. The filming-side and independent-placement changes
are the next feature to review, following the user's request to work one feature
at a time.

## Reproduced problem

The original process answered `/api/health` with `ok: true`, while a real preview
request to `/api/previs/templates` returned HTTP 400 with the stale-planner error.
The browser showed both previews as unavailable. A healthy HTTP listener was not
proof of a working simulator.

The prior watcher captured another disk snapshot after startup rather than
comparing with the configuration module's import-time snapshot. It also did not
watch the server source itself, and attempted replacement from a background
thread before closing the server's listening socket and services.

The prior browser retry only recognized the stale-code message. A connection drop
during a restart or a busy response ended that retry and left an error panel.

## Changes and recovery mapping

| File | Before | After |
|---|---|---|
| `packages/takeone/config.py` | The watcher took a separate disk snapshot | `process_inputs_changed()` compares current files with the actual import snapshot; the provenance guard remains enforced |
| `apps/rehearsal/server.py` | Background-thread exec without service shutdown | Idle restart is serialized with compilation and robot requests, the main thread closes services and the listener, then starts the replacement |
| `apps/rehearsal/dist/orbit.js` | An inline retry for one error string | Startup and preview requests use the same bounded recovery client |
| `apps/rehearsal/dist/planner-client.js` | No shared client | Retries temporary disconnects, interrupted response reads, restart notices and busy responses; validation failures still surface |
| `apps/rehearsal/dist/index.html` | Older asset versions | Loads the current recovery script and stylesheet |
| `apps/rehearsal/dist/orbit.css` | White placement fields with pale text | Readable placement controls matching the dark interface |
| `apps/rehearsal/package.json` | New module absent from syntax checks | Includes `planner-client.js` |

Original edited files were copied before alteration to
`C:\TakeOne\data\recovery\simulator-recovery-20260914`, retaining their relative
paths. The user's existing Director, sequence, IK and calibration work was not
replaced with an older Git revision. No calibration file was edited.

## Live verification

- Two real automatic source-change restarts succeeded. The first replacement
  became healthy in **3.02 s**; editing and restoring the source completed two
  restarts in **6.54 s**. The source bytes were restored exactly. See
  `live-reload.json`.
- In the existing browser tab, the ground path, Truck left, Dolly Zoom in and
  Tracking lead previews loaded. Selection changed the displayed shot, camera
  settings, duration and timeline. Play, pause and scrub were exercised.
- Dolly Zoom in changed from **50.0 mm to 31.518 mm**. Its existing projected-scale
  readout was 0.00% drift. Tracking lead moved the actor **1.5 m**.
- The checked previews kept the actor and cart separated. See `live-previews.json`
  for exact returned template IDs, timing, distances and lens values.
- The final browser view is a paused Tracking lead shot at 10 s, showing the actor
  upright in the phone monitor and separate from the cart in world view.
- Robot status remained idle. This is software verification; no physical robot
  take was started.

## Tests

The seven new Python reload tests and seven new browser-client tests passed.
The Python tests cover edits before watcher startup, server-source edits, clean
shutdown, deferral during a compile or active take, and rejection of a new start
after a restart has been chosen. The browser tests cover reconnects, busy/restart
responses, invalid settings, startup requests and bounded failures.

The required `scripts/TakeOne.ps1 -Command test` was run. Its first suite completed
**619 tests with 8 failures and 5 errors**. All 16 movement-library tests passed,
including checks over all 28 templates for real motor/FK parity, landscape filming
starts, named movement behavior and initial cart/actor separation. The seven new
reload tests, 11 phone-camera tests, three orbit HTTP tests and 14 studio-robot
tests also passed. Full command results are in the accompanying `full-checks/`
folder. The complete verification command finished with exit code 1:

| Check | Result |
|---|---|
| Main Python suite | 619 tests; 8 failures, 5 errors |
| Older simulation suite | 29 tests; 1 failure, 2 errors |
| Browser unit tests | **191 passed** |
| Browser module syntax | **Passed**, including the new recovery client |
| Source integrity | **Passed** |
| Repository-wide Python lint | 9 issues outside the files changed for this repair |
| Repository-wide formatting | 11 files require formatting outside this repair |
| Python files changed for this repair | **Lint and formatting passed** |
| Diff whitespace for edited application/config files | **Passed** |

The additional older-simulation failures concern obsolete `time` frame fields and
an arm-speed assertion in the legacy planner. No full-project pass is claimed.

## Confirmed unfinished work — next checkpoint

1. **Filming side is not fixed.** With the current powered-wheel heading, the
   actor is at cart-local Y = -2.5 m for Truck left and approximately -2.499 m for
   Arc clockwise. The phone mount is at +0.23 m and the light mount at -0.23 m.
   These shots still use the light-arm side. A rigid rotation of the entire set
   preserves that relationship, so the current Set rotation control cannot fix it.
2. **Actor and cart cannot yet be placed independently through those controls.**
   `readStage()` and `placePreview()` translate/rotate both together. Drawing also
   needs a consistent conversion between set and shot coordinates when a stage
   transform is active.
3. **The light-clearance solve uses the wrong phone keyframe.** The path compiler
   solves all phone goals first, then reads `solver.optical(q, "phone")` in the
   light loop without loading the phone goal for that loop's time. It therefore
   uses the phone pose left at the end of the phone solve. This is a separate
   regression to correct with the filming-side feature, rather than presenting
   the current soft-clearance term as a completed solution.
4. **A standing actor is currently turned toward the lens every frame.** An
   independent actor-facing control is needed for an actor who should remain
   stationary while the cart orbits.
5. **The complete project is not green.** The full Python run also reports
   Director model/response mismatches, legacy planning/execution test failures
   and a shot-cache assertion affected by differing arm-setup duration. These
   were not hidden by weakening checks or changing calibration.

The pasted design and previous assistant's statements were used as material to
audit, not accepted as proof that those features were already complete.
