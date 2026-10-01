# Powered front wheels and passive rear casters

The user confirmed: swap the wheel ends and keep the upper arms in place. The model now has the two 19 cm diameter, 6 cm wide powered wheels at the front and the small unpowered swivel casters at the rear. All three light variants use this layout.

## Frames and geometry

The upper/cart frame is preserved. Cart +Y points toward the filming subject; cart -X points toward the powered front wheels. Drive +X is cart -X, drive +Y is cart -Y, and both frames are Z-up. Thus drive heading = cart yaw + pi. Driver-left/right refer to looking toward the powered front.

| Component | Before in cart frame | After in cart frame |
|---|---|---|
| Powered axle midpoint | x = +0.27 m | x = -0.27 m |
| Rear caster swivel pivots | opposite end | x = +0.32 m |
| Powered left/right centers | previous side mapping | (-0.27, -0.29, 0.095) / (-0.27, +0.29, 0.095) m |
| Upper mounts, uprights, deck and arms | original saved transforms | unchanged |

Wheel size is user supplied. Track width, axle offset magnitude and caster dimensions are estimates. The rear caster wheel trails its swivel pivot by 0.025 m in nominal straight travel. Its radius is 0.047 m and width is 0.036 m; these visual dimensions are not measured. The model gives casters no motor actuator. Their rendered swivel direction follows the local pivot velocity, including reverse; drag and swivel transients are not modeled.

## Movement and shot placement

Differential-drive integration uses v = (vL + vR)/2 and omega = (vR - vL)/track at the powered axle. The signed axle-to-cart transform, driver-left/right mapping and rendered wheel rotation were updated together. The raw UART encoder, physical polarity configuration, command limits and watchdog timing were not changed. Positive commands predict movement toward the powered end; physical wiring still needs verification.

Swapping the axle while retaining an axle-centered shot also shifts the upper cart's world path. The first corrected forward trajectory exposed aiming and motion-limit failures. Those failures were retained while correcting the requested placement: the straight dolly now specifies its **cart-center** midpoint through `dollyOffset` (world Y, default 0.40 m). Axle placement is derived from that value and the signed geometry. The setting is visible in the simulator and belongs to shot intent, not calibration. No IK limits, aiming tolerances or motion thresholds were weakened.

The resulting 9-second default uses equal 0.04 commands, predicts 1.2375 m wheel travel, zero base yaw, 51.1 degrees of phone pan and 39.8 degrees of light pan. Phone sweep/lift requests remain 0.16/0.04 m; light requests remain 0.12/0.03 m. The estimated payload margin still fails, so this remains a preview rather than a hardware-qualified shot.

## Evidence and reproduction

- [Generated movement proof](../apps/rehearsal/DRIVE-PROOF.md) and [numeric evidence](../apps/rehearsal/verification/drive-proof.json).
- All 26 simulation tests passed. Every upper-body pose and structural geometry entry matches the preserved `tests/fixtures/upper_before_rotation.json` within 1e-12; maximum upper-body position change is 0 m.
- Tests independently check actual wheel centers/axes, ground contact, driver-left/right roles, forward/reverse/arc/spin contact velocities, passive caster alignment and adjustable track width. Fifty randomized wheel traces also agree with a separate numerical ODE solver within 1e-9 tolerance.
- The ring, panel and tube GLBs were regenerated and imported by the web tests; all have powered-front/rear-caster positions and meter-scale dimensions.
- The served simulator was opened and played at `http://127.0.0.1:8768/`. It displayed zero base turn, 51.1/39.8 degree arm pans, a correctly framed simulated camera and the corrected wheels. No physical device was used.

From another working directory, invoke `C:\TakeOne\scripts\TakeOne.ps1 -Command test`. Regenerate models with the root environment's `python -m takeone.simulation.model`, then `node C:\TakeOne\apps\rehearsal\export_models.mjs`. Regenerate the proof with `C:\TakeOne\.venv\Scripts\python.exe C:\TakeOne\apps\rehearsal\verify_drive.py`.

Source ownership remains the same: configuration in `configs/rig.json` and `configs/shots/arm-led.json`, geometry/odometry in `packages/takeone/simulation`, settings in `packages/takeone/planning/settings.py`, rendered animation in `apps/rehearsal/dist/robot-model.js`. Earlier geometry and source are recoverable from baseline commit `8e3bf62abd90f9789224e503fe0e101fcf56c56e`; compare individual files before any recovery and preserve later user changes.
