# Drawn-path feature verification — 13 September 2026

The ground-path feature is implemented and the local simulator is running at
`http://127.0.0.1:8766/`. The browser was left in Top view, reset to the calibrated
starting frame. No physical robot run was initiated.

## Passing checks

- **63 focused Python checks**, including eight new path tests and the existing
  orbit, cart geometry, robot service and physical player contracts. See
  `focused-final.txt` (37.882 seconds). This run followed the service refresh and
  includes the current additional editor files in the source snapshot.
- **115 browser unit tests**: `check-2.txt`.
- Browser JavaScript syntax checks: `check-3.txt`, plus an explicit syntax check
  of the new `dist/path-editor.js` module.
- Product lint: `check-5.txt`. Formatting of all Python files changed for this
  path feature passed a separate focused check.
- Preservation check: 1,086 LeRobot files checked; no preservation failures.
  See `preservation.json`. Git comparison also showed no changes to calibration,
  rig configuration, cart drivers, robot models or the physical playback module.

The path tests cover exact foot conversion, straight travel, forward travel in
both circle directions, wire precision, 200 ms command holds, changing arm goals,
calibrated starts, input validation, saved settings and cache isolation. They
reintegrate every wheel packet independently and compare the result to every
preview frame, then recompute camera FK from the actual raw arm goals.

A full player test used fake arms and a fake cart with a drawn-path artifact.
The arms deliberately reported stale positions: the player continued sending
changing goals, completed, stopped the cart and retained the arm goals. This is
software verification, not evidence of physical tracking accuracy.

## Browser verification

Checked in the existing 618-pixel-wide app browser:

- Click-to-add points and freehand dragging.
- Red requested route and amber motor prediction on a one-foot grid.
- Start/end markers, precise endpoint editing in feet, and route timing updates.
- Close loop; Undo of a stroke, redraw and endpoint edits.
- Save confirmation; Open of `data/examples/drawn-path.json` with restored
  coordinates and recalculated timing.
- Play/pause, scrub and reset; inspected the cart position and phone framing
  mid-route. Verified the idle robot panel no longer covers the camera monitor.
- Prepare robot run enabled Run on robot; redrawing invalidated it immediately.
- Existing orbit template still compiles after switching movement modes.
- Final refresh showed Path ready; no browser warnings or errors were recorded.

## Broader check limitations

The requested `scripts/TakeOne.ps1 -Command test` entry point was rejected because
the launcher is unsigned under this computer's policy. Its underlying
`scripts/verify.py` was run directly without changing execution policy.

The full Python discovery run was **interrupted**, not passed, after about twelve
minutes. It had recorded failures/errors in older cart-plan and planner/contract
tests. During that run a separate set of `packages/takeone/editor` files appeared
in the shared workspace, invalidating the running service's source snapshot.
The unrelated editor files were preserved. The simulator was restarted and all
63 focused checks were rerun successfully against the current workspace.

The broad simulation discovery was also interrupted after approximately three
minutes in its older compiler setup; its 15 drive checks had passed. Partial logs
are retained as `check-0.txt` and `check-1.txt`; their process-termination exit codes
in `summary.json` must not be interpreted as complete test runs.

The remaining broad checks completed. Global formatting reports 34 files in the
older planning/simulation code and separate editor work (`check-6.txt`). These
files were not reformatted as part of the ground-path feature. **The complete
repository suite is not claimed to pass.**

## Physical scope

The preview and robot artifact share wheel commands, arm samples, start poses and
timing. Actual motion remains open loop using the configured approximate wheel
response. Slip, unequal motors and stopping lag can cause physical deviation.
The red line is requested travel; the amber line is a prediction, not measured
robot motion. Original calibration and the user's motor identities are retained.
