# Tomorrow's supervised hardware test

The first objective is to gather trustworthy measurements and validate one subsystem at a time. The software preview is available; combined physical replay is blocked. A separate [cart-only commissioning command](cart-live-testing.md) now supports a bounded supervised test with stationary supported arms. It does not bring up or command the arms. Existing LeRobot bring-up can configure motors and torque, so it must be inspected and performed deliberately by the hardware operator.

## Roles and stop procedure

Assign one operator to authorize each movement and a second person to observe clearance and the physical power-stop arrangement. Keep the cart and payload supported as needed. Before energizing, identify what cuts cart motor power and how loaded arms remain supported; removing servo torque can drop a payload. Agree on a spoken abort cue. The firmware command timeout is reported as 60 ms with failsafe runaway brakes; physical stopping distance and exact firmware behavior remain unverified. A UI pause, Ctrl+C, closed serial port or zero packet is not a verified emergency stop.

On unexpected motion, identity mismatch, cable snag, missed feedback, excessive heat/noise, or an unclear stop response, use the agreed physical abort procedure and support the payload. Record the fault and inspect before restarting. Never automatically resume after a fault or reconnect. Software attempts cart zero and a fresh measured arm hold; communication failure may prevent both.

## 1. Offline preflight — ready now

From the root run setup if needed, then `scripts/TakeOne.ps1 -Command diagnose`, `-Command test`, and `-Command dry-run`. Open the simulator and inspect start/middle/end of the default shot with each light. Check that the full phone/light geometry is present and that the cart travels along its wheel plane.

Pass: tests succeed, the calibration audit hash matches, the dry-run records `physical_commands_sent: false`, and the documented default has equal wheel commands with zero base yaw. Preserve run manifests and software/model/configuration hashes. Known hardware blockers are expected here and must remain visible.

## 2. Identify devices and recover originals — operator work required

With movement disabled and payloads supported, identify each adapter by USB serial, not merely COM number. Match the saved profile to the physically labeled phone/light arm. Verify motor identities against the recorded five-joint maps; phone ID 6 must not be interpreted as a gripper. Record cart USB identity, actual port, board/firmware revision and command mode. Obtain the ESP32 firmware and verify the reported 60 ms command timeout, valid-packet reset conditions, brake latching/release and restart behavior.

Retrieve the original arm calibration files from the recorded robot-host locations through the authorized operator workflow. Verify their hashes before updating `calibration/registry.json`. Do not overwrite the originals or trigger a new calibration to solve a file-path issue.

Pass: actual device-to-role identity and calibration provenance agree with recorded evidence, or a reviewed new revision explains every difference. A missing original or unexpected ID stops the arm test path. Merely opening an adapter or reading a file is not evidence of torque-safe bring-up.

## 3. Parked cart, one arm at a time — gated

Immobilize the cart and inspect/support the mounted payload. Use the existing reviewed hardware workflow to bring up one arm. First record its measured pose. Establish each joint's sign and model-zero offset through small, operator-bounded observations away from limits. Record raw encoder positions, calibrated degrees, model radians and the observed physical direction. Validate the same mapping at multiple distinct poses and independently check the resulting camera/light pose against physical measurements.

Do not infer signs or URDF zero from the calibration midpoint. Measure lens-to-wrist/light-to-wrist transforms. Establish loaded, cable-safe ranges and conservative speed/acceleration/jerk limits; observe wrist cable travel explicitly. Predeclare measurement tolerances based on the instruments and shot requirements in the sheet, then compare residuals to those tolerances. This migration supplies no invented physical tolerance or certified load limit.

Pass: the operator signs off measured mapping and tool-transform residuals within the recorded tolerances, safe limits are documented, actual/commanded direction agrees, and hold/abort behavior is demonstrated under support. Repeat independently for the other arm. Update derived records only with evidence, retaining original calibration bytes. The current assumed payload-margin failure must be resolved before an unsupported loaded move.

## 4. Cart-only measurements — gated independently

Keep the arms in a supported, verified stationary configuration. Measure wheel center-to-center spacing and powered-axle offset from the cart origin. Confirm 19 cm diameter and 6 cm tire width. Use a marked clear floor area and bounded operator-controlled runs. First verify channel polarity and stop behavior using the reviewed controller/firmware, with a working physical abort arrangement.

Follow [cart live testing](cart-live-testing.md) to prepare a source-bound plan, run virtual replay, check host timing without hardware, and explicitly identify the cart USB adapter. The provided live command is limited to equal commands in the globally configured direction, currently reverse `-0.04`, and at most four seconds. Additional speeds and turning require a subsequent measured-response workflow; this initial command cannot execute them.

Record both commanded channels, timestamps, travel from rest, steady travel if identifiable, heading change, final zero time, coast distance and time-to-rest. Repeat the lowest usable straight command in both directions, then test additional commands and gentle turns only after straight/stop checks pass. Never reduce below the reported 0.04 threshold and assume the motor will creep; its behavior must be measured. Keep the ±0.15 cap, and use smaller operator-approved commands for initial characterization.

Pass: repeatable measurements are available for each tested condition, left/right polarity is understood, stopping remains inside the predeclared clear area, and firmware loss-of-command behavior has been demonstrated under controlled conditions. Record spread across trials and floor/payload conditions. The approximate 55 cm in four seconds is a reference observation, not an acceptance guarantee or established steady-state transfer function.

## 5. Combined short move — currently blocked

Do not transmit the exported preview's radians to the arms. Prerequisites are verified originals/mapping/tool transforms, measured loaded limits, identified cart dynamics and watchdog, a physical stop procedure, and a validated transition from the actual measured starting pose through motion to a supported stop. The current nine-second preview has nonzero boundary velocities and cannot serve as that start-to-stop sequence.

Once prerequisites and a reviewed live bring-up/execution workflow exist, begin with a short straight cart segment and small independent arm correction. Measure actual versus planned pose, timing, framing, light exclusion and stop distance. Broaden the shot only after the previous segment meets recorded tolerances. Qualification flags must reference evidence; flipping booleans does not qualify hardware.

## Records to keep

Use the templates in `docs/templates/`. Store filled sheets, videos and measurements in a new `data/measurements/<date>-<run-id>/` directory, along with software revision/file hashes, configuration/calibration hashes, device identities, firmware version, floor, payload, operator names and abort notes. Keep requested, transmitted, measured and estimated quantities in separate columns. The dry-run's fake state is labeled simulated and must not be reused as measurement evidence.

After testing, create a findings record with pass/fail for each subsystem, measured limits with uncertainty, unresolved blockers and the exact next experiment. Keep the previous evidence and calibration revisions recoverable.
