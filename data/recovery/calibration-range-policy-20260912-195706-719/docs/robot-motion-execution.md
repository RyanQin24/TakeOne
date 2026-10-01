# Simulator to real robot execution

The physical route is implemented for the cart and both five-joint arms. It uses real UART and Feetech interfaces, one serial owner per role, one finite reviewed plan, actual encoder feedback, and a retained hold until supported release. **Full physical movement is not yet verified.** Recovered calibration and successful stationary holds are available; loaded operating ranges, response/stop measurements, tool alignment, and a passing requested shot are still required.

The current implementation/evidence record is [real robot implementation, 12 September 2026](real-robot-implementation-2026-09-12.md). The [parameter inventory](calibration-inventory.md) distinguishes available calibration from missing measurements. Older dated reports are historical.

## One reviewed artifact

`takeone.robot-plan.v2` binds ten named joints, phone/light roles, radians/metres/seconds, explicit coordinate frames, duration, piecewise polynomial coefficients, dispatch times, exact two-decimal wheel commands, acceptance criteria, and source/configuration/model/calibration hashes. Phone wrist roll is ID 6; light wrist roll is ID 5. There are no grippers. Loading checks finite values, identities, ordering, timing, samples and provenance; offline `check` and live execution additionally reconstruct the whole artifact from its canonical inputs. A recomputed digest does not authorize a hand-edited plan.

`planning/curve.py` preserves the existing cubic spline fitted at 81 IK knots. Both the physical arm runner and the execution preview evaluate this same curve. `simulation.robot.pose_frame` supplies the existing FK and body/tool serialization. The browser displays complete FK frames at 40 ms dispatch instants and holds the previous frame between them; it does not interpolate world meshes into a second joint path. The exact endpoint is included. The artifact quantifies the display time step and sampled midpoint spatial differences. These are visualization differences, not measured mechanical lag or continuous physical error bounds. The original 321 source frames remain available for analysis.

Cart prediction is integrated from the actual quantized wire schedule, including the signed axle offset and any modeled braking after the shot. Cart +X points toward the rear casters; drive +X is cart -X. World is right-handed Z-up. Tool optical axes are +Z forward, +X image-right and +Y image-down. Serialized world quaternions are xyzw. The model composes world-from-cart, cart-from-mount, joint FK and wrist-from-tool; historical cinebot optical transforms cannot be inserted without conversion.

The nine-second default has nonzero boundary velocities. `--transition-seconds` creates a new artifact with explicit quintic approach/departure segments, zero boundary velocity/acceleration, and the original shot unchanged between them. This can include excursions needed to join the original derivatives. Optional `--initial-pose` supplies a JSON array of ten measured model angles. Without it, the revision begins at the original first pose; it does **not** assume the robot is physically there. Review the entire revision before considering execution. There is no implicit positioning, clipping, wrapping, dropped role or retiming.

Plan validity, requested-shot fidelity and physical qualification are separate. Full phone and light position residuals now gate fidelity alongside aim, height and horizon. Failed candidates remain inspectable. Preparation includes continuous polynomial extrema and a conservative swept nominal-geometry bound covering nonadjacent robot parts and the shared set/actor scene in `configs/scene.json`. Attached parts are explicitly excluded. Static COM margin and assumed gravity demand are reported separately. Missing cables, measured geometry/mass uncertainty, dynamic tipping, slip and real motor capability require physical evidence.

## Real torque and feedback lifecycle

1. Reconstruct the exact plan and validate all prerequisites before serial IO. Verify each port's USB identity, role and five motor IDs. The driver opens the installed LeRobot Feetech bus directly; it does not call follower configuration or calibration.
2. Require position mode, firmware calibration correspondence, initially torque-off state, ordinary angle mode, valid existing limits and healthy replies. Read actual raw positions and verify the measured starting pose against the reviewed start.
3. In the same process that will execute the arm, capture one fresh pose, acknowledge individual Goal_Position writes, verify them, enable torque with individual acknowledgments, then write and verify the **same captured goals again**. Commissioning `--until-enter` and production activation share `adapters/fixed_pose.py`. The target never follows later sag.
4. Grant a common monotonic start only after all three owners are ready. Keep both arms active even when their trajectory holds while the cart travels. Each arm reads real feedback and writes five acknowledged targets per dispatch. Conversion is performed once, to raw counts using the saved range midpoint and installed integer truncation. Both requested and encoded positions must remain in measured safe ranges.
5. A 31-byte RAM read per motor records torque, goal, present position and health with per-joint acquisition intervals. SDK communication errors, device status errors, incomplete packets, unexpected goals, torque loss, stale samples, tracking error and deadline misses fail the run. Requested model angles, calibrated degrees, encoded counts, acknowledgments and actual encoders remain distinct.
6. Normal motion ends with a measured settling window. The same arm owner retains and monitors its fixed terminal goal. Reports include maximum/RMS joint error, acquisition and command timing, sample gaps, activation, final hold and release outcome.

During live operation type `abort` to cancel travel while retaining the arm stop/hold policy. Support **both** arms fully before typing `release`; this explicitly attempts torque-off on all ten motors and checks the result. Early release cancels the run. EOF/detach or supervisor loss retains targets and reports uncertainty; it does not claim a mechanical stop. The interface never automatically reconnects, re-enables torque or resumes.

On a fault the cart attempts its bounded zero sequence. Each arm may request one fresh stopping pose only within the validated step/freshness envelope; otherwise it retains its last target and marks stopping unconfirmed. It never continually chases feedback and never automatically removes loaded-arm torque. A wedged process can be terminated after bounded cleanup; termination is not physical stopping. The narrower commissioning hold command has its own supported-release policy and must not be used as a hold handoff to the live runner.

## Timing and measured limits

Cart policy remains 20 ms period + 10 ms dispatch allowance + 5 ms write timeout < 40 ms host-gap limit < the user-reported 60 ms watchdog. Firmware receipt, reset/brake semantics and stop distance remain unmeasured. Arms use a 40 ms period, 12 ms dispatch allowance, and a **25 ms complete read/write cycle limit**, plus individual-call checks. Feedback age is limited to 50 ms, peer lease to 100 ms and supervisor lease to 150 ms. Host timestamps bound acquisition intervals; they are not simultaneous device timestamps. The SDK packet clock uses monotonic time and bounded timeouts.

`configs/arm-execution.json` requires measured five-element arrays for velocity, acceleration, jerk, step, initial/tracking/final tolerances, with mapping and evidence hashes. Validation checks continuous reference derivatives and finite differences of the actual encoded dispatch stream, including terminal holding. Those finite differences do not establish mechanical jerk or loaded capacity. Actual three-device timing/response evidence is required; passing an injected software timing case does not provide it.

## Runnable offline workflow

Set the repository path once (the current checkout is shown); subsequent paths are resolved from it, so commands work from another directory. The environments remain separate.

```powershell
$repo = 'C:\Users\nonst\Documents\Python\TakeOne_Astra\TakeOne'
$plannerPython = Join-Path $repo '.venv\Scripts\python.exe'
$robotPython = Join-Path $repo 'lerobot\.venv\Scripts\python.exe'
$review = Join-Path $repo 'data\real-robot-review-v2.json'
& $plannerPython -m takeone.motion.cli check --plan $review
& $plannerPython -m takeone.motion.cli preflight --plan $review --profile windows
```

`data/real-robot-review-v2.json` is an inspectable 11-second candidate: one-second approach, original nine-second shot, one-second departure. It fails requested-position fidelity and physical preflight. Open the simulator and use **Review prepared robot plan (including transitions)** to load it. Export returns that exact artifact, including its revision. No HTTP endpoint commands motors.

For a new candidate, use a new output filename:

```powershell
& $plannerPython -m takeone.motion.cli prepare --transition-seconds 1 --output (Join-Path $repo 'data\NEW-candidate.json')
& $plannerPython -m takeone.motion.cli templates --plan (Join-Path $repo 'data\NEW-candidate.json') --output-directory (Join-Path $repo 'data\NEW-measurements')
```

`prepare` without a source loads the active default. `--settings` expects a plain settings object (not the schema wrapper in `configs/shots/arm-led.json`); `--shot` accepts a current exported shot. `--initial-pose` and `--criteria` explicitly bind the intended start and predeclared tolerances. Source changes require a new artifact and a server restart. `check`, root `dry-run`, and the retired `replay`/`timing` aliases perform offline validation only; they run no fake device clock and make no motor-completion claim. Ordinary tests open no motor ports.

## Physical evidence and eventual live command

The user has a tape measure and final-heading measurement. `motion/measurements.py` accepts these independent endpoint observations, with uncertainty, operator/method, load/floor and plan/run hashes. This proves only the endpoint quantities measured. Full path, tool pose, stopping time/distance and physical coordination require the corresponding independent observations. Command integration cannot fill them. Repeatability remains a separate multiple-trial finding.

Generated templates leave unknown measurements and tolerances null. Before a trial, record criteria; complete measured mappings/limits, the independent cart response tables, and evidence in `configs/motion-evidence.json`. The five evidence categories cover cart stopping/watchdog, loaded arm stop/hold, scene/stability, tool alignment and complete-host timing. Each record binds a motion fingerprint, actual measurement quantities/units/uncertainties, method/conditions and source-file hashes. The fingerprint permits sealing the evidence index without a circular hash. Legacy `configs/qualification.json` booleans do not qualify this full-shot route.

After those checks pass, prepare/review the final identity, record a fresh `setup.json` with measured cart world position/heading, payload/floor, operator and physical abort/support arrangement. Its placement must match the reviewed start and be no older than ten minutes. Only a present operator authorizing that exact motion can run:

```powershell
& $robotPython -m takeone.motion.cli live --plan $review --profile windows --confirm-plan FULL_REVIEWED_PLAN_ID --setup (Join-Path $repo 'data\MEASURED-setup.json') --operator-ready
```

This is a workflow example, not authorization for the current failing candidate. A supported initial-pose mismatch stops before activation/travel. See [the hardware runbook](hardware-test-runbook.md) for the smallest remaining physical steps.

Every real run saves the plan, report and separate device traces under `data/runs/`. After recording independent observations:

```powershell
& $plannerPython -m takeone.motion.cli assess --run (Join-Path $repo 'data\runs\ACTUAL-RUN') --observations (Join-Path $repo 'data\MEASURED-observations.json') --output (Join-Path $repo 'data\NEW-assessment.json')
```

`completed` concerns the command lifecycle. `robot_movement_verified` stays false unless required actual commands, encoder tracking, independent cart/tool path observations, physical skew, terminal behavior and stopping pass the predeclared criteria. Missing measurements stay unavailable.
