# TakeOne: implement real movement from the simulator

Prepared from this working tree and its motion, calibration and commissioning records on 2026-09-12. This is an implementation assignment for the next engineering session. It does not record new hardware tests or grant physical readiness. Recheck facts that may have changed since this review.

**Copy the assignment below into the implementation session.**

Act as the robotics and controls engineer responsible for making TakeOne's physical robot execute the movement reviewed in its simulator. Complete the implementation through the actual device interfaces. The required robot is the cart, the independent five-joint phone arm, and the independent five-joint light arm. Both powered wheels and all ten arm joints must participate in the same finite motion plan, including joints whose planned movement is a hold.

Remove fake hardware functionality and fake hardware testing from this workflow. A completed replay, animated robot, successful dictionary update, open serial port, or transmitted packet must never stand in for observed physical movement. Deliver a working route from reviewed simulation to real commands, with measured acceptance of the resulting motion. Keep the useful simulator, existing kinematics, actual drivers and recovered calibration. Focus on completing this route; avoid new AI policies, a replacement simulator, general robotics frameworks, or unrelated Director features.

Work from the actual checkout at `C:\Users\nonst\Documents\Python\TakeOne_Astra\TakeOne`. Resolve paths from the repository root so commands also work after relocation. Old documentation containing `C:\TakeOne` or `E:\TakeOne` is not evidence of the current location. Inspect the dirty working tree and preserve all unrelated changes and untracked evidence. Preserve original calibration bytes and the independent local LeRobot repository/environment. Read any applicable `AGENTS.md` before modifying that subtree.

**1. Establish the current implementation before changing it.**

Read the following files and their actual callers. Treat older designs, source code, configurations and physical reports according to what each can establish. Resolve contradictions explicitly; a recent prose statement cannot override contradictory device evidence.

| Read | Why it matters |
|---|---|
| `AGENTS.md`, `README.md`, `docs/architecture.md` | Ownership, workflow, preservation and repository conventions |
| `docs/robot-motion-execution.md`, `docs/robot-motion-verification-2026-09-12.md` | Existing coordinated runner and the scope of its verification |
| `docs/arm-commissioning.md`, `docs/calibration-inventory.md` | Recovered calibration, nominal midpoint mapping, actual hold and communication evidence |
| `docs/arm-movement-design.md`, `docs/architecture-review-2026-09-12.md` | IK objectives, interpolation and missing path acceptance |
| `docs/cart-audit-2026-09-12.md`, `docs/wheel-layout-correction-2026-09-12.md`, `docs/cart-live-testing.md` | Correct wheel topology, polarity, quantization, drift and timing |
| `docs/hardware-test-runbook.md`, `apps/rehearsal/MATH-PHYSICS-AUDIT.md`, `apps/rehearsal/DRIVE-PROOF.md` | Physical test procedures and historical numerical assumptions; revalidate stale findings |
| `configs/rig.json`, `configs/shots/arm-led.json`, `configs/devices/*.json` | Active dimensions, requested shot, identities and direction |
| `configs/cart-response.json`, `configs/cart-runtime.json`, `configs/arm-execution.json`, `configs/qualification.json` | Response data, timing budgets and outstanding physical evidence |
| `calibration/registry.json`, `calibration/originals/*.json`, `calibration/derived/*.json` | Original hashes, actual encoder ranges, mapping and qualification status |
| `packages/takeone/planning/{compiler,targets,kinematics,trajectory,validation}.py` | Existing target-to-joint computation and acceptance |
| `packages/takeone/simulation/{drive,model,robot}.py` | Geometry, wheel-derived chassis prediction and serialization |
| `packages/takeone/motion/{plan,service,devices,arm,limits,cli,commission,hold}.py` | Export, physical composition, execution, measurements and hold ownership |
| `packages/takeone/{execution,calibration,protocol,clock}.py`, `packages/takeone/adapters/{lerobot_arm,uart,identity,simulated}.py` | Coordination, conversion, real transport and synthetic transport paths |
| `packages/takeone/cart/{plan,response,runtime,diagnostics,cli}.py` | Cart preparation, feed-forward mapping, timing and actual commissioning |
| `apps/rehearsal/server.py`, `apps/rehearsal/dist/{app,rehearsal,robot-model}.js` | What the user reviews, exports and sees during playback |
| Relevant `tests/test_robot_motion.py`, `test_contracts.py`, `test_cart_runtime.py`, `test_supported_hold.py`, `test_arm_commission.py`, simulation tests and `scripts/verify.py` | Which claims are analytically tested, injected, or physically measured |
| `lerobot/src/lerobot/motors/motors_bus.py`, `lerobot/src/lerobot/motors/feetech/feetech.py` | Installed degree normalization, packet behavior and connection side effects |

The existing route is approximately:

```text
reviewed shot settings
  -> planning.compiler.compile_shot
  -> solved cart/phone/light trajectory
  -> motion.plan.prepare_shot / RobotPlan
  -> motion.service.execute_plan
  -> execution.RobotRunner, one owner per serial bus
  -> cart.runtime.CartRunner + motion.arm.ArmRunner for phone and light
  -> adapters.uart.MotorUART + adapters.lerobot_arm.LeRobotArm
  -> physical devices and actual observations
```

Repair and complete this route. Do not duplicate FK, IK, calibration, serial ownership or a second execution engine.

**2. Start from the facts already available.**

| Item | Recorded state at this review |
|---|---|
| Phone | COM9, USB `5B14111456`; ordered IDs `1,2,3,4,6` |
| Light | COM8, USB `5A7A058801`; ordered IDs `1,2,3,4,5` |
| Joint order | `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`; neither arm has a gripper |
| Cart | Windows profile names COM5 at 115200 baud; its USB identity is still absent from the profile |
| Calibration originals | Present locally; both file SHA-256 values were checked against the registry when preparing this assignment |
| Nominal mapping | Both arms have signs `[1,1,1,1,1]` and additional degree offsets `[0,0,0,0,0]`; firmware calibration correspondence and a visual pose match were recorded |
| Remaining arm qualification | Derived mappings still have `verified: false`, `safe_ranges_rad: null`, and unverified tool transforms; both loaded execution-limit records are incomplete |
| Cart geometry | Two large powered front wheels, two small passive rear swivel casters; radius 0.095 m; estimated track 0.58 m and axle offset -0.27 m in the cart frame |
| Active direction | `reverse_enabled: false`; positive logical commands request motion toward the large wheels; physical polarity still needs evidence |
| Cart response | `provisional_symmetric`; independent wheel tables are empty; approximately 0.55 m / 4 s is the provisional shared sample; real drift with equal commands was reported |
| Default preview | 9 seconds; phone sweep/lift 0.16/0.04 m and independent light sweep/lift 0.12/0.03 m; response and brake time settings are both zero assumptions |
| Existing execution | Prepared joint playback and separate cart/arm workers exist; live motion has qualification checks and no automatic simulated fallback |

Do not ask to recover already recovered calibration or rebuild already implemented kinematics. Verify the registry and actual original files, then reuse them.

Read `data/commissioning/20260912T202954Z/` for calibration inspection and nominal/visual pose evidence. Read the supported hold reports cited in `docs/arm-commissioning.md`. Those trials requested a stationary pose; mechanical support and subsequent torque release limit what they prove. Later reports describe sag and arms falling during cart-only operation.

Also read `data/phone-direct-sdk-read-20260912T214744350257Z.json`. At that recorded time, COM9 had the expected USB identity and accepted five outgoing read packets, but none of IDs 1/2/3/4/6 returned a status packet. Positions were null and SDK communication results were -6. This is a historical communication failure requiring fresh diagnosis, not proof of its physical cause or of the present device state. A serial write count cannot clear it.

Produce a compact table of each required parameter, value, units/frame, source, evidence date, uncertainty and the capability it enables. Distinguish existing calibration, nominal geometry, assumptions and missing measurements. Replace stale blockers with specific remaining work; do not replace missing evidence with true booleans.

**3. Remove the actual fake paths and misleading completion claims.**

Audit the entire simulator-to-hardware call chain and its operator commands for synthetic devices, mock acknowledgments, invented feedback, permissive test limits, hard-coded success and swallowed errors. Read behavior rather than deleting files by keyword.

Specific removal targets include production imports of `SimulatedArm`, `SimulatedCart` and `VirtualClock` in `motion/service.py` and `motion/devices.py`; the virtual replay that runs the three roles sequentially on separate fake clocks; `simulated_limits()` in the operator execution path; and the root `dry-run` path that currently calls `execute_plan(..., mode="replay")` and reports completion. Remove these from the real-robot workflow and its completion criteria. Retire redundant product fake runners. Keep any necessary isolated fault-injection helpers in test support, outside the production hardware composition.

Preserve the simulator as an explicitly offline planning and visualization tool. A replacement offline plan-check command may validate data and mathematics, but must report only those results. Never change an existing harmless `dry-run`, test, preview or timing command into an implicit hardware command. Update or remove its callers and documentation deliberately.

Delete or rewrite tests that substitute generated state for the central hardware behavior and then claim motor movement, physical holding, synchronization or stopping. For example, inspect `test_default_preview_replays_both_arms_with_real_feedback_errors`: the current plant is simulated even though the name says "real." Renaming a claim alone does not complete physical verification.

Retain useful independent numerical tests and narrowly scoped transport/fault tests. Packet encoding, calibration arithmetic, stale-feedback rejection and failure cleanup need software coverage. Clearly label injected conditions as software checks; they cannot satisfy hardware acceptance. Preserve historical reports and unrelated upstream tests. Do not weaken thresholds, bypass failed checks, or patch the hardware adapter out of a test advertised as a hardware test.

Define separate outcomes for plan validation, commands transmitted, sampled arm tracking, independently observed cart motion, final hold and physical stop. If any required device is missing or unresponsive, report that device and stop the physical run. Never return an overall "robot movement verified" from a simulated source or a transport-only result.

**4. Make the reviewed movement and the executed movement the same contract.**

Use one versioned finite artifact with the plan identity, joint names, roles, units, frames, duration, timing/interpolation semantics, calibration/model/configuration hashes, both five-joint trajectories, and the exact quantized left/right command schedule. Validate every sample and reject non-finite values, missing joints, stale sources, mismatched roles and invalid timing before motion. A digest establishes content identity; it is not proof of physical correctness.

The current planner fits cubic splines at 81 IK knots, samples 321 frames, and exports joint samples. `RobotPlan.arm_at()` interpolates those samples linearly; the arm runner dispatches at 25 Hz. The browser independently interpolates world body positions and quaternions. Derivative checks on the original spline do not automatically apply to the piecewise-linear or held motor commands. Resolve this discrepancy explicitly.

Render the execution preview from the authoritative joint evaluation and FK, together with the cart prediction generated from the transmitted commands. Document any remaining visualization approximation and quantify its error. Verify all ten joints at source knots, between knots, dispatch instants and the exact endpoint. Do not derive motor targets by scraping animated mesh transforms.

Preserve reviewed timing and independent arm intent. If physical constraints require a different interpolation, speed, approach or departure, generate a new plan revision and preview the resulting motion before execution. Never silently clip, wrap a joint, omit an arm, alter a wheel command, retime one subsystem independently, or execute a different default shot. Exported start/stop behavior must agree with what is displayed.

Browser scrub, actor-pace controls and synthetic obstacle/tracking-loss buttons are rehearsal features. Keep them out of physical scheduling unless an actual bounded implementation exists. The first complete result is a finite reviewed shot; speculative actor-following and perception are outside this assignment.

**5. Implement the exact coordinate and servo mathematics.**

Use SI units internally: metres, radians, seconds, rad/s, rad/s² and rad/s³. Declare each transform's source and destination. Distinguish positions, velocities, normalized drive commands, servo degrees and encoder counts.

The world is right-handed Z-up. Cart +Y points toward the filming side; cart +X points toward the rear casters. Drive +X is cart -X and drive +Y is cart -Y. Current optical axes are +Z forward, +X image-right, +Y image-down. Historical LeRobot cinebot optical conventions differ. An explicit fixed transform is required before combining them. Preserve the upper frame and both mounting transforms.

For each arm and tool, compose:

```text
T_world_tool(t) = T_world_cart(t)
                * T_cart_mount
                * FK_mount_wrist(q_arm(t))
                * T_wrist_tool
```

Include actual joint axes/origins and the correct camera lens or light reference point. Declare quaternion order, multiplication convention and handedness. A five-joint arm cannot generally satisfy six arbitrary tool-pose constraints: retain the actual IK priorities and independently check achieved position, pointing and required roll. Solver convergence alone is insufficient.

For joint j, use the saved original calibration and the installed LeRobot degree conversion:

```text
mid_j        = (range_min_j + range_max_j) / 2
servo_deg_j  = sign_j * q_model_rad_j * 180/pi + offset_deg_j
raw_goal_j   = int(servo_deg_j * 4095/360 + mid_j)
measured_deg_j = (raw_position_j - mid_j) * 360/4095
measured_q_j = (measured_deg_j - offset_deg_j) * pi/180 / sign_j
```

Confirm the encoder resolution and integer-conversion behavior against the installed motor model. Homing offsets are already applied in firmware; do not add them again. The calibrated range midpoint can differ from 2047. Do not substitute another zero or assume the wrist's assigned 0..4095 range proves unrestricted cable travel.

Use one conversion boundary: either calibrated degrees passed to LeRobot's degree-mode writer, or a deliberately verified raw writer. Do not normalize twice. Record requested model angles, resulting degrees and actual encoded targets. Read actual `Present_Position` separately; stored `Goal_Position` establishes a target register, not achieved movement. Validate round trips within the encoder quantization and reject targets outside both encoder limits and measured operating ranges. Preserve phone wrist ID 6 and light wrist ID 5 in every path.

The SO101 new-calibration model and its range-middle convention are described in the [designer's simulation documentation](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md). The installed local driver and pinned asset provenance remain the authority for this checkout; do not replace them with a different upstream revision as an incidental fix.

**6. Treat the cart as the actual differential-drive vehicle.**

The powered axle has two commanded wheels; rear swivel casters have no actuator commands. The chassis x/y/yaw coordinates are derived state, not three independent motor channels. Driver-left and driver-right do not swap during reverse travel.

At the powered axle midpoint, with signed ground speeds vL and vR, track width b, wheel radius r, and drive heading psi:

```text
v       = (vL + vR)/2
omega   = (vR - vL)/b
vL      = v - omega*b/2
vR      = v + omega*b/2
wheel_angular_speed_L = vL/r
wheel_angular_speed_R = vR/r
dx_axle/dt = v*cos(psi)
dy_axle/dt = v*sin(psi)
dpsi/dt    = omega
p_axle = p_cart + R_cart * [axle_offset, 0]
```

Integrate the axle motion with a numerically stable straight/turning formulation, then recover the cart center and tool poses with the signed offset. Apply the no-sideways-slip constraint at the powered axle. The offset cart center may have a lateral velocity during turns. These are kinematic assumptions under rolling contact, consistent with [Modern Robotics' wheeled-robot model](https://modernrobotics.northwestern.edu/nu-gm-book-resource/13-1-wheeled-mobile-robots/); validate slip and caster effects physically.

UART fields are dimensionless commands, capped at magnitude 0.15 and serialized to two decimal places as `left,right\n`. The reported minimum moving magnitude is 0.04. Neither field is metres per second, motor torque or watts. Validate before encoding; the protocol's clamp must not silently change an accepted motion.

Use independently measured left/right command-response data where available. Invert desired wheel speeds to commands, quantize through the real protocol, then predict from the resulting wire values. Reject an unachievable request or present a revised plan. At 0.04, tiny trim changes can round away and 0.03 can fall in the deadband. Do not invent a 0.05 speed from the one provisional 0.04 observation, assume reverse symmetry, or extrapolate missing table data.

Account for loaded wheel radius, polarity, startup lag, caster alignment, hysteresis, saturation, floor traction and braking where measurements support them. The current zero response/brake times are ideal assumptions. Slowing the arm timeline without a realizable cart command changes the shot geometry. Retiming must respect cart deadband and response as well as arm limits.

`MotorUART` provides no measured cart position or speed. Implement real measurement capture using available encoders or independent external observations for physical acceptance. Calibrated feed-forward may meet a finite shot's tolerance under measured conditions; characterize repeatability. Add bounded correction only when real feedback and its timing support it. Never label command integration as measured odometry or claim closed-loop cart control from a response table.

**7. Make start, hold, movement and stopping physically coherent.**

Read both actual arm poses before starting. Establish robot placement in the reviewed world frame; arm encoders cannot establish cart world position or heading. A mismatch with the reviewed initial state requires an explicit positioning procedure or a new checked approach trajectory. No jump to the first keyframe and no unreviewed straight-line joint move through the workspace.

Close the existing hold-to-motion integration gap. `hold.py` is a stationary commissioning command whose cleanup releases torque. `LeRobotArm.connect()` expects torque already on. Running the hold command, exiting it, and opening the live runner does not provide continuous support. Implement one reviewed ownership/torque lifecycle that can capture fixed goals, activate them with the verified sequence, maintain support, transition into motion, settle and retain the terminal pose until a supported release. Keep one owner per arm bus throughout. Verify both arms, including during cart-only movement.

Reuse the existing supported-hold sequence where applicable: read positions, seed those same goals, verify them, enable torque, reissue those fixed goals and verify actual response. Never continually adopt sagging feedback as a new target. Resolve no-reply, mode, torque or power faults before commanding travel. Do not change supply voltage, PID, torque limits, homing, calibration, IDs or firmware to make a test pass without a specific justified and authorized change.

Distinguish the commissioning procedure's supported torque release from the loaded production stop policy. On a run fault, the cart attempts its bounded zero sequence; arms use the validated stopping/holding behavior with fresh feedback. Communication loss leaves physical state uncertain. Do not automatically drop a loaded arm, re-enable torque, reconnect, resume, or report process termination as a mechanical stop.

**8. Validate real trajectory limits and loads.**

Check per-joint position, velocity, acceleration, jerk, command step and tracking limits through approach, shot, departure and fault-stop behavior. Evaluate the actual dispatched stream and the controller's known interpolation/response. A small finite-difference acceleration in an offline trace does not prove bounded mechanical jerk.

For a smooth joint path q(s) and shared phase s(t), use the full chain rule:

```text
q_dot   = q_s * s_dot
q_ddot  = q_ss * s_dot^2 + q_s * s_ddot
q_jerk  = q_sss * s_dot^3 + 3*q_ss*s_dot*s_ddot + q_s*s_jerk
```

Phase changes, pauses and braking must respect those derivatives. A quintic time law can give zero boundary velocity and acceleration for a smooth path; duration and displacement still determine the physical demand. It does not repair an arbitrary discontinuity or establish motor capability. See [Modern Robotics on time scaling and boundary conditions](https://modernrobotics.northwestern.edu/nu-gm-book-resource/9-1-and-9-2-point-to-point-trajectories-part-2-of-2/).

The default arm-led preview is a continuous segment with nonzero arm boundary velocities. Prepare explicit realizable transitions. Do not describe its existing nine-second window as a qualified rest-to-rest move.

Evaluate gravity and dynamic demand with installed masses, centers of mass, payloads, cable loads and motor capability at actual voltage and temperature. The arm torque balance includes inertia, velocity-dependent terms, gravity, friction, external loads and moving-base acceleration. Include each contribution once. As a basic check, each gravity load contributes `m*g*perpendicular_lever_arm` about a joint. Slow motion reduces dynamic demand but does not eliminate gravity torque. Treat the existing 0.800 N·m screen as an assumption until supported by appropriate evidence; static zero drift under mechanical support does not establish holding capacity.

Check whole-robot swept clearance, both arms, payloads, cart, actors, set and cable routing with one consistent scene and declared uncertainty margins. Sampled inter-arm checks alone leave gaps. Assess stability with the loaded center of mass, actual ground contacts, cart acceleration and arm motion; a planar model that cannot tip cannot establish stability. Use measured stopping behavior and a bounded stopping corridor. A constant-deceleration estimate such as `distance = speed*reaction_delay + speed^2/(2*deceleration)` is only applicable to the stated assumptions and cannot replace stop measurements.

Fix full tool-position acceptance in `planning/validation.py` for both arms. It currently evaluates pointing and phone height without gating each full requested position residual. `playable` also excludes the assumed payload and camera-height checks. Keep failed previews inspectable, but give plan validity, achieved shot fidelity and physical qualification separate meanings. Recompute current residuals; historical numerical results refer to older plans.

**9. Preserve one bounded real device clock.**

Retain one agreed monotonic epoch, independent bus owners, readiness checks, finite duration, cancellation and fault propagation. Start nonzero cart motion only after both arms and the cart meet the actual readiness requirements. Keep UI rendering, HTTP handling, AI, IK, filesystem writes and unbounded logging out of the timed device workers.

The current cart settings are a 20 ms period, 10 ms lateness allowance, 5 ms write timeout and 40 ms host-gap limit against a user-reported 60 ms firmware watchdog. The documented budget is `20 + 10 + 5 < 40 < 60 ms`. It is a host policy; firmware receipt, watchdog/brake semantics and worst-case latency require evidence. Preserve the deadline margin and verify measured gaps under the complete three-device workload.

Arms currently use a 40 ms period, 12 ms dispatch lateness allowance, 25 ms individual IO limit, 50 ms feedback-age limit and 100 ms peer lease. Audit the whole cycle: read plus write plus processing plus scheduling must fit. Separate calls each below 25 ms can still exceed a 40 ms period. Record acquisition intervals and uncertainty; a timestamp taken before a bus read is not a device-provided simultaneous sampling timestamp.

Monitor freshness, monotonic ordering, per-joint error and endpoint settling from actual observations. Renew health only after successful relevant device work. Define bounds for inter-device skew, missing samples and allowed tracking error based on measured response and shot tolerances. Deadline misses latch a fault; do not send a burst of overdue nonzero commands. A common epoch alone does not prove simultaneous physical response.

Account for serial packet sizes, baud rates, read/write round trips, SDK retries, OS scheduling and process behavior. Report timing distributions and worst observed gaps. If the host cannot meet the required timing under the measured workload, make the smallest justified timing architecture change, explicitly addressing any firmware change. More sleeps or an unmeasured rate increase is not a solution.

**10. Complete a practical operator workflow and honest acceptance.**

Deliver the path: review the shot, prepare the exact artifact, resolve specific preflight failures, inspect actual devices, establish the measured initial pose and hold, run all three subsystems, settle/stop, and inspect the recorded result. Reuse the existing CLI and preparation UI. Do not add a second website or allow preview playback to energize motors.

Use capability-specific prerequisites. Recovered encoder calibration is sufficient for its supported coordinate calculations; measured lens extrinsics are separately needed for a claim of lens-position accuracy. Do not make every unrelated measurement a prerequisite for a limited diagnostic, and do not use a limited diagnostic to qualify the full shot. Complete authorized software work while a physical prerequisite is pending. Avoid repeating already answered calibration or permission questions.

Actual actuation requires the present operator and the documented physical setup for that specific motion. An old hold report or an offline flag is not present readiness. Prepare the complete bounded run and exact commands first, then request only the necessary current operator action if it has not already been authorized. Do not automatically repeat physical trials or broaden their envelope. The recorded cart-only 0.04/four-second and 0.05/two-second experiments do not establish the default full-shot envelope.

Before trials, declare acceptance tolerances and measurement methods. Do not invent universal safe values or choose thresholds after observing errors. At minimum record the following for the reviewed complete shot:

| Acceptance item | Required evidence |
|---|---|
| All ten joint commands and two wheel channels | Exact plan identity, role/ID mapping, timestamped real command trace, and actual encoded values |
| Arm tracking | Raw encoder feedback converted through the original calibration; per-joint maximum/RMS error, latency, sample gaps and final settling |
| Cart motion | Independent time-aligned displacement/heading or wheel observations, drift and repeatability under recorded load/floor conditions |
| Camera/light result | Desired versus FK-achieved tool path; independent physical pose/framing checks sufficient for the claimed spatial accuracy |
| Coordination | Shared start epoch plus observed dispatch/acquisition timing and physical lag/skew bounds across cart, phone and light |
| Start and completion | Measured initial placement, continuous arm support/hold, final cart stop and terminal arm behavior |
| Failure behavior | Real interface error reporting and appropriate supervised fault evidence; injected software cases explicitly identified as such |
| Provenance | Source/config/model/calibration hashes, devices, firmware/SDK identity where available, payload/floor, measurement method and uncertainty |

Never manufacture missing values. Mark unavailable evidence as unavailable. A full shot cannot pass while one arm is omitted, cart motion is only predicted, required measurements are absent, or the stopping outcome is unknown. A real hardware test with unavailable equipment must report unavailable/skipped with a reason rather than silently substituting a fake device or returning success.

**11. Finish the engineering work, not another demonstration scaffold.**

Implement in small complete changes, keeping before/after ownership and recovery for removed unique source. Update launchers, imports, relevant tests and documentation together. Preserve authored `apps/rehearsal/dist` files, original evidence and existing user changes. Use the pinned lightweight environment for planning and the established LeRobot environment for device work.

Run relevant independent mathematical checks and software failure checks, then the required `scripts/TakeOne.ps1 -Command test` after implementation changes. Report its scope correctly. Actual hardware acceptance is a separate run using the real adapters and current hardware evidence. Never place automatic actuation in import, test discovery or the ordinary verification command.

Deliver changed working code, the exact runnable workflow, a concise list of removed fake paths, the motion/calibration/timing decisions, reproducible verification results and the complete physical evidence when available. Update stale architecture statements about missing originals, obsolete executors, wheel direction and completed capabilities. Preserve dated historical records as history.

If physical completion is blocked, finish all independent implementation and give the exact failing interface or missing measured quantity, the evidence, and the smallest next operator action. Say which parts are implemented and which physical claims remain unverified. Do not declare the original simulator-to-entire-robot objective complete until the required real movement and acceptance evidence exist.
