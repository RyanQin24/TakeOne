# From simulator movement to a supervised cart-only test

**Current operator-requested command, 12 September 2026:** use `prepare --command 0.05 --duration 2` for an explicit equal-command trial. The new command-test plan records its intent separately from a simulator shot. The existing response model still uses the provisional `0.04` / `0.1375 m/s` association; this request is not a new speed calibration. Live commissioning permits `0.04` for at most four seconds and `0.05` for at most two seconds. The current direction is forward, with the large powered wheels intended to lead. Both supported arm holds passed and left torque off; cart-only testing keeps both arms mechanically supported and sends no arm commands. Recreate plans after this source/configuration update.

**2026-09-12 drift audit:** the user reports real drift with equal packets. Equal commands are not a straightness guarantee. The [audit and measurement guide](cart-audit-2026-09-12.md) documents the axle math, current reverse direction, independent wheel-response model, non-actuating `analyze-drift` command and UART resolution limits. `commissioning_equal_commands_only` describes the actual software constraint. The sender now yields throughout its early-wake guard; it does not busy-spin.

The software now calculates a finite cart command schedule and can replay it through a deadline-based sender. This is open-loop commissioning, not proof that the real cart follows the simulated pose. No hardware was actuated while developing this path. Arms are excluded entirely and must be supported in a stationary configuration during a physical cart test.

## What is known and what remains to measure

The user reports 19 cm diameter / 6 cm width wheels, minimum moving command magnitude 0.04, caps ±0.15, and **60 ms without a motor command activates failsafe runaway brakes**. The approximate 55 cm in 4 seconds was provisionally associated with equal +0.04 commands. The configured reverse run assumes the same speed magnitude for equal -0.04 commands; that directional response has not been measured. Track width 0.58 m, axle offset 0.27 m, speed symmetry, response, braking and no slip are still assumptions. The watchdog report is recorded in `configs/cart-runtime.json` with source attribution; the measured qualification flag is not automatically set.

A zero-speed packet and watchdog-triggered braking may have different behavior. Confirm firmware version, when its timer resets (complete valid packet?), brake release/latching behavior and actual stop distance. Host serial writes are not firmware acknowledgements. A 60 ms timeout does not mean the cart is physically stationary 60 ms later. Test watchdog behavior only through a separate supervised procedure; this software never deliberately starves commands during a live motion test.

## Calculation, not a hardcoded motion script

The path is settings / current simulator export → existing differential-drive prediction → immutable timed cart plan → scheduler → existing UART transport.

`configs/rig.json` contains the single global setting `cart.reverse_enabled`. When it is `true`, the simulator, compiled cart plan and live-test schedule all use negative wheel commands. There is no separate CLI reverse flag and no second transport-level polarity inversion. The reverse simulation also mirrors the cart-relative arm sweep so subject tracking remains within the existing motion screens; it does not reverse the actor cue timeline.

At the powered axle midpoint, for forward speed v, yaw rate w and wheel spacing b:

```
left wheel speed  = v - w*b/2
right wheel speed = v + w*b/2
```

Wheel angular speeds are wheel linear speeds divided by the 0.095 m radius. UART values are controller commands, not wheel RPM or watts. The current provisional inverse map is `command = wheel_speed * 0.04 / 0.1375`. The shared simulator formats that to two decimal places, applies the cap and predicts the motion produced by the actual wire values. Paths that fail that quantized prediction are rejected by the cart planner. Small differential commands can produce appreciable turning; a smooth drawn path is not automatically commandable.

`prepare_cart()` reuses those equations, and `cart_from_shot()` checks the exported `motorCommands` against that calculation. The host does not translate screenshots, copy UI wheel rotations or infer a route from pixels. The initial simulation pose is a reference frame; it does not localize the real cart. Physically align the cart's travel axis with the floor test line before starting. Replay reproduces command timing, not guaranteed metres of travel.

Plans bind settings, the complete schedule and source/configuration hashes. Loading re-calculates and rejects edited or stale plans before connecting. Source/config changes require preparing/reviewing a new plan; restart the simulator before exporting after a code change. The live runner executes one finite plan once. It never reconnects or resumes after a fault.

Do not hand-edit a generated plan to change direction. Change `reverse_enabled`, restart the relevant Python process, and prepare a new plan. A valid newly generated JSON plan loads normally; an old or manually modified plan intentionally fails closed as stale.

## Timing and the 60 ms watchdog

| Setting | Current policy | Meaning |
|---|---:|---|
| Firmware timeout | 60 ms | User-reported loss-of-command brake trigger |
| Command period | 20 ms | Target 50 Hz, independent of the UI and AI |
| Sleep wake guard | 10 ms | Wake before the deadline to absorb ordinary Windows sleep overshoot |
| Maximum dispatch lateness | 10 ms | Abort on an overdue cycle; do not catch up nonzero commands |
| Maximum host start-to-start gap | 40 ms | Abort threshold below the firmware timeout |
| Serial write timeout | 5 ms | Avoid the previous 100 ms write timeout exceeding the watchdog |
| Startup / shutdown zero windows | 100 ms each | Repeated explicit zero requests; not a physical-stop acknowledgement |

Configuration must satisfy `period + lateness + write_timeout < host_gap_limit < watchdog`. The sender preserves every compiled command boundary and inserts keepalive deadlines at `segment_start + tick*period` if an interval is longer than the configured period. All deadlines use one monotonic epoch, so serial work does not accumulate into each sleep interval. It sends the command for current elapsed time, stops at the finite end deadline, and aborts on clock regression, late dispatch, slow/partial writes or cancellation. No high-rate catch-up burst and no separate thread that keeps a stale motion alive. Host timestamps and successful writes cannot bound USB/firmware queues; measure controller-side receipt timing during qualification. Do not add a blocking flush to the timed loop.

The runner is a dedicated CLI process with no video/AI/UI work in its timed loop. For real-clock timing and live-test modes on Windows, it temporarily requests above-normal process priority and highest thread priority, never real-time priority, and restores the original values afterward. It wakes 10 ms early and remains runnable until each absolute deadline; virtual replay does not use this path. These measures reduce ordinary host scheduling jitter but do not make Windows/Python hard real time. A stalled process cannot execute its software stop; the reported firmware watchdog and physical abort arrangement remain independent mechanisms. On a detected software fault, only zero requests are attempted and the run remains faulted.

## Commands from any working directory

Use a separate PowerShell window. All commands below except `live-test` are non-actuating.

From `C:\Users\nonst\Documents\Python\TakeOne_Astra\TakeOne`, use the dedicated robot environment to prepare the current two-second forward command experiment. It uses the shared wheel-response model to predict movement while preserving the exact requested commands. The output must not already exist:

```powershell
& '.\lerobot\.venv\Scripts\python.exe' -m takeone.cart.cli prepare --command 0.05 --duration 2 --output '.\data\cart-forward-005-2s.json'
& '.\lerobot\.venv\Scripts\python.exe' -m takeone.cart.cli replay --plan '.\data\cart-forward-005-2s.json'
& '.\lerobot\.venv\Scripts\python.exe' -m takeone.cart.cli timing --plan '.\data\cart-forward-005-2s.json'
```

`replay` uses virtual time and memory transport; `timing` uses real wall time and memory transport. Both write evidence to a new `data/runs/*-cart-*/` directory. A successful timing run excludes USB and firmware latency. Repeat timing under the intended computer workload before hardware testing. A failure is useful evidence: investigate host scheduling; do not widen budgets past the watchdog.

To use the exact cart portion of a current simulator export:

```powershell
python -m takeone.cart.cli prepare --shot '.\data\exported-shot.json' --output '.\data\cart-from-shot.json'
```

This does not execute the arms and does not transfer their feasibility status to the cart. The initial live-test envelope rejects the default nine-second shot; prepare/recompile a shorter shot. Changing the duration of an imported export is rejected rather than silently changing its timing.

## Physical commissioning, explicitly operator initiated

Before running: identify the correct USB adapter and COM port, arrange a physical abort, support/secure both arms and payload, align the wheel travel direction with a marked clear test area, and reserve room for unmeasured braking. This is a low-command measurement experiment. It does not require pretending that speed and stopping have already been calibrated.

Install the optional pinned UART dependency if absent:

```powershell
python -m pip install -e '.[uart]'
python -m takeone.cart.cli ports
```

The port inventory opens no motor ports. Match the physical cart adapter to its USB serial. If it has no unique serial, stop and establish another reviewed identity mechanism; this workflow does not guess based on COM5 alone.

After the physical setup is checked, the operator can initiate the test:

```powershell
& '.\lerobot\.venv\Scripts\python.exe' -m takeone.cart.cli live-test --plan '.\data\cart-forward-005-2s.json' --port COM5 --usb-serial 'REPLACE_WITH_CART_USB_SERIAL' --operator-ready --execute
```

`--operator-ready` attests that the identity, supported arms, clear test area and physical abort procedure have been checked. It is not a calibration certificate. COM5 is the user-supplied example, and must match current device identity. The command requires both opt-in flags and matches the port/serial before opening. It accepts only equal two-decimal commands in the globally configured direction, at magnitude 0.04 for at most four seconds or 0.05 for at most two seconds. These are commissioning limits based on the supplied test and explicit operator request, not measured safe-motion limits. Broader motion needs a measured-response workflow and reviewed limits; changing the direction setting does not widen the envelope.

Ctrl+C requests shutdown zeros when Python can handle the interrupt; it is not the physical emergency stop. Zero write failure is recorded, not swallowed as a successful stop. There is no firmware receipt acknowledgement in the supplied protocol.

## What to measure and what comes next

Record start time, travel from rest, heading drift, timing of final zero, time/distance to rest, payload/floor and repeated-trial variation. Compare the provisional prediction (0.55 m over four seconds) with actual measurements; do not treat that prediction as the pass criterion without an agreed measurement tolerance. Record command gaps at firmware receipt where possible. Verify zero behavior and watchdog braking separately before expanding motion.

Next replace the provisional symmetric speed map with measured per-wheel, direction-aware response data, including deadband and transient effects. Add actual encoders or calibrated camera localization for feedback, then a controller that corrects path error. Extend beyond straight commissioning only after measured turns and stopping pass. The mathematics already separates v/w, wheel speed and wire commands; the missing piece is the real transfer function and observed cart state, not another hardcoded speed loop.

Combined cart-and-arm replay remains blocked by original calibration, joint-to-model mapping, loaded limits, start/stop transitions and the outstanding full tool-position residual issue recorded in [the architecture review](architecture-review-2026-09-12.md).
