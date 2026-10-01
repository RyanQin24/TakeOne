# Feature 02: run the orbit on the robot

The simulator has a **Real robot** panel with **Prepare robot run**, **Run on robot**, and **Stop**. Ordinary **Play orbit** remains a preview. This feature runs locally on the Windows computer connected to the cart and both arms. Copy this repository's code to that computer; remote control between computers is outside this feature.

## Start on the robot computer

Use the existing simulator setup first (`scripts/Setup.ps1`) if this is a fresh checkout. From the checkout root:

```powershell
.\.venv\Scripts\python.exe scripts/setup_robot_runtime.py
.\.venv\Scripts\python.exe -m takeone.cli simulator --port 8766
```

Open `http://127.0.0.1:8766/`. The first command installs pinned motor-bus dependencies in `.runtime/robot/.venv`, separate from the simulator and the LeRobot training environment. It imports the drivers to verify installation and opens no ports. Both scripts resolve the project from their own location. `uv` and Python 3.12 or newer are required; the lock was resolved for Python 3.13.

The device profile is `configs/devices/windows.json`: cart **COM5**, phone **COM9**, light **COM8**, with their saved USB identities. Phone wrist-roll is ID **6**; light wrist-roll is ID **5**. Keep the robot computer's actual device profile and calibration originals when transferring code. An environment or process from the development computer is not transferred.

1. Place the cart and actor to match the preview's starting arrangement and radius.
2. Choose the orbit settings and click **Prepare robot run**. This calculates commands without connecting devices. The panel shows the robot duration before motion can start.
3. Click **Run on robot**. The player reads the current encoders, enables each arm on its present pose, waits two seconds, and resets both arms to their calibrated initial pose. It then aims both arms while the cart stays stopped, before starting the orbit. The preview includes the calibrated start and aiming sequence and follows the same clock. Settings and preview transport are locked during the run.
4. Click **Stop**, or press **Esc**, to end travel and retain the arms' last goals. Completion also stops the cart and leaves arm torque enabled. There is no automatic loop, release, reconnect, or restart. The existing explicit supported-release command remains available from the hardware launcher.

The panel controls the cart and both arms. Phone recording and physical lens selection remain manual. The camera monitor is a simulated view, not a live iPhone feed. Cart travel is timed open-loop; the displayed path is a prediction, not measured odometry. The browser sends a presence signal while it owns a run. Closing the page requests Stop; if its connection disappears, the worker stops dispatch after a five-second lease. The existing cart firmware watchdog covers loss of command traffic separately.

## Timing and commands

`motion/studio_plan.py` uses the orbit compiler's solved arm poses and the existing calibrated degree-to-count conversion. It compiles both wheel streams together at 20 ms boundaries. The existing hardware player resends the current cart command every 5 ms and streams both arm goals every 40 ms. It uses the configured transport polarity; it does not change wiring, firmware or calibration.

Wheel commands and the plan's `wire` strings are expressed in the logical drive frame, before transport polarity. The UART adapter applies the installed `cart-runtime.json` polarity, and the run report records that polarity. Encoder goals in `raw_by_role` are the exact integers sent to the named motors.

If the requested speed exceeds the configured `0.15` cart command cap, compilation extends the orbit and displays its duration before Run becomes available. The default 2.5 m, 360°, 20 s orbit becomes **51.0 s of travel + 5.84 s of aiming**. Resetting from the measured current pose to calibration happens before that clock and takes as long as the recorded travel requires at the existing approach rate. Both wheel schedules end in zero. Error diffusion selects valid two-decimal commands above the configured moving threshold or zero, keeping accumulated nominal wheel travel close to the requested circle. Low-speed easing can therefore contain stop/move pulses. The currently configured linear symmetric wheel response remains an assumption. Physical tracking accuracy is not established by this arithmetic.

## Corrected model and calibrated start

The user's 13 September correction supersedes the previous photo interpretation:

- Large powered wheels are now at cart **+X**, the front; small casters are at **−X**, the rear. Their centers are at +0.27 m and −0.32 m along the chassis, respectively. The gold arrow in World view marks the powered front.
- Both complete arm mounts rotate **180°**, from +90° to −90° about their existing vertical pivots. Mount positions and calibration files stay the same.
- The user's follow-up turns the complete cart **180° at the starting mark**. The default orbit is now **counterclockwise in forward drive**, with the large powered wheels leading and the cart tangent to the circle. The left wheel follows the inner circle; the right wheel follows the outer circle. The opposite sweep is explicitly labelled reverse travel. Wheel direction, wheel rolling, passive caster direction and camera/light FK use this corrected heading; the exported ring/panel/tube assets retain the same cart-local geometry.
- Every take starts at the integer midpoint of each saved calibrated min/max, matching the existing motor diagnostic. The arm then eases to its aiming pose with the cart stationary. Preview and physical commands share the same exact integer encoder goals.

| Motor | Phone initial count | Light initial count |
|---|---:|---:|
| Shoulder pan | 2120 | 2119 |
| Shoulder lift | 1987 | 1985 |
| Elbow flex | 1987 | 1990 |
| Wrist flex | 2018 | 2039 |
| Wrist roll | 2047 (ID 6) | 2047 (ID 5) |

**There is no arm aiming-error or tracking-error threshold that gates this playback.** Endpoint error is logged as an observation; it does not fail the run. Calibrated motor target ranges, valid device identities, Stop and transport-loss handling remain. This path does not use the older qualification/preflight supervisor.

## Implementation and recovery

| Before | After |
|---|---|
| `dist/orbit.js` preview transport | Same preview, plus the `orbit-robot.js` panel and `robot-client.js` control state |
| Rehearsal server provided offline plans | Adds local, token-protected `/api/robot/` endpoints; only explicit Start launches a motor worker |
| `motion/play.py` accepted terminal-only control | Same CLI, with injected stop/event callbacks and retained torque for browser runs |
| Motor imports loaded PyTorch through `lerobot.utils` | Three device helpers load lazily; public helper names remain available |
| No isolated browser-playback runtime | `requirements-robot.in`, pinned lock and `scripts/setup_robot_runtime.py` |
| Powered axle −X, casters +X, both mounts +90° | Powered axle +X, casters −X, both mounts −90°; shared geometry, orbit and frame definitions updated |
| Preview begins in the final aiming pose | `previs/start_pose.py` supplies calibration midpoints and the shared stationary-cart aiming sequence |
| Downloadable models posed by the older shot solver | The same corrected geometry exported at the calibrated initial pose |

`motion/studio.py` owns prepared plans, exact run identity, duplicate-start protection, process lifecycle and logs. `motion/studio_worker.py` owns the browser lease and a workspace-wide process lock, then calls the existing hardware player. All real serial imports and activity remain in the child process. There is no fake-device mode in the production HTTP API. Tests inject their own isolated fake processes and devices.

Pre-change copies are preserved under `data/recovery/robot-button-20260913/`, with `before.json` for the initial changed files, `geometry-before/` for the geometry correction and previous exports, and a copy of LeRobot's utility initializer. The preservation audit authenticates that initializer's original recovery bytes and exact new hash using `docs/robot-studio-feature-02-changes.json`; it reports the edit explicitly. No calibration original or unique user work was deleted. Per-run prepared plans, command reports, measured endpoint observations when available, and worker logs go under `data/runs/studio-<run-id>/`.

## Verification

Focused automated checks cover calibrated goals, wheel precision/caps, reverse motion, retiming, finite zero endpoints, stale/edited plans, local-origin/token enforcement, duplicate starts, exclusive ownership, Stop, browser expiry, and the absence of automatic replay or torque release. **43 playback/orbit checks, 15 drive/geometry checks, and all 111 web checks pass.** A corrected powered-front contract assertion also passes. A deliberately non-tracking fake arm completes the take, verifying that measured position error does not gate playback. The isolated motor environment validates the exact counterclockwise plan without importing MuJoCo or PyTorch and without opening a port.

Browser verification confirms the 180° cart turn, powered wheels leading counterclockwise, the calibrated starting sequence, preparation and edit invalidation, and fitted Top/Rig views. No hardware Run was pressed. The app remains available at `http://127.0.0.1:8766/`.

Full repository results are in `data/verification/robot-button/summary.json`. The broader run is not clean: legacy compiled-shot paths can exceed the updated arm ranges, including the legacy Director robot-plan endpoint; existing fixture/import and planner expectation failures also remain. Obsolete geometry assertions were updated and passed separately. Six existing files fail repository-wide formatting; modified feature files pass. The unsigned PowerShell test launcher was rejected, so its underlying checks were run directly without changing execution policy. This record does not claim the older planning path has been adapted to the corrected rig.

This feature is ready for the user's supervised physical test on the robot computer. Development-computer tests have not established real-world path accuracy, braking, or arm tracking under load.
