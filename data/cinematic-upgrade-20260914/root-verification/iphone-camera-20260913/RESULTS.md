# iPhone camera view and reusable zoom verification

Date: 2026-09-13. Workspace: `C:\TakeOne`. Simulator: `http://127.0.0.1:8766/`.

## Delivered feature

- Normal shots use an upright simulated output. Intentional roll and handheld presets retain physical roll in Auto mode. Explicit level and physical-phone modes are available on every movement.
- Raw camera FK, calibrated starting positions, and motor commands remain distinct from the corrected output pose.
- The iPhone 17 Pro Max profile offers 13, 24, 48, 100 and 200 mm equivalents, plus approximately 360 mm for the published 15x digital video range. This is ideal pinhole framing; it does not reproduce all recording modes, stabilization crops, distortion or lens switching.
- Every template, drawn path, and original orbit accepts fixed, preset, keyframed or Dolly Zoom lens behavior. Curves support zoom in, holds, zoom out, and explicit cuts.
- Camera edits reuse cached cart/arm solutions. Offscreen lens and height readouts update during scrubbing without waking the 3D renderer.
- Camera options survive movement switching and saved-shot round trips; Reset preset restores the preset camera options.

## Completed automated checks

| Check | Result | Evidence |
| --- | --- | --- |
| Python camera suite | 10 passed | `camera-python-final.txt` |
| Movement library, shot templates, drawn path and orbit suites | 42 passed, including default compilation of all 28 named presets | `movement-regressions.txt` |
| Frontend suite | 177 passed | `frontend-final.txt` |
| Frontend syntax check | Passed, including both new camera modules | `frontend-syntax.txt` |
| Ruff on the seven changed product/test Python files | Passed | Final tool output |
| Whitespace check on changed tracked feature source/docs | Passed | Final scoped tool output |

Camera assertions include preserved optical aiming direction, finite vertical aim, intentional roll, zoom holds/cuts, optical-depth Dolly Zoom, focal-range clipping, settings/plan identity round trips, unchanged motor packets, and cached camera edits that invoke no IK.

The earlier combined `motion-regressions.txt` run was interrupted. It is retained as partial evidence and is not counted as a completed suite. The two completed Python runs above total 52 tests.

The requested `scripts/TakeOne.ps1 -Command test` launcher was blocked by this computer's unsigned-script execution policy. The policy was left unchanged; direct runtime checks above were used instead. The full repository suite was not rerun and is not claimed to pass. A repository-wide whitespace check also reports unrelated existing CRLF log whitespace in `data/logs/preview-loading-error.log`; that log and other task changes were preserved.

## Live interface checks

- Restarted the local planner after the final Python edit and loaded the updated frontend assets. Health reported `ok: true`, `hardwareConnected: false`, `robotPlayback: idle`.
- Visually confirmed an upright standing actor during calibrated setup and after aiming, while the world model retained the physical arm pose.
- Switched to a roll preset and observed Auto select physical phone roll. Switching back restored the custom zoom curve. Reset preset restored default camera settings.
- Created a 10-second static shot with 24 mm at 0 seconds, 48 mm at 3 seconds, 48 mm at 6 seconds, and 24 mm at 10 seconds. The editor displayed all four times after arm setup.
- With the canvases offscreen, scrubbed to global 9.48 seconds (shot time 4 seconds): readouts immediately showed 48.0 mm and 1.59 m. Scrubbing to the end showed 24.0 mm.
- Left the demonstration loaded and paused at global 5.48 seconds, the start of filming after calibrated arm setup. The visible phone frame showed the actor upright at 24 mm.

## Scope and recovery

No physical robot or iPhone commands were sent. Zoom cues and level output remain explicitly simulated; the recording app must match the chosen lens and output orientation. Scripted cart/arm pauses are deferred to the next review step. The existing preview pause control only pauses rehearsal.

The implementation guide is `docs/iphone-camera-feature-08.md`. Original changed files are preserved under `data/recovery/iphone-camera-20260913/` using workspace-relative paths. Calibration and robot geometry were not edited. No commit or GitHub push was performed for this feature.
