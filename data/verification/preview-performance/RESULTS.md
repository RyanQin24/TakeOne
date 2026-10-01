# Preview performance verification — 2026-09-13

Scope: browser rendering only, alongside the existing uncommitted drawn-path
feature. No physical robot was activated and no Python, calibration, driver or
motion-planning code was edited for this performance change.

## Measurements

Read-only local service samples before the change:

- `/api/health`: 0.057 s.
- `/api/model`: 0.324 s, 12.696 MB JSON, 13 unique meshes, 95 geoms, 19 bodies.
- Mesh inventory: 132,851 unique vertices, 266,522 unique triangles; 646,500 mesh
  triangles after instancing. Primitive geometry is additional.

Same default route, initial calibrated pose, Studio view, approximately 618 x 876
CSS viewport in the Codex embedded browser. Both views were visible. Counts are
from Three.js `renderer.info`, with automatic resets disabled in the opt-in
profiler so shadow passes are included.

| Measurement | Original | Smooth |
| --- | ---: | ---: |
| Triangles submitted for both views at initial pose | 1,326,370 | 659,894 |
| Repeated view draws while paused, settled 2 s sample | 4 | 0 |
| World color pass calls, Smooth | — | 124 |
| Phone color pass calls, Smooth | — | 7 |

The 50.2% triangle-work reduction is a renderer-counter comparison, not a measured
FPS speedup. Original paused sampling was throttled to about 1 frame/s by this
browser environment. Optimized playback was also about 1 frame/s, so these FPS
samples do not predict foreground user performance. CPU submission samples of
roughly 2.8 ms before and 1.65 ms after were taken at different moving poses and
are only diagnostic observations, not a controlled CPU/GPU benchmark. Initial
shader compilation is excluded from steady-state comparisons.

Smooth at the starting pose: world 657,768 triangles, phone 2,126. Switching to
Detailed restores shadows: world 1,315,370 triangles, phone 11,000 on its initial
refresh. The measured buffers were 380 x 420 and 378 x 213 in Smooth; 570 x 630
and 568 x 319 in Detailed. The original 1.7 pixel-ratio ceiling was higher again.

## Automated checks

- `npm.cmd test`: **121 passed, 0 failed**, including six new scheduler/quality
  tests and the existing robot-client, playback, geometry and path-editor tests.
- `npm.cmd run check`: passed; includes syntax checks of both new modules.
- Required `scripts/TakeOne.ps1 -Command test` was attempted. Windows rejected the
  unsigned launcher before it executed. Execution policy was not changed. The
  frontend commands above were run directly. The whole Python/integrity/style
  suite was not rerun for this frontend-only change; the prior drawn-path record
  documents its unrelated failures and incomplete long-running checks.

The new regression checks exercise idle sleep, bursts of edits, separate view
invalidation, camera damping that requests another frame, hidden-tab cancellation
and return, dropped-frame elapsed-time playback, and pixel-ratio limits.

An initial browser-only requestAnimationFrame binding error was found during
verification and fixed with a native-call wrapper. Browser verification after
that fix uses the working final build.

## Browser interaction checks

- Default Smooth mode loads the full cart, both arms, red route and phone view.
- Switching Detailed on/off restores/removes cast shadows without changing the
  playhead, route or solved shot values. Smooth persists after reload.
- Top view redraw: world 126 draw calls; phone **0** draw calls. The paused phone
  monitor remains intact while navigating the ground map.
- Drawing a three-point replacement route, finishing and compiling updates the
  red route, start/end coordinates and enables preview playback. The temporary
  test route was 4.08 m with a 32.40 s preview.
- Scrubbing to 15 s updated both clock labels and the cart/arm scene. Playing
  with both canvases scrolled offscreen advanced the timeline with **0 view
  draws** in a settled two-second sample. Returning to Top refreshed the current
  paused pose and route.
- No new browser warnings/errors after the native-call fix. The four old error
  entries from the first failed build remained in browser log history and were
  distinguished by their timestamps.
- Normal `/` reloaded at the end with diagnostics removed, Smooth selected, and
  the original default half-circle route ready for user review. No real run was
  prepared or started during this verification.

Frontend test and syntax outputs are retained beside this record. `git diff
--check` passed for the edited existing frontend sources and README.
