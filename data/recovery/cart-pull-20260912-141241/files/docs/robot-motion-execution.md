# Simulator-to-robot motion execution

The product now prepares and executes **one finite timeline for the cart, phone arm and light arm**. It lives in `packages/takeone`, works without the website, and includes an explicit LeRobot motor-bus driver. A live failure never switches to simulated feedback.

Software execution is implemented. Physical tracking is **not yet qualified**: original calibration files are missing locally; both derived alignment files and loaded motion envelopes remain unverified. No motor, torque, firmware or calibration setting was changed during implementation.

## What following the simulator means

Preparation preserves every solved five-joint phone/light pose in reference-model radians and every quantized cart command. It checks imported preview joints against a fresh solution before accepting them. A content digest and source/configuration/calibration/model hashes bind the artifact. Playback runs neither IK nor AI inference.

The executor interpolates joint angles linearly and dispatches at 25 Hz plus the exact endpoint. The cart retains its separate 20 ms schedule. The renderer's interpolated body poses between knots are an approximation; the explicit joint timeline is the execution contract. Encoder resolution also quantizes physical angles. Literal zero-error, zero-delay motion cannot be promised.

Each encoder reading is compared with the planned angles at its monotonic acquisition timestamp. Reports distinguish planned angles, transmitted targets and measured/simulated observations. Per-joint tracking error and final settling must meet explicit tolerances. Encoder agreement does not prove lens position, structural flex, cart position, clearance or acting performance.

## Control and failure behavior

1. Validate the plan and current source hashes. Check every source segment and dispatched target against role-specific range, velocity, finite-difference acceleration and step limits. There is no clipping, angle wrapping or automatic retiming.
2. Live execution requires the existing qualification gates, original calibration hashes, verified signs/zeros/tool transforms, loaded operating limits and USB identities. Phone wrist roll stays motor **6**; light wrist roll stays motor **5**.
3. A separate process owns each serial bus. The arm driver opens only the motor bus, checks attached calibration, position mode, existing torque state and angle mode, and writes only `Goal_Position`. It never calls follower `configure()` or `calibrate()`.
4. Both measured starting poses must already match the reviewed first pose within tolerance. A mismatch sends no arm positioning command and permits no nonzero cart command. Supported initial positioning remains a separate supervised setup procedure.
5. All schedules start from one agreed monotonic epoch. Cart zero packets continue while waiting. Short leases are renewed only after successful device work; a background timer cannot fabricate arm health.
6. Stale feedback, tracking error, missed dispatch, write failure, lost workers or an expired supervisor lease cancel the whole run. The cart attempts its logged zero window. Each arm requests a hold only at a sufficiently fresh observed position; otherwise it retains its last target and reports stopping unconfirmed. Torque is never dropped automatically. An unresponsive driver gets bounded cleanup time before its process is terminated; process termination is not a mechanical stop.
7. Normal completion requires cart zero and a stable final observation window for both arms. Logs are written after leaving the control loops. A faulted run cannot restart itself.

Windows/Python is not hard real time. The user's **60 ms cart firmware watchdog** remains independent protection against lost UART packets. The host budget remains 20 ms period + 10 ms lateness + 5 ms write < 40 ms host gap < 60 ms watchdog. The separate 100 ms arm lease bounds the age of successful arm work; it is not a cart packet interval. Worst-case USB/OS latency and actual stopping distance still need measurement.

## Use it without connecting hardware

In the simulator, recalculate/review the shot and select **Prepare robot motion** under Shot Settings. It downloads the complete plan and displays physical-execution blockers. Editing settings disables preparation until recalculation. There is no web endpoint that actuates hardware.

These commands also work from another working directory:

```powershell
C:\TakeOne\.venv\Scripts\python.exe -m takeone.motion.cli prepare --output C:\TakeOne\data\verification\robot-motion-plan.json
C:\TakeOne\.venv\Scripts\python.exe -m takeone.motion.cli preflight --plan C:\TakeOne\data\verification\robot-motion-plan.json
C:\TakeOne\.venv\Scripts\python.exe -m takeone.motion.cli replay --plan C:\TakeOne\data\verification\robot-motion-plan.json
C:\TakeOne\.venv\Scripts\python.exe -m takeone.motion.cli timing --plan C:\TakeOne\data\verification\robot-motion-plan.json
```

Use `prepare --shot <export.json> --output <plan.json>` for an existing simulator export, or `prepare --settings <settings.json>` for another configured shot. Source/configuration changes invalidate older exports.

`replay` uses virtual time and a lagging simulated arm plant to test numerical tracking and settling. `timing` uses real host time and three processes with simulated devices. It measures scheduling, not real USB or motor response. `scripts/TakeOne.ps1 -Command dry-run` now uses the same prepared-plan replay service.

Every run retains `data/runs/<timestamp>-robot-<id>/plan.json` and `report.json`. Process runs also retain `phone.json`, `light.json` and `cart.json`, with target/feedback traces and maximum joint errors. An absent or unreadable worker report fails the run.

## Qualify physical playback

Follow the [hardware runbook](hardware-test-runbook.md), [calibration inventory](calibration-inventory.md) and [cart commissioning guide](cart-live-testing.md). Preserve original calibration bytes. Do not enable qualification booleans merely to dismiss a warning.

For each arm, complete `calibration/derived/<role>.json` with measured signs, zeros, safe ranges, verified tool transform and reference hash. In `configs/arm-execution.json`, complete `live_limits.<role>` with:

- `verified`, `mapping_sha256`, a workspace-relative `evidence_path`, and `evidence_sha256`.
- `limits`: five-element arrays named `velocity_rad_s`, `acceleration_rad_s2`, `step_rad`, `initial_tolerance_rad`, `tracking_tolerance_rad` and `final_tolerance_rad`, in the plan's explicit joint order.

These must come from loaded measurements with the installed phone/light and cable routing. Acceleration screening uses finite differences of setpoints, not a torque model. A numerical pass does not qualify the default continuous shot's physical start/stop behavior. The existing combined-start/stop, payload-support and independent-stop gates remain required.

Live runtime uses the established LeRobot environment with TakeOne installed editable, preserving that environment's dependencies. The explicit supervised command is `python -m takeone.motion.cli live --plan <reviewed-plan.json> --profile windows --confirm-plan <full-reviewed-plan-id> --operator-ready`. This command is never an automated test. The Linux interface is implemented but has not been hardware-tested here.

The bus must already be correctly configured and torque-enabled by the supervised setup procedure. The driver rejects a mismatch and closes with `disable_torque=False`. It neither initializes torque nor releases a payload after a run; use the established physical support and stop procedure.

## Architecture and recovery mapping

The previous synchronous `Executor.apply` sent both arm targets followed by a cart packet, without complete-plan playback or measured tracking acceptance. It has been replaced, not retained as a live fallback.

| Previous source/behavior | Current owner |
|---|---|
| `execution.py::Executor`, per-frame batch API | `execution.py::RobotRunner`, isolated device owners and shared start |
| CLI `dry_run`, hand-built motion frames | `motion.service.execute_plan` and `motion.plan` |
| `adapters/lerobot_arm.py`, borrowed follower | Same module, one owned, read-verified LeRobot motor bus |
| `adapters/fake.py`, instantaneous fake feedback | `adapters/simulated.py`, lagging test plant and virtual time |
| Cart CLI's embedded transport/clock and USB helper | Shared `adapters/simulated.py` and `adapters/identity.py` |
| Old synchronous executor tests | `tests/test_robot_motion.py`, plan/driver/tracking/process fault tests |

Prior unique source/tests are recoverable from root commit **`0da7950d79df5cf777da41f1decdfb64bacd7365`**, for example `git show 0da7950d79df5cf777da41f1decdfb64bacd7365:packages/takeone/execution.py`. The independent LeRobot checkout was not edited. The standalone cart commissioning API retains its narrower test envelope.
