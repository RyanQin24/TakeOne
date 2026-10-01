# Feature 04: responsive preview rendering

The studio now starts in **Smooth** mode. Use the **Preview** selector above the
world view to choose **Detailed** when sharper rendering and cast shadows matter.
The selection is saved on this browser. Both modes use the complete existing
robot geometry, the same camera field of view, the same solved arm poses, and the
same path and timestamps. Preview quality is not sent to the planning service.

## Changes

- Paused views render on changes rather than continuously. Camera navigation,
  scrubbing, drawing, undo, settings, resize and finished calculations wake them.
  Camera-control damping continues until the view settles.
- Turning the world camera redraws only that view. Offscreen views are skipped
  and refreshed when they become visible again.
- Smooth uses at most one drawing pixel per CSS pixel and no cast-shadow passes.
  Detailed caps the ratio at 1.5 and uses 1024 x 1024 shadow maps. Previously both
  views used up to 1.7 and recomputed 2048 x 2048 shadows on every animation frame.
- Detailed shadows refresh when the robot pose changes, instead of on every
  world-camera movement. The saved shadow stays valid while the shot is paused.
- Hidden documents suspend drawing. Local rehearsal excludes hidden time when
  the page returns; a real run resynchronizes to the playback service clock.
  Existing robot polling, heartbeat, Stop and motor timing are unchanged.
- Unchanged clock labels and control states are not repeatedly written to the DOM.

This addresses drawing cost, not initial model loading or path solving. The model
endpoint still sends the original full geometry. There are no dependency updates,
physics approximations, calibration edits or new hardware gates in this feature.

## Reproduce the measurements

Open `http://127.0.0.1:8766/?profile=1` to show a local performance sample. Wait
until the shot is ready and shaders have warmed up, then compare paused playback,
playing, world-camera navigation and the two quality modes. The output's
`data-sample` and `data-last-frame` attributes expose render counts and submitted
triangles for read-only browser inspection. No telemetry leaves the computer.

CPU/frame measures JavaScript and graphics submission, not GPU completion or
display latency. A background or embedded browser can throttle animation frames;
its FPS cannot establish the performance of a foreground browser. Diagnostics
are off without the query flag and do not poll or update the page in normal use.

Three.js documents the extra scene passes required by
[shadow maps](https://threejs.org/manual/en/shadows.html) and the renderer's
[shadow update controls](https://threejs.org/docs/pages/WebGLRenderer.html).

## Source mapping and recovery

| Before | After |
| --- | --- |
| Unconditional `orbit.js` animation loop | `render-loop.js` coalesces edits and sleeps when idle; `orbit.js` invalidates the affected views |
| Two full renders and pose evaluation on every frame | Pose evaluated when shot/time changes; visible dirty views render independently |
| Fixed high-resolution shadows | Smooth/Detailed selector in `index.html` and `orbit.css` |
| No render counters | Opt-in `render-profile.js`, disabled during ordinary use |
| Existing frontend regression suite | Adds `render-loop.test.mjs`; package syntax checks include both new modules |

Exact pre-feature copies of `orbit.js`, `orbit.css`, `index.html` and `package.json`
are under `data/recovery/preview-performance-20260913/`. These include the earlier
uncommitted ground-path feature. No unique source was deleted. The separate
editor work and physical robot modules are outside this change.

Results are recorded in `data/verification/preview-performance/RESULTS.md`.
