# Front powered-wheel cart: pull, math audit and drift diagnosis

The `main` checkout was fast-forwarded from `0da7950` to `3d4cd5bf17b96c5ff8aa9b77d55a9577fded01eb` (`Add global reverse cart direction`). Local Director and coordinated arm work was restored. One overlap in the cart runner was resolved by retaining the arm health/heartbeat hooks and the incoming reverse-command behavior. Nothing was pushed. No motor port was opened or hardware actuated during this audit.

**The real cart's straightness is not yet established.** The user reports drift with equal commands. Its direction, magnitude, individual wheel response, firmware control mode and stopping behavior have not been measured here. The software changes expose and support diagnosing that problem; they do not fabricate calibration or feedback.

## Findings and changes

| Finding | Consequence | Change |
|---|---|---|
| Front powered-wheel geometry and axle math agree with independent rolling/ODE checks | No evidence that swapping ends introduced a kinematic sign error | Preserve the geometry, left/right convention and unchanged upper assembly |
| `reverse_enabled` changes the requested path and signed packets | Negative packets are not proof of physical travel toward the large wheels | Preserve incoming `-0.04,-0.04`; expose actual commands and physical polarity uncertainty |
| Both motors were assumed to have the same speed response | Equal packets were guaranteed to look straight in the simulator even if the hardware drifts | Add explicit provisional or independent measured-table response modes used by simulation and plan preparation |
| UART values are rounded to two decimal places | Small trims at 0.04 may vanish; a reduction to 0.03 falls below the reported moving threshold | Predict from the actual rounded packet and reject infeasible paths; report whether a drift-trim hypothesis changes that packet |
| Runner spins for up to 10 ms every 20 ms | About half a CPU core was consumed in the measured baseline | Yield during the early-wake guard; retain absolute deadlines, late-dispatch faults and the same watchdog margins |
| Priority treatment was applied only to cart-only playback | Coordinated arm/cart playback had a different host scheduling policy | Apply the same scoped priority policy to the independent cart worker and restore it on exit |
| Code/config hashes were read from disk while some constants were cached at import | A long-running process could identify old logic with new source hashes after a pull | Refuse plan provenance if process-captured code/drive settings changed; require a restart |
| UI described positive commands and left-to-right arm sweep after reversal | Displayed explanation disagreed with the trajectory | Show the compiled packet and describe the planned sweep direction; state the missing feedback |
| Commissioning called equal packets “straight” | A command constraint could be mistaken for a measured physical result | Rename the policy to `commissioning_equal_commands_only`; report straightness as unverified |
| A repeated integration run exposed a Windows HTTP reset on rejected POSTs | A caller could lose the intended 403/415 response | Consume only the bounded request body with a timeout before rejection; leave authorization and mutation checks intact |

## Frames and equations

The existing upper cart frame is unchanged: cart +Y is the filming side. Drive +X points toward the large powered front wheels, which is cart -X. Drive +Y is driver-left, which is cart -Y. Driver-left/right **do not exchange when driving in reverse**. The two small rear casters have no motor commands.

Powered wheel centers are cart `(-0.27, -0.29, 0.095)` on the driver's left and `(-0.27, +0.29, 0.095)` on the driver's right. Radius is 0.095 m, width 0.06 m. The 0.58 m center spacing and 0.27 m axle offset remain estimates.

At the powered axle midpoint, with signed ground speeds `vL`, `vR` and center spacing `b`:

```text
v = (vL + vR) / 2          omega = (vR - vL) / b
vL = v - omega*b/2        vR = v + omega*b/2
dx/dt = v*cos(heading)    dy/dt = v*sin(heading)
```

These equations hold for front or rear driven axles and for forward/reverse travel. Merely reversing both commands changes the motion direction; it does not eliminate a wheel-speed difference. Wheel radius converts linear wheel speed to rad/s. Tire width is geometry/contact information, not a multiplier in differential-drive kinematics. Casters can cause load-dependent drag and startup transients that this kinematic model does not identify.

The cart-center pose is the axle pose minus the rotated **signed cart-frame axle offset**. A point on the chassis can move laterally while the wheel contacts satisfy no sideways slip. The test suite checks contacts individually, rather than incorrectly requiring zero lateral velocity at the offset chassis center.

For a measured constant-command trial with signed **axle arc length** `s` and signed heading change `delta_theta`:

```text
left wheel travel  = s - b*delta_theta/2
right wheel travel = s + b*delta_theta/2
average wheel speed = wheel travel / measured interval
```

This inference assumes rolling without slip. Straight-line displacement between endpoints, a mark on the cart's rear deck, or an unsigned tape measurement is not the same input. A measurement starting from rest yields an average including the startup transient; it must not be relabelled steady-state speed.

## Why a small trim may not fix it

A synthetic example makes the limit explicit: left speed `-0.1375 m/s`, right speed 2% faster, a four-second hold, and assumed `b=0.58 m` produce about **1.09 degrees of heading change**. This is a mathematical witness, not a measurement of this cart. The simulator now rejects that modeled request at its existing one-degree heading tolerance.

`-0.04 * 0.98 = -0.0392`, but the supplied formatter still transmits **`-0.04`**. The next smaller magnitude, `-0.03`, is below the reported moving threshold. Choosing a larger correction, pulsing a wheel off, or changing serial precision without knowing the firmware is not a justified repair. The audit does none of those.

For corrections smaller than the usable wire steps, establish the actual firmware command interpretation/resolution and wheel feedback. A local firmware velocity controller with encoder measurements is the appropriate place for fast wheel-speed regulation; host pose/heading feedback can then correct trajectory drift. A language model is not needed in either control loop.

## Operator measurement workflow

Existing supervised cart commissioning remains bounded to four seconds, the minimum command magnitude and equal packets in the configured direction. Those constraints do not assert that the cart drives straight. Keep the existing runbook's physical supervision and abort procedure. This audit does not expand the live motion envelope.

1. Confirm which physical wheel each UART column controls and what signed command moves it toward the large-wheel front. If negative packets move physically forward, that is a polarity mapping to document, not evidence that model-negative travel is forward. Do not swap left/right to compensate for driving backwards.
2. Record repeated trials with the same load/floor, initial caster alignment and command. Record whether drift is mainly at startup or continues throughout the hold. Measure powered-wheel center spacing. Prefer independent wheel encoders or external pose observations.
3. Copy the empty [drift measurement template](templates/cart-drift-measurements.csv) into `data/measurements/` and add actual measurements. `axle_travel_m` is signed arc length in the drive frame; `heading_change_deg` is positive counterclockwise viewed from above. State measurement methods, geometry uncertainty, load/floor and start/stop conditions in `source` and `conditions`.
4. Run the non-actuating analyzer from any working directory:

```powershell
& 'C:\TakeOne\.venv\Scripts\python.exe' -m takeone.cart.cli analyze-drift --measurements 'C:\TakeOne\data\measurements\cart-drift.csv' --output 'C:\TakeOne\data\measurements\cart-drift-report.json'
```

The output contains the exact input hash, inferred wheel travel/speed difference, polarity consistency and a **diagnostic-only** proportional trim hypothesis before/after UART rounding. It never activates that hypothesis, edits calibration or opens a port. It rejects duplicate IDs, malformed measurements and an existing output file. If measuring axle arc length is impractical, collect independent encoder or externally localized wheel/axle data rather than substituting chassis displacement.

## Independent wheel response in the real planning path

`configs/cart-response.json` currently selects `provisional_symmetric`, explicitly recording the missing measurements and reported real drift. No measured table or trim has been invented.

After verifying polarity and recording **steady, loaded** response data, a reviewed profile can select `measured_table`. Its exact fields are `schema_version`, `mode`, `evidence`, and `wheels`. `wheels.left` and `wheels.right` contain sorted lists of `{ "command": <actual signed wire command>, "speed_m_s": <signed ground speed> }`. Evidence identifies the measurement files/trials, conditions and uncertainty. Positive speed/command use the verified drive-forward convention. The table is not a wiring adapter; resolve any inverted physical polarity before using it.

The model enforces finite, monotonic, two-decimal points inside the existing 0.04–0.15 moving magnitude range. It interpolates within each measured direction, never assumes reverse symmetry or extrapolates past measured points. Below the lowest measured speed it can predict only stop or the lowest measured moving speed; it cannot invent a low-speed response through the deadband. Missing/invalid data is an error, not a fallback to the provisional model.

The simulator and cart compiler use the same table inversion, **then** UART formatting, **then** forward prediction from those transmitted values. Arm targets are solved against the resulting chassis prediction. Changing a profile invalidates prepared plans. Restart the simulator and prepare a new plan. Broader live execution remains subject to existing qualification; a table alone does not qualify the robot or override the equal-command commissioning envelope.

## Timing and reproducible evidence

The 20 ms target, 10 ms lateness limit, 40 ms host-gap limit, 5 ms write timeout and user-reported 60 ms watchdog are unchanged. The margin remains `20 + 10 + 5 < 40 < 60 ms`. Failures fault the run and attempt zeros; there is no stale-motion keepalive, reconnect, catch-up burst or automatic resume. Both fields are sent in one serial packet. A left/right difference is not introduced by sequential host wheel writes.

The measured four-second baseline consumed **1.984375 CPU seconds over 4.206513 wall seconds (47.17% of one core)**. After replacing the spin, the first comparison consumed **0.125 CPU seconds over 4.201256 wall seconds (2.98%)**, with **20.54 ms maximum observed host gap** and **0.7285 ms maximum lateness**. That is about a 94% reduction in CPU use for that comparison. These are local observations, not universal latency or efficiency guarantees. Windows/Python cannot guarantee hard real time, and USB/firmware receipt is outside this measurement.

Raw baseline and initial comparison are in `data/verification/cart-audit-before-timing.json` and `cart-audit-after-timing.json`. To generate fresh repeated evidence without opening a motor port:

```powershell
& 'C:\TakeOne\.venv\Scripts\python.exe' 'C:\TakeOne\scripts\verify_cart_audit.py' --runs 3 --output 'C:\TakeOne\data\verification\cart-audit-timing-new.json'
& 'C:\TakeOne\scripts\TakeOne.ps1' -Command test
& 'C:\TakeOne\.venv\Scripts\python.exe' 'C:\TakeOne\apps\rehearsal\verify_drive.py'
```

The timing artifact records current source hashes, per-write deadlines, CPU use, p99 lateness, faults and an explicitly synthetic imbalance witness. Routine reports are written after the timed loop; planning, IK, UI, network calls and model inference stay outside it. No additional runtime dependency or paid model service was added.

Final verification passed **132 product tests, 28 simulation tests and 12 web tests (172 total)**, both Ruff checks and the preservation audit of **1,092 LeRobot files**. The complete root check was also run from `C:\`, outside the project working directory. The first full pass found only a formatting issue; a subsequent run exposed the HTTP reset described above. Both were corrected before the final all-green run. Logs are in `data/verification/cart-audit-full-tests.txt` and `summary.json`.

Three further four-second host trials in `data/verification/cart-audit-timing.json` all passed: CPU use was **1.12%, 1.86% and 2.98% of one core**; maximum observed host gaps were **20.67, 20.61 and 20.61 ms**. Maximum lateness across those trials was **0.752 ms**. Yielding trades some sub-millisecond dispatch precision for substantially lower CPU use while remaining inside the unchanged tested host budget. It is not a hard real-time guarantee.

The refreshed rehearsal preview is served at `http://127.0.0.1:8770/`. The page, JavaScript, Director page, health endpoint, current shot and movement proof all returned HTTP 200. The served app JavaScript matches the workspace file hash, and the shot reports `-0.04,-0.04`, reverse direction, the explicit provisional response profile and the unchanged robot model hash. Only the previously started preview on port 8770 was restarted; the other cart-testing previews were left running. Old processes must be restarted before they can use the pulled/new planning logic.

## Source mapping and recovery

The 47 locally changed/new/deleted paths were captured with byte hashes under `data/recovery/cart-pull-20260912-141241/`, including `local.patch`, `files/` and `manifest.json`. The Git stash titled **TakeOne local Director and robot motion before cart pull 2026-09-12** remains available. The saved patch is relative to the pre-pull commit; applying it over current work is not a restore procedure. Inspect it, or recover individual files into a separate location for comparison. Do not blindly reapply the stash or discard current work.

| Before | After |
|---|---|
| Symmetric command-to-speed calculation in `simulation/drive.py::wire_speed` | `cart/response.py` owns the single explicit provisional/table implementation; `drive.simulate` consumes it |
| No measured drift analyzer | `cart/diagnostics.py`, CLI `analyze-drift` and the empty CSV template |
| Busy-spin guard plus cart-only priority wrapper | Yielding `CartRunner` wait and scoped priority in both execution entry points |
| On-demand disk provenance alone | Process-input comparison before accepting provenance |
| `commissioning_straight_only` | `commissioning_equal_commands_only`, with physical straightness explicitly false |
| Stale direction text in the UI | Actual compiled packet, planned sweep direction and missing-feedback status |
| Rejected POST could close with unread bytes | Bounded body consumption before non-mutating rejection in `apps/rehearsal/server.py` |

LeRobot, calibration originals, firmware, arm mappings, torque and robot geometry were not edited. Existing Director and coordinated arm work remains local and uncommitted. The only removed function was the obsolete duplicate symmetric speed helper; its implementation and callers are preserved in the recovery snapshot and Git history.

## Reference checks

The axle equations agree with [WPILib differential-drive kinematics](https://docs.wpilib.org/en/stable/docs/software/kinematics-and-odometry/differential-drive-kinematics.html). [ROS differential-drive control](https://control.ros.org/rolling/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html) distinguishes command-based odometry from measured wheel feedback and provides separate wheel-radius correction parameters. [Python's timing documentation](https://docs.python.org/3/library/time.html#time.sleep) describes the monotonic clock and Windows waitable-timer behavior, while explicitly allowing scheduler delays. These references support the model and timing boundaries, not unmeasured physical calibration.
