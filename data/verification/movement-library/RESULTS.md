# Movement library verification - 2026-09-13

The local studio at http://127.0.0.1:8766/ contains 28 cinematic presets in six
families, plus the previous drawn-path editor and original orbit controls.
The complete catalog and usage instructions are in
[camera-movement-library.md](../../../docs/camera-movement-library.md).

## Automated checks

- The initial targeted backend regression run passed **84 tests** in 110.451 s.
  It covered the new catalog, Hero, drawn paths, orbit previews, robot preparation,
  playback scheduling and the cart drive model. Output: [python.txt](python.txt).
- The final motion run passed **23 tests** in 68.374 s after fixing initial
  Dolly Zoom lens setup and locked framing with a walking actor. This includes
  all 28 defaults and independent checks of wheel integration, camera/light
  forward kinematics, calibrated starting commands, pointing directions,
  optical roll, height changes, walking targets and saved plan identity.
  Output: [final-motion.txt](final-motion.txt).
- The rehearsal frontend passed **123 tests**, including repeatable walking
  animation and geometry/material reuse across 240 pose updates.
  Output: [frontend.txt](frontend.txt).
- The frontend syntax check passed. Output: [check.txt](check.txt).
- The required root PowerShell test launcher was attempted, but Windows blocked
  the unsigned script under its existing execution policy. The policy was not
  changed. The direct checks above do not constitute a full repository-suite pass.

## Live browser checks

The in-app browser loaded the catalog and successfully selected every one of the
28 presets. Each reached its named ready state with Play preview enabled.
One automation wait timed out on the full 360-degree orbit; the next UI inspection
confirmed the finished preview and enabled playback without a retry or code change.

Visual checks confirmed:

- Dolly Zoom holds 50 mm during calibrated setup. At the start/end of filming,
  the actor stays the same apparent size while the background changes and the
  lens moves from 50.0 to 31.3 mm over approximately 1.51 m of cart travel.
- Side tracking shows the articulated walking actor, its world movement and
  camera framing. Editing its end camera height from 1.59 to 1.45 m changes the
  solved result. Play advances the timeline.
- Switching away and back preserves edited preset parameters. Reset preset
  restores the original values.
- Roll left visibly tilts the filmed horizon; the cart remains at its mark.
- Dolly Zoom's Prepare robot run reached Robot commands ready with 8.8 seconds
  of travel and 5.9 seconds of initial aiming. Run on robot was not clicked.
- No browser console errors or warnings were reported during the final checks.

## Reproducible default measurements

Run the non-actuating [probe.py](probe.py) with the project environment to
reproduce [default-metrics.json](default-metrics.json). All 28 defaults compile
and validate. The final local run took approximately 0.52-2.54 seconds per preset
without relying on a previously compiled complete result. These are backend
calculation timings, not frame-rate measurements.

The measurements use the configured wheel-response model and calibrated arm
mapping. Hero's camera rises from approximately 1.25 to 1.59 m and both arms'
shoulder-lift commands change. Both Dolly Zoom directions preserve f/z throughout
filming within floating-point precision. One ground square is 0.3048 m.

The cache retains up to eight wheel routes and six complete compiled results.
Playback interpolates solved frames; it does not run IK on each rendered frame.
No frame-rate target or physical accuracy is claimed from these checks.

## Scope

This feature implements the selectable movement library and shared cart/arm plan
generation. It does not transmit phone lens or recording commands. Lens changes
are simulated timestamped cues and remain manual on the physical phone. Walking
is a scripted rehearsal target, not live vision feedback. No hardware was moved
or calibrated during verification. No new aiming-error playback gate was added.
Automatic AI Director dispatch into these presets is a later integration.
