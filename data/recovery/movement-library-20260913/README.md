# TakeOne

**Feature 05 — Hero reveal:** select **Hero reveal · rising orbit** to start at chest height, look upward, and raise the camera toward eye level during an orbit. Both arms have changing motor goals on the same clock as cart travel. Adjust radius, sweep, pace, starting/ending height and lift timing; save/reopen the shot or prepare its matching robot plan. This is the first reviewed slice of the [researched camera movement library](docs/camera-movement-library.md); Dolly Zoom and the walking actor are subsequent slices.

**Feature 04 — smoother previews:** the studio defaults to **Smooth**, with a **Detailed** option above the world view. Paused views sleep until edited, offscreen views skip drawing, and world-camera navigation leaves the phone monitor alone. Path math, full robot geometry and robot command timing remain the same. See [preview performance and verification](docs/preview-performance-feature-04.md).

**Feature 03 — draw a ground path:** the default studio now lets you click points or drag a route, redraw it, undo a stroke, close a loop, and enter start/end coordinates in feet. Every ground square is exactly one foot. The red route and amber motor prediction show requested versus predicted travel. Path previews and **Prepare robot run** share the same forward wheel commands, calibrated arm samples and timestamps. The existing orbit template is available in the movement selector. See [drawn path usage, maths and verification](docs/drawn-path-feature-03.md).

One cart, an independent phone arm, and an independent light arm. This workspace now separates shot planning, the simulator, device adapters, calibration evidence and run records.

**Feature 02 — robot playback from the orbit studio:** the **Real robot** panel prepares the current orbit, shows any timing adjustment, and starts the cart and both arms only when **Run on robot** is pressed. **Stop** or **Esc** stops travel and retains arm goals. Run the simulator on the robot-connected Windows computer; install its isolated driver runtime with `.venv/Scripts/python.exe scripts/setup_robot_runtime.py`. No ports open during setup, preview, or preparation. See [setup and feature 02 details](docs/robot-studio-feature-02.md).

**13 September model correction:** large powered wheels are at the cart's +X front and small casters at its −X rear. Following the user's latest arm correction, both complete arm assemblies have rotated another 180° at their existing mounting pivots, from −90° to **+90°**. The complete cart still starts turned 180° and travels **counterclockwise with the powered front wheels leading**. Every orbit take resets both arms to their saved calibration midpoints, aims with the cart stationary, then starts travel. Preview, motor goals and exported models share the corrected geometry. Arm aiming/tracking error does not gate the studio's robot playback.

**Current simulator — feature 01, orbit study:** open `http://127.0.0.1:8766/` after starting the simulator. Change orbit radius, duration, sweep, direction, starting angle, camera height and iPhone-equivalent focal length. The world and phone views share the solved robot pose, with a timestamped single-shot scrubber. This feature uses ideal cart kinematics and the configured arm ranges; it does not wait for hardware qualification. The existing direct motor diagnostic is available at `/motor-test.html`. The full multi-shot timeline and Director-to-simulator connection are separate review steps. See [the orbit feature record](docs/orbit-studio-feature-01.md).

**Real commissioning launcher:** run `scripts/Run-Robot.ps1` in an interactive PowerShell terminal. It first learns larger observed encoder maxima with torque off, verifies the corresponding firmware endpoint writes and preserves the model's angle zero. It refreshes the plan after calibration/source changes, then uses the real three-device runtime and an encoder-captured, checked arm approach. Missing production evidence is recorded as warnings; actual identity, feedback and timing errors remain actionable failures. `--qualified` retains the formal evidence checks. See [the current commissioning workflow](docs/robot-commissioning.md), which supersedes the older evidence-gated live instructions below.

**12 September calibration and geometry record:** the observed phone elbow maximum became 3092, acknowledged by the real motor; light wrist-flex remained 3204. Original calibration files are unchanged. The arm platform is 1.23 m high; maximum extended height is 1.80 m and each arm's horizontal extension is 0.34 m. That day's photo interpretation used +90° mount yaws; the latest user correction above restores those yaws while retaining the corrected cart and wheel orientation. Both arms are confirmed standard SO-101 kits with custom holders. IK and execution use the same calibration ranges. Custom holder transforms remain nominal. See [the historical photo geometry record](docs/photo-geometry-correction-2026-09-12.md).

**Cart audit after the reverse-direction pull:** the front powered-wheel geometry is preserved. Equal commands are an open-loop test, not proof of straight physical travel; real drift has been reported. Independent wheel-response tables and a non-actuating `analyze-drift` command are now part of the planning system. The timed sender yields instead of busy-spinning, with the same watchdog limits. See [the audit and measurement workflow](docs/cart-audit-2026-09-12.md). No measured motor correction has been invented or activated.

**Implemented:** local simulation, offline diagnostics, coordinated cart/phone/light playback, real LeRobot arm inspection, guarded calibration-endpoint revision, nominal SO101 midpoint mapping, and an explicit supported current-position hold test. Readback confirmed both connected arms match the configured revision. The operator also confirmed the nominal model pose matches the observed joint positions. Tool transforms, loaded limits, directional checks and combined movement remain to be qualified. See [robot motion execution](docs/robot-motion-execution.md) and [arm commissioning](docs/arm-commissioning.md).

**Real arm hold:** run `lerobot/.venv/Scripts/python.exe -m takeone.motion.hold --until-enter` with the options in [the hardware hold guide](docs/arm-commissioning.md#hold-until-enter-following-the-working-script). The entry point is `packages/takeone/motion/hold.py`; `tests/test_supported_hold.py` only uses fake buses and cannot control motors. The hardware command opens the configured Feetech serial port, captures current positions, writes those goals, enables torque, then writes the same captured goals again with per-motor acknowledgments. It keeps those targets fixed until operator release, reports drift, and saves the port/driver and acknowledged writes. Health/communication faults can still release torque; support/catch and cart motor power off are required. The timed `--observe` mode retains its drift-triggered release. Software tests do not establish physical holding.

**Director parts 01-02 and partial package 05 voice:** open `/director.html` for saved briefs, editable scripts, dialogue choices and shot proposals. A bounded OpenAI Responses adapter is implemented for live planning; `OPENAI_API_KEY` and explicit enablement in `configs/director-planning.json` are required, and live planning quality/access remain unverified. Open `/voice.html` for an explicitly labelled offline text rehearsal whose simulated recording lifecycle closes the local conversation gate. The offline fixture does not acquire a microphone, contact GPT-Live, operate a recorder or control production. Live voice is disabled by default and remains unavailable until its provider transport, conversation backend and real recorder gate are integrated independently. This slice does not complete package 05 or verify silence during physical capture. Full synchronized previs, camera capture and Director-controlled robot movement remain later packages. See the [voice implementation record](docs/ai-director/implementation/05-rehearsal-voice.md), [creative planning implementation record](docs/ai-director/implementation/02-creative-planning.md) and [engineering prompt](docs/requests/ASTRA-ENGINEERING-PROMPT.md).

## Start here

Run these commands in PowerShell from your checkout root. Scripts also work when invoked by absolute path from another directory.

```powershell
# Install/reconcile the lightweight environment and existing web dependency.
.\scripts\Setup.ps1

# Start the simulator; open http://127.0.0.1:8766/ . Ctrl+C stops it.
# The default page is the ground-path editor; the orbit template remains available.
# Open /motor-test.html for the existing direct calibrated motor diagnostic.
.\scripts\TakeOne.ps1 -Command simulator

# Export the same exact raw values without opening the browser.
.\.venv\Scripts\python.exe -m takeone.direct --output data/direct-motor-test.json

# Inspect/validate the export without opening any hardware ports.
.\lerobot\.venv\Scripts\python.exe -m takeone.motion.direct `
  --plan data/direct-motor-test.json

# Physical playback is deliberately explicit. Replace PLAN_ID with the ID printed
# by the export command. The sequence uses no IK or trajectory-limit pipeline.
.\lerobot\.venv\Scripts\python.exe -m takeone.motion.direct `
  --plan data/direct-motor-test.json --confirm-plan PLAN_ID `
  --operator-ready --execute

# Use another port if an existing simulator is running.
.\scripts\TakeOne.ps1 -Command simulator -Port 8768

# Inspect saved device identities, evidence hashes and readiness blockers; no ports open.
.\scripts\TakeOne.ps1 -Command diagnose

# Compile and validate the complete default plan offline; no ports open or fake execution.
.\scripts\TakeOne.ps1 -Command dry-run

# Product contracts, original simulation regressions and web/GLB checks.
.\scripts\TakeOne.ps1 -Command test
```

Setup requires Python 3.13, uv and Node/npm. It leaves the separate LeRobot Python 3.12 environment alone. The simulator lock file pins the previously working versions; the root package installs editable. The root environment was freshly built and checked on this machine. A clean machine and the Linux robot host have not been tested. Linux paths in the device profile are recorded identities, not evidence of a successful connection.

To preserve the versioned verification reports, route a run to a fresh directory outside the repository: `.venv/Scripts/python.exe scripts/verify.py --output-dir C:\TakeOne-verification` on Windows or `.venv/bin/python scripts/verify.py --output-dir /tmp/takeone-verification` on macOS/Linux. Relative output paths resolve from the caller's working directory. Omitting the option retains the existing `data/verification` destination.

The separate [cart-only commissioning workflow](docs/cart-live-testing.md) provides exact calculated command plans, offline checks and an explicit supervised `live-test` command. Install the `uart` extra only in the intended hardware environment. Root `dry-run` validates data and mathematics; it does not execute fake devices. The simulator never opens a motor port. Do not run LeRobot's normal `connect()` expecting a read-only diagnostic: it configures motors. Follow the test runbook before hardware work.

The motor diagnostic at `/motor-test.html` uses the direct motor path in `packages/takeone/direct.py`. It starts all ten joints at the integer midpoint of their configured calibration min/max, moves both arms directly in encoder counts, and sends a constant forward cart command. The downloaded JSON carries every raw count at every 40 ms frame; `takeone.motion.direct` validates that the export still matches the installed calibration and sends those exact values without IK, aiming, collision, workspace, velocity, acceleration, or jerk planning. Device identity, calibration endpoints, servo health faults, the UART command cap, and an explicit execution confirmation remain intact because they are hardware/protocol boundaries rather than motion planning.

The older shot-planning pipeline remains available for imported plans and legacy tooling. `python -m takeone.motion.cli` still provides `prepare`, `check`, `preflight`, `templates`, `assess` and its prior supervised `live` path.

## Full robot implementation and remaining measurements

Read [the mobile-IK correction record](docs/mobile-ik-correction-2026-09-12.md), [hardware runbook](docs/hardware-test-runbook.md) and [parameter inventory](docs/calibration-inventory.md). The physical owner activates a captured fixed pose, carries it into motion and retains the terminal hold until supported release. The current 13-second review artifact passes declared software fidelity and adds explicit transitions around the original nine-second shot. The cart can start anywhere: its physical starting pose becomes run-local `(0, 0, 0)`, and execution uses the simulator-derived timed wheel schedule as a relative path. Physical preflight still fails because loaded limits, independent cart response/stopping, tool/scene measurements, model alignment and full-robot timing remain unqualified.

The corrected layout has large powered front wheels and small passive rear swivel casters. Both arm mounts are 1.23 m above the floor while the original SO101 chains remain unscaled. `cart.reverse_enabled` is false. The coordinated default uses a reviewed two-decimal 0.04/0.05 packet schedule with different average left/right values and reintegrates those exact packets before acceptance. This remains a provisional open-loop prediction until independent loaded wheel response is measured. The requested camera sweep is 16 cm with 4 cm lift, frozen in world space before cart optimization. Restart an existing simulator after source changes and export a new plan.

The cart's reported firmware watchdog activates failsafe runaway brakes after 60 ms without commands. The cart runner targets 20 ms command intervals, detects late writes, and records host timing separately from physical response. Its live-test envelope permits only equal commands in the globally configured direction: `0.04` for at most four seconds, or the operator-requested `0.05` for at most two seconds, with supported stationary arms. `python -m takeone.cart.cli prepare --command 0.05 --duration 2 --output NEW.json` prepares the explicit command experiment without changing the speed calibration or the default simulator shot. The dated [architecture review](docs/architecture-review-2026-09-12.md) is historical; the [current implementation record](docs/real-robot-implementation-2026-09-12.md) describes the changes and unresolved tool-position residuals.

## Where things live

| Path | Owns |
|---|---|
| `apps/rehearsal/` | Local API, authored Three.js UI, static GLBs and existing simulation verification |
| `packages/takeone/` | Shared contracts, configuration, protocol, planner, simulation, execution and adapters |
| `configs/` | Active rig, shot and device profiles; historical imports marked separately |
| `calibration/` | Byte-preserved audit and restored originals; nominal midpoint mappings with static-pose evidence and pending full qualification |
| `assets/robots/` | Active geometry and intact original validation/upstream assets with licenses |
| `scripts/`, `tests/` | Operator commands, migration/recovery tooling and product contract tests |
| `data/` | Saved diagnostics, run manifests/events, measurements and verification logs |
| `docs/` | Architecture, roadmap, runbook, templates and migration record |
| `lerobot/` | Complete LeRobot source and local modifications, included in this repository |
| `archive/` | Verified recovery snapshot and original distributions/historical enclosing material |

[Architecture and future milestones](docs/architecture.md) define package responsibilities and extension points. LeRobot's working files are now versioned directly in this repository, so a normal clone includes the arm drivers and project-specific changes. The original local `lerobot/.git` repository and environment remain intact; a fresh clone receives the source without a nested Git database. Saved project data and archives are included. Installed environments, caches and credentials remain excluded. See [repository contents and cloning](docs/repository-contents.md) for Git LFS, provenance and byte-preserving checkout instructions.

## Development

The simulator imports the installed TakeOne package directly. Compatibility shims and the sys.path bootstrap have been removed from the active app. Its `dist/` is authored source, not disposable build output. After changing models, run `.venv/Scripts/python.exe -m takeone.simulation.model`, followed by `node apps/rehearsal/export_models.mjs` and the tests. Root commands use `.venv`; there is no supported relocated environment in the app folder.

[Arm movement design](docs/arm-movement-design.md) is the code-reading guide for settings, target strategies, IK, trajectory generation and validation. Camera and light sweep/lift controls are independent. The test command includes the pinned Ruff lint and formatting checks; run setup once after updating to install the development extra. Simulation regression tests now live in `tests/simulation/` and the preserved upper-frame fixture is in `tests/fixtures/`.

Run manifests include configuration/calibration/model hashes, requested commands, transmitted packets and observation source labels. The cart UART has no measured-speed feedback. A fake observation and a successful serial write must never be presented as a measured physical movement. `TAKEONE_ROOT` can select a different complete configuration/assets checkout; it must contain the same layout. Windows/Linux device overrides belong in the versioned profiles, not hardcoded imports.
