# Simulator full repair — 14 September 2026

Workspace: `C:\TakeOne`. App: <http://127.0.0.1:8766/>.

This checkpoint addresses all five unfinished items recorded in
`../simulator-recovery-20260914/RESULTS.md`. It preserves the earlier stale-process
recovery, the existing 28 movement templates, and the user's Director work.
The attached design and prior assistant statements were audited as reference
material, not treated as proof of implementation.

## Changes and before/after mapping

| Area | Before | After | Implementation |
|---|---|---|---|
| Filming side | Truck left and clockwise arc placed the subject on the light-arm side. Rotating the whole set did not change that relationship. | Templates default to phone-side filming. Those two route directions are adapted and labelled in the shot status, timeline, notes and saved plan. “Keep requested direction” restores the original route direction. Drawn routes retain their authored order. | `packages/takeone/previs/templates.py`; `apps/rehearsal/dist/orbit.js` |
| Placement | Actor X/Y and set rotation transformed a rendered preview, moving actor and cart together. | Separate actor and powered-axle start coordinates enter the deterministic planner before wheel prediction and arm IK. The scene has route rotation about START, separate actor facing, and an optional walking target. | New `packages/takeone/previs/placement.py`; existing `previs/program.py`, `previs/path.py`, `previs/compiler.py`, `motion/studio_plan.py` |
| Route editing | Drawing under a preview transform could mix scene and route coordinates. | World points are stored in metres and displayed in feet. Imported placement is baked once before editing. Moving the actor leaves the cart route alone. Moving the cart translates its route. | New `apps/rehearsal/dist/scene-placement.js`; existing `orbit.js`, `index.html`, `orbit.css` |
| Light IK | The light solve used the final phone pose for earlier keyframes. | Each light keyframe uses its matching quantized phone joint goals and optical direction. Soft clearance distinguishes a fixture behind the lens from one obstructing the view ahead. Light-arm geometry remains visible in the simulated phone view. | `packages/takeone/previs/compiler.py`, `previs/path.py`; `apps/rehearsal/dist/orbit.js` |
| Standing actor | The renderer turned the actor toward the moving camera every frame. | Default facing is the opening camera direction, held throughout the take. Fixed world heading and explicitly following the camera are separate choices. A walking actor follows the chosen walking heading. | `previs/placement.py`; `apps/rehearsal/dist/walking-actor.js` |
| Test contracts | Provider fixtures, timing fields, software coordination and legacy packet assertions disagreed with current contracts. | Fixtures use the configured model/budget/timeout, canonical frame timestamps, and scoped software coordination. Public physical admission remains intact. Packet verification checks actual emitted commands and resulting odometry. | `tests/test_creative_planning.py`, `tests/test_robot_motion.py`, `tests/support/coordination_clock.py`, `tests/simulation/test_engine.py`; `packages/takeone/execution.py` |
| Windows fixture cleanup | A preservation test created its temporary nested repository inside the live checkout; a run failed when Windows held that directory during cleanup. | The fully independent fixture uses the system temporary folder, outside workspace watchers. Its five tests pass. | `tests/test_repository_integrity.py` |
| Legacy trajectory | Render and dispatch grids could contain almost-equal times, producing artificial derivative spikes. The old 9 s demonstration exceeded its existing arm-speed limit with the corrected geometry. | Coincident timestamps preserve the exact dispatch time. The existing demonstration uses 14 s; no motor range or limit was expanded. | `packages/takeone/planning/trajectory.py`; `configs/shots/arm-led.json` |

The new placement fields are consumed by the existing compiler. No separate
preview-only IK implementation or motor-goal generator was added. Off-centre
legacy orbits use the path solver because their arms cannot rely on circular
symmetry. Their timing follows the calculated motor packets.

## Recovery and preservation

Before editing, 323 relevant source, test, document and launcher files were copied
to `C:\TakeOne\data\recovery\simulator-full-fix-20260914`, retaining relative paths.
The demonstration shot configuration was backed up before its duration changed.
`execution.py` and `planning/trajectory.py` were clean at the start; their original
Git HEAD blobs are also saved under that recovery folder. Existing unique work
was retained. No calibration original, firmware or LeRobot source was edited by
this repair. The prior recovery folder remains intact.

## Live browser checks

- All **28 distinct movement presets** were selected in the actual interface.
  Every one completed compilation, displayed its matching shot status and
  timeline, and enabled “Prepare robot run”. See `movement-selector.md`.
- A new horizontal ground route was drawn directly on the map, compiled and
  saved. Its route remained separate from the actor. Changing actor movement to
  Walk, 2 ft at 90 degrees, compiled successfully and showed the moving target
  in the mid-shot world and phone views.
- Actor X was set to 2.5 ft, the shot saved, another preset loaded, and the saved
  shot reopened using the actual file chooser. Actor X returned to 2.500 ft.
  The downloaded settings are preserved in `saved-truck.json`.
- The cart was placed on the map at approximately (-6.676, -8.745) ft while the
  actor remained at (2.500, 0) ft. Preparing that shot completed with
  “Robot commands ready”. The physical Run button was not clicked.
- The phone view showed an upright landscape image. The checked world views
  showed the cart and actor at separate marks and the requested route in red.
- Quick consecutive selection of Whip pan, Hero reveal, and Dolly Zoom in ended
  with Dolly Zoom in selected and loaded, with the matching timeline. There were
  no browser console errors after the complete 28-preset check.
- Play and Pause advanced and stopped the preview clock. The final page is the
  Hero reveal paused at **16.0 s**, with Studio view and the landscape phone
  monitor visible. A final console check returned no errors.

## Live compiler evidence

`check_live.py` submits compile-only requests to the running local app. It does
not start a robot take. Results are recorded in `live-results.json`:

| Case | Verified result |
|---|---|
| Hero reveal | Actual planned camera height rises from 1.254447 m to 1.590469 m; both phone and light joint goals change. |
| Dolly Zoom in | Focal length changes from 50.0 mm to 31.517843 mm while the cart approaches; both arm goals change. |
| Walking target | Actor travels from (0.3, 0.1) m to (0.3, 0.7) m; both arms change their tracking goals. |
| Saved truck | Saved actor mark is (0.762, 0) m; cart and actor stay separated in the sampled preview. |
| Drawn route | Saved world points compile into the motor plan; minimum sampled cart/actor separation is 1.936 m. |

These cases verify planned geometry and command consistency, not measured robot
motion. The robot endpoint remained idle. Focal-length effects and upright output
remain simulator features; the phone's recording app still controls real zoom
and recording. Clearance is a soft planning objective, not a promise that every
arbitrary manual placement can avoid an obstruction.

## Automated checks

All current check groups passed:

| Check | Result | Evidence under `full-checks/` |
|---|---|---|
| Complete main Python suite, final rerun | **629 passed** in 384.399 s | `main-python-after-fixture-fix.txt` |
| Legacy simulation suite | **29 passed** in 524.021 s | `check-1.txt` |
| Browser unit tests | **195 passed** | `check-2.txt` |
| Browser module syntax | **Passed** | `check-3.txt` |
| Source and calibration evidence preservation | **Passed**, 1,086 LeRobot files checked | `check-4.txt`, `preservation.json` |
| Python lint | **Passed** | `check-5.txt` |
| Python formatting | **Passed**, 208 files checked | `check-6.txt` |

The required `scripts/TakeOne.ps1 -Command test` was run twice during the repair.
The final combined launch returned exit code 1 because its main suite hit the
Windows temporary-repository cleanup error described above. The fixture was
corrected; its five tests and then the entire 629-test main suite passed. Every
other group from that launch passed. The original launcher output and raw
`summary.json` are retained without rewriting the failed result. The final
group-by-group status and follow-up explanation are in `verified-summary.json`.
Source/configuration whitespace checks also passed.

Focused checks already passed: 10 placement/timestamp tests, 38 provider/light/
coordination checks, and a final six-test coordination rerun. The expanded checks
verify actual raw motor/FK parity, independent marks, exact saved-plan identity,
actor-facing behaviour, matching phone/light keyframes, and preservation of the
motor dispatch grid.
