# Hero reveal / rising orbit verification

Date: 2026-09-13. Workspace: `C:\TakeOne`.

This is the first reviewable camera-choreography feature. Dolly Zoom, the other
researched templates, walking actors and automatic AI Director dispatch are not
implemented in this step. See `docs/camera-movement-library.md` for their design.

## Automated checks

- 72 Python tests passed in 79.697 seconds. Command from the workspace root:
  `.venv/Scripts/python.exe -m unittest tests.test_shot_templates tests.test_drawn_path tests.test_orbit_previs tests.test_studio_robot tests.test_shot_playback tests.simulation.test_drive -v`.
- Coverage includes template validation, calibration starts, changing motor 2
  goals on both arms, independent FK and wheel-packet integration, robot prepare
  serialization, the actual robot player's changing arm goals using fake devices,
  HTTP origin/parameter handling and cache isolation/invalidation.
- 121 frontend tests passed. Run `npm.cmd test` from `apps/rehearsal`.
- Frontend syntax checks passed with `npm.cmd run check` from `apps/rehearsal`.
- Targeted Ruff checks passed for `packages/takeone/previs`,
  `packages/takeone/motion/studio_plan.py` and `tests/test_shot_templates.py`.
- The required `scripts/TakeOne.ps1 -Command test` launcher was attempted but
  Windows blocked the unsigned script. Execution policy was not changed. The
  targeted checks above were run directly; a clean full repository suite is not
  claimed.

See `python.txt`, `frontend.txt` and `syntax.txt` for command output.

## Default shot measurements

The default is a 90-degree counterclockwise arc, 2.5 m radius, 0.17 m/s requested
pace and 35 mm equivalent simulated focal length. The actor remains stationary.

| Quantity | Result |
| --- | --- |
| Setup before travel | 6.08 s |
| Travel | 25.80 s |
| Total timeline | 31.88 s |
| Predicted cart distance | 3.9428 m |
| Predicted peak cart speed | 0.171875 m/s |
| Achieved optical height, opening to finish | 1.25037 to 1.59016 m |
| Achieved upward optical pitch | 10.02198 to 0.08791 degrees |
| Maximum simulated face-aim error | 2.15261 degrees |
| Phone motor 2 span during filming | 1112 encoder counts |
| Light motor 2 span during filming | 346 encoder counts |

The height profile holds low for the first 10% of travel, rises with quintic
easing until 85%, and holds at the finish. These values are predictions from the
existing wheel response and calibrated arm model, not physical measurements.
No new aiming-error stop threshold was introduced. No hardware was activated.

## Cache measurements

Measured in one fresh process using the same default settings:

| Request | Time | Relevant cache behavior |
| --- | --- | --- |
| Initial compile | 1.3858 s | One cart-route miss |
| Identical repeat | 0.1196 s | Complete result reused |
| Change finish height to 1.50 m | 1.7884 s | Same cart route reused; arms recalculated |
| Return to original settings | 0.2397 s | Original complete result reused |

See `measurements.json`. These are local compile timings, not rendered FPS. A
height edit still needs arm planning; the route cache avoids duplicate wheel
prediction. Playback interpolates precomputed frames. The existing Smooth,
on-demand and offscreen-render behavior remains in use.

## Browser verification

Verified in the Codex in-app browser at `http://127.0.0.1:8766/`:

- The final `choreo-05b` interface loads the Hero reveal option and reaches
  "Hero reveal ready" with preview, save, export and robot preparation enabled.
- The red requested arc, amber motor prediction, start/end markers and one-foot
  grid are visible. The default preview uses Smooth quality.
- At 6.376 s, the camera readout is 1.25 m / 10.0 degrees / Hold low. At the
  finish it is 1.59 m / 0.1 degrees / Hold finish.
- The joint inspector follows the playhead. The phone shoulder-lift reading
  changes from approximately 96.4 degrees near the opening to -1.3 degrees at
  the finish; the light shoulder lift also changes.
- Editing the finish to 1.50 m recompiles and visibly produces 1.50 m / 2.7
  degrees at the finish. Restoring 1.59 m restores the original result.
- Play advances through the changing-height shot. Scrubbing pauses and updates
  both views and the joint readouts. No browser warning/error logs were captured
  on the verified tab.
- The final visual adjustment stages the actor toward the opening lens and
  keeps the actor's heading stationary during the take. The opening screenshot
  visibly shows the face with a low, upward-looking camera composition.
- The simulator is left paused near the start of filming with Hero reveal
  selected for user review. Robot playback remains idle.

Concurrent editor changes under `packages/takeone/editor` invalidated the running
server's source provenance during verification. The idle rehearsal service was
restarted after those writes; no provenance checks were bypassed. The old browser
tab had a stale connection-error page, so verification used a fresh tab in the
same in-app browser. The new working tab is retained for review.
