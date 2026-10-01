# Landscape filming start

Verified 2026-09-13 in `C:\TakeOne` at `http://127.0.0.1:8766/`.

The phone arm now starts filming with the physical handset held horizontally.
Both arms first retain their exact calibrated reset counts, then aim while the
cart is stationary. The prepared robot plan and world model use the same joint
goals. Intentional roll starts from landscape and follows the shot afterwards.

## Before and after

The old optical frame used the short handset edge for image width. Zero-roll IK
therefore placed the long handset edge vertically. The corrected optical frame
uses the long edge for image width and retains the lens origin and forward ray.
No handset remount, joint-axis change or calibration revision was made.

The default static shot's planned phone wrist-roll goal changed from 1055 to
2079 counts, using motor ID 6. Its calibrated reset remains 2047 counts. The
new handset long edge is 0.020 degrees from horizontal in simulated FK of the
planned motor values. See `static-pose.json`; this is software evidence, not a
physical encoder observation.

| Source | Change |
| --- | --- |
| `simulation/model.py` and three generated rig XML files | Portrait optical basis becomes a landscape basis; geometry, lens origin and forward direction stay fixed. |
| `previs/compiler.py` | Try both wrist-wrap directions for the initial phone solve and prefer continuous phone postures during movement. Light solving retains its previous weighting. |
| `previs/path.py` | Solve arms independently; work backwards from the neutral end of an upward tilt to select its starting pose. Matching loop endpoints reuse the first exact encoder goals. Shot durations and motor-rate limits are preserved. |
| `previs/camera.py` | Advertise landscape output and pin the final zoom point despite floating-point clock rounding. |
| `apps/rehearsal/dist/index.html` | Label the phone profile as Landscape. |
| Exported GLBs | Regenerated using the existing exporter after updating the canonical models. |

## Verification

- **68 Python tests passed** in `python-tests-verified.txt`: camera, all 28 movement presets, drawn path, original orbit, reveal choreography, and robot-playback contracts with fake devices.
- The new all-preset assertion decodes the player's raw arm goals and checks the actual handset's longest geometry axis at filming start. It also verifies unchanged calibrated reset counts and zero cart commands during setup.
- Ring, panel and tube model variants share the corrected phone width axis and unchanged lens position/forward direction.
- Existing checks still pass for aim, named pan/tilt/roll directions, camera height movement, wheel packets, raw-goal/FK parity, zoom, saved-shot round trips and cached lens edits.
- **177 frontend tests passed** in `frontend-tests.txt`.
- Targeted Ruff lint/format and changed-source whitespace checks passed.
- The root PowerShell test launcher was attempted but blocked by this computer's unsigned-script policy. The policy was not changed. The completed checks above ran directly; the full repository suite is not claimed to pass.
- Earlier Python logs record failures corrected during this feature. `python-tests-verified.txt` is the final result.

The live simulator was restarted after the final code change. The Static shot
was loaded in Rig view and left at 5.48 seconds, the start of filming. With
**Follow the phone's roll** selected, the phone is horizontal and the actor is
upright without output horizon correction. The profile displays
**iPhone 17 Pro Max · Landscape**.

No physical robot or iPhone was operated. No new arm-error stop threshold was
added. Existing saved shots use the corrected start when loaded and prepared
again. No GitHub push was performed in this feature.

Original files are preserved with their relative paths under
`data/recovery/landscape-start-20260913/`. The camera guide and root README explain
the new start behavior. Other task changes in the workspace were preserved.
