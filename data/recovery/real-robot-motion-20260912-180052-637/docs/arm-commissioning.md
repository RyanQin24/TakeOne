# Arm inspection, midpoint mapping and supported hold

TakeOne uses LeRobot's Feetech motor-bus implementation for the two five-joint arms. Its simulator already has FK and IK, and its executor already coordinates the cart and both arm timelines. Standard SO101 `new_calib` model angles use the same range-middle convention as LeRobot degree normalization. No separate IK implementation or learning policy is required to replay the solved joint samples.

On 12 September 2026, read-only inspection of COM9 (phone, USB 5B14111456) and COM8 (light, USB 5A7A058801) confirmed their firmware calibrations exactly match the recovered original files. The operator confirmed that rendering these readings with the nominal standard mapping matches the physical joint poses. This is a visual static-pose check; it is not loaded tracking or optical accuracy evidence. Reports are under `data/commissioning/20260912T202954Z/`.

The first operator-authorized supported phone hold on COM9 completed at 20:41:31 UTC on 12 September 2026. It requested two seconds of torque, captured 48 encoder samples through 2.0025 seconds, reported zero encoder drift on all five joints, and confirmed all five torque-enable registers were zero after release. Its unmodified report is under `data/commissioning/20260912T204131Z/TakeOne-Phone-Hold-Test.json`. The operator then ran the light hold on COM8; its report at 20:54:38 UTC also recorded completion, zero encoder drift and confirmed torque-off. That report is `data/commissioning/operator-20260912-165141-980/light-hold.json`. Both supported current-position state checks completed; their zero drift with mechanical support does not establish physical holding capacity. Neither test requested joint travel; torque is intentionally off afterward.

The operator subsequently reported that the arms fall during cart-only tests. Pause cart motion and mechanically secure both arms. A read-only inspection at 21:14:20 UTC found torque off and zero servo status flags on all ten motors. Phone voltage feedback was 12.3-12.5 V and light feedback was 5.7 V. The operator reported 12 V phone and 5 V light supplies. These are observations, not verification of the supplies' current capacity or motor variants. No voltage, gain, torque limit or calibration was changed.

## Existing calibration to model angles

```text
mid = (saved_range_min + saved_range_max) / 2
servo_degrees = (Present_Position - mid) * 360 / 4095
nominal_model_radians = radians(servo_degrees)
```

The standard nominal axis signs are +1 and additional offsets are zero in this calibrated-degree coordinate system. Firmware homing is already applied. The initial centering/Enter procedure assigns a raw reading of approximately 2047; the later degree conversion centers the recorded min/max range, which can have a different midpoint. Do not add the saved homing offset again or silently substitute 2047 for that final midpoint.

[The model's calibration documentation](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md) describes the new-calibration range-middle zero. [LeRobot's kinematic integration](https://huggingface.co/docs/lerobot/phone_teleop#step-3-run-an-example) uses the new-calibration SO101 URDF. The custom phone wrist is motor 6 and light wrist is motor 5; neither TakeOne arm includes a gripper.

The nominal signs/zeros are now recorded in `calibration/derived/`. Physical direction checks, tool transforms and loaded cable-safe ranges remain separate, so full mapping qualification is still false. Encoder travel and URDF limits can establish a nominal range intersection, not a payload/thermal limit. Wrist 0..4095 was assigned by calibration rather than measured as unobstructed cable travel.

## Read-only commands

Use Windows PowerShell from the actual project directory:

```powershell
Set-Location -LiteralPath 'C:\Users\nonst\Documents\Python\TakeOne_Astra\TakeOne'
$robotPython = '.\lerobot\.venv\Scripts\python.exe'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
& $robotPython -m takeone.motion.commission nominal --role both --profile windows --output ".\data\nominal-$stamp.json"
& $robotPython -m takeone.motion.commission inspect --role both --profile windows --output ".\data\inspection-$stamp.json"
```

`nominal` reads files only. `inspect` opens the identified arm ports and sends ping/read requests; its motor-register write methods are blocked. It reports raw positions, stored goal positions, calibration correspondence, torque/mode state and nominal model angles. It closes without changing torque. Neither changes qualification flags. `completed: true` means inspection completed, not that live motion is allowed.

The first actual snapshot had torque off and stored Goal_Position zero on all ten motors. Enabling torque directly with those old goals could request a large unwanted movement.

## Physical supported hold trial

The hold command is a separate physical commissioning step. Keep the selected arm and payload mechanically supported throughout, clear of pinch points, and be able to cut that arm's motor power. It does not operate the cart. The operator must be present; a background agent must not infer readiness from a successful file check or from agreement with the rendered pose.

The command rechecks identity, calibration, position mode and initially torque-off state. It reads current positions, writes those as raw goals while torque remains off, verifies the goals and their freshness, then enables torque for a requested duration of at most two seconds. It samples raw encoder drift and attempts to turn every motor off on completion, fault or Ctrl+C. USB/process failure can prevent release; the physical support and motor-power cut are still required. It changes no homing, calibration, PID, mode or acceleration parameters.

Only when the operator and support are ready, a first phone-arm trial is:

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
& $robotPython -m takeone.motion.hold --role phone --profile windows --duration 2 --max-drift-deg 1 --operator-ready --payload-supported --output ".\data\phone-hold-$stamp.json"
```

The 1-degree threshold detects excessive encoder drift during this supported check; it is not a claim of safe unsupported movement or optical accuracy. Require `completed: true` and `torque_disabled_confirmed: true`, together with the operator's observations. A failed release reports `manual_motor_power_cut_required: true`. Inspect the report and hardware before another attempt. Do not automatically repeat a physical trial.

This trial holds the current pose and then releases it. It does not position an arm at a shot start, qualify loaded motion, or qualify combined cart/arm transitions. Those remain subsequent work. Production `takeone.motion.cli live` retains its qualification gates.

## Stationary observation when an arm will not hold

**Superseded as the holding procedure:** use the explicit `--until-enter` mode below for the operator's requested stationary holding behavior. This `--observe` mode is a strict timed drift test that automatically removes torque. Its drift cutoff must not be interpreted as proof that the motor failed to enable.

The first 20-second phone observation ended after 0.250 seconds on 12 September 2026: elbow drift reached 1.143 degrees, all five torque-enable registers still read 1, and the operator confirmed self-weight sag. Voltage was 12.2-12.5 V with no servo status flags. The wrapper's 1-degree guard then disabled all motors and confirmed release. This is a failed holding observation, not a connection failure or a completed 20-second test. The unchanged report is `data/phone-observe-20260912-172459-616.json`.

The observation path now explicitly sends the same fixed current-position goals once after torque enable as well as before it. Before that second command it confirms torque, unchanged goals, drift within the existing limit and an activation check duration of at most 100 ms. It never replaces the saved targets with the sagging positions. This brings the sequence closer to LeRobot's normal active position-command path; whether it fixes the observed sag remains a physical test question. PID, voltage, torque limits and the 1-degree drift guard are unchanged. `active_target_confirmed` records the second goal readback, while `drift_trip` identifies the offending joint and elapsed time. This readback alone does not establish mechanical holding.

Use the additive `--observe` mode to distinguish holding during torque-on from expected release afterward. It defaults to 20 seconds and rejects durations above 30 seconds. The original mode remains limited to two seconds. No simulator or shot file is needed for this current-position test.

Park the cart and turn off its motor power. Close other programs using COM8/COM9. Keep the arm power supplies connected to their corresponding controllers. Test one arm at a time in a compact, supported pose with a mechanical catch close enough to prevent a fall. Support the selected arm and payload during initialization and before release. Only while torque-on is confirmed may the operator cautiously transfer the weight to the motors above that catch; keep hands clear of pinch points. If the catch cannot prevent a fall, retain full support and treat the result as an electrical state check only. Secure the other arm throughout.

The supported SO101 supply voltage depends on the installed motor variant: the [designer's parts list](https://github.com/TheRobotStudio/SO-ARM100/blob/main/README.md#sourcing-parts) distinguishes standard 7.4 V motors, for which a 5 V supply is permitted, from the optional 12 V follower motors. Do not replace the light arm's 5 V supply with 12 V based on the phone arm's supply. The present test preserves all existing power-related settings.

Run the following only when physically ready. The flags attest those conditions; the command cannot switch cart motor power off or create mechanical support.

```powershell
Set-Location -LiteralPath 'C:\Users\nonst\Documents\Python\TakeOne_Astra\TakeOne'
$robotPython = '.\lerobot\.venv\Scripts\python.exe'
$phoneReport = '.\data\phone-observe-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'
& $robotPython -m takeone.motion.hold --role phone --profile windows --observe --duration 20 --cart-parked --operator-ready --payload-supported --output $phoneReport
Get-Content -Raw -LiteralPath $phoneReport | ConvertFrom-Json | Select-Object role, completed, torque_on_confirmed, max_drift_deg, torque_disabled_confirmed, error
```

The display shows `TORQUE ON 5/5`, encoder drift, voltage feedback and seconds until automatic release. These are register observations, not a force measurement. The final five seconds say `RELEASE SOON: SUPPORT THE ARM NOW`. Put the weight fully onto the support before the countdown ends. Completion, a detected fault or Ctrl+C attempts to disable all five motors, then checks torque-off. A fault can release earlier than the countdown; the catch must remain in place. If the arm sags while torque is on, the catch takes its weight; end the test and investigate the saved report. Do not push the joints to test strength. Failed release requires the arm motor-power cut.

Observation checks voltage and temperature against each motor's existing firmware limits, nonzero position gain and torque limits, servo status, unchanged seeded goals and continued torque-on. It aborts on drift greater than the default 1 degree, a read fault, unhealthy state or an unexpected target change. It records current/load feedback as raw diagnostics without treating those values as calibrated joint torque. It never raises limits or automatically retries a failed trial.

If the phone arm stayed in place during torque-on and its report shows `completed`, `torque_on_confirmed` and `torque_disabled_confirmed` all true, secure it and test the light arm in the same way:

```powershell
$lightReport = '.\data\light-observe-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'
& $robotPython -m takeone.motion.hold --role light --profile windows --observe --duration 20 --cart-parked --operator-ready --payload-supported --output $lightReport
Get-Content -Raw -LiteralPath $lightReport | ConvertFrom-Json | Select-Object role, completed, torque_on_confirmed, max_drift_deg, torque_disabled_confirmed, error
```

Each command saves a new JSON file with all samples, firmware limits and health readings. `physical_holding_capacity_verified` remains false because the program cannot observe whether a support carried the load. Record the operator's physical observation alongside the file before interpreting a completed test. A successful stationary observation still does not enable holding during cart motion. A coordinated persistent hold/start/stop procedure remains required before resuming unsupported cart-and-arm operation.

## Hold until Enter following the working script

The hardware entry point is **`packages/takeone/motion/hold.py`**, launched as **`python -m takeone.motion.hold` using the LeRobot Python environment**. `tests/test_supported_hold.py` is an automated test file: its dictionary-backed `HoldBus` and `ManualBus` never open COM9. Passing those tests is only evidence about software behavior. The product factory creates `FeetechHoldBus`, a subclass of the installed `FeetechMotorsBus`, and opens the configured physical serial port. There is no simulator fallback in this command.

The operator's requested sequence for phone COM9, IDs 1/2/3/4/6, is: read all current positions, write those captured goals, enable all five motors, and write the **same** goals again. The program never replaces the captured targets with later encoder readings. The timed observation reports recorded release at their drift threshold; that describes their release behavior and does not establish the cause of a motor failing to hold.

`--until-enter` implements this sequence using LeRobot's individual `read` and `write` methods with `normalize=False`. Inspection of the installed code confirms they call the SDK's `read2ByteTxRx`/`read1ByteTxRx` and `writeTxRx` on its real `PortHandler`. This environment provides `PacketHandler(0)` and does **not** export `sms_sts`; importing the pasted variant unchanged would fail. The raw addresses are present position 56 (2 bytes), goal position 42 (2 bytes), and torque enable 40 (1 byte), also documented in [Feetech's SDK control table](https://gitee.com/ftservo/FTServo_Python/blob/main/scservo_sdk/sms_sts.py).

Manual mode checks the goal registers before enabling, enables the five motors individually with acknowledgments, then resends each saved goal individually and verifies the readback. It keeps torque enabled until Enter or Ctrl+C; drift over 1 degree produces a visible warning and is recorded without removing torque for that measurement alone. There is no duration timer. The old 2-second and `--observe` modes retain their automatic release behavior.

Health, communication, unexpected-target and original-range faults can still trigger release. Keep the cart parked with its motor power off and keep an adequate catch/support in place. Remain beside the arm; support its full weight before pressing Enter or Ctrl+C. Close any other program using its serial port first. The mode requires an interactive terminal, requires all five identified/calibrated motors, and attempts torque-off for all five after any partial enable failure. It never silently continues with a partially responsive arm.

```powershell
Set-Location -LiteralPath 'C:\Users\nonst\Documents\Python\TakeOne_Astra\TakeOne'
$robotPython = '.\lerobot\.venv\Scripts\python.exe'
$phoneReport = '.\data\phone-manual-hold-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'
& $robotPython -m takeone.motion.hold --role phone --profile windows --until-enter --cart-parked --operator-ready --payload-supported --output $phoneReport
```

The console says `TORQUE ON 5/5 | holding until ENTER`. It may say `DRIFT WARNING; TORQUE REMAINS ON`. Support the arm and press Enter when ready to release; require `TORQUE OFF CONFIRMED`, or use its motor-power cut if release is unconfirmed. Do not add `--observe` or `--duration` to this command. Light uses `--role light` and its configured IDs 1/2/3/4/5 when separately supervised.

The console identifies the serial port, baud rate and IDs after connection. The report records the module path, bus class, USB identity, each acknowledged individual motor write, goal readback after enable, peak drift, the first warning and the most recent 1200 samples, plus sample totals/dropped counts. No calibration, gains or torque limits are changed. A completed manual hold means the operator ended the session and release was confirmed; its encoder accuracy and payload capacity are not automatically qualified. The cart/full-robot qualification remains separate.

At 21:47 UTC on 12 September 2026, a real read-only check opened COM9 and verified USB serial `5B14111456`, but the handshake received no replies from IDs 1/2/3/4/6. A separate direct SDK probe sent a position-read packet to each ID at 1,000,000 baud: each serial write returned 8 bytes written, no receive bytes were observed, and each SDK read returned communication result -6 (no status packet). Positions are recorded as null, not the SDK's failure placeholder. The reports are `data/phone-hardware-inspection-20260912-174702-820.json` and `data/phone-direct-sdk-read-20260912T214744350257Z.json`. No torque or goal writes were made by these checks. This establishes a communication failure during those checks; it does not identify the physical cause or verify holding.

After the operator confirmed motor power and cabling, the next direct read at 21:50 UTC received successful replies from all five IDs at the original 1,000,000 baud; no alternate rates were needed. The raw positions were 2043/3175/2094/1320/2976 for IDs 1/2/3/4/6, respectively. A subsequent hardware inspection confirmed the original calibration matched, all five motors were in position mode with torque off, and voltage feedback was 12.3–12.5 V. See `data/phone-baud-probe-20260912T215034194446Z.json` and `data/phone-hardware-inspection-20260912-175109-190.json`. These are actual serial read results; no torque was enabled and physical holding was not measured by them.

The operator then confirmed arm support/catch and parked cart with motor power off and authorized the real phone hold. `data/phone-live-hold-20260912-175308-157.json` records 30.9107 seconds on COM9, 531 real encoder/health samples, and 20 acknowledged individual writes: five initial goals, five torque enables, five identical goals after enable, and five torque disables on the operator's release request. Captured goals were 2043/1988/2031/2045/2976 for IDs 1/2/3/4/6; these were read afresh for this run rather than copied from the earlier inspection. Maximum encoder deviations were 1.143/1.670/1.407/0.967/0.703 degrees, respectively. The largest deviation was shoulder lift. All five torque-off readbacks were confirmed, and the port closed. This is real serial/encoder evidence of the requested sequence; the operator did not report whether the motors or the support carried the load, so physical holding capacity remains unverified.

The operator next requested the same real hold on COM8. Inspection verified light-arm USB serial `5A7A058801`, IDs 1/2/3/4/5, original calibration, position mode and initial torque-off (`data/light-hardware-inspection-20260912-175616-013.json`). The run in `data/light-live-hold-20260912-175631-493.json` lasted 50.6497 seconds with 898 feedback samples and 20 acknowledged writes in the same goal/enable/same-goal/disable sequence. Its captured raw targets were 2117/2030/2064/2041/970; peak encoder deviations were 4.220/2.198/4.308/3.165/2.198 degrees for IDs 1/2/3/4/5. The operator reported “Holding; arm supported now—release torque.” All five torque-off readbacks were confirmed and COM8 closed after that request. The operator statement is saved with the report hash in `data/light-live-hold-20260912-175631-493-operator.json`; the original machine report is unchanged. This records an observed stationary hold with measured deviations, not a measured payload-capacity or combined-motion qualification.

Recovery for this addition is under the task directory's `work/working-hold-comparison-before/`: pre-change module, tests, README and this guide are retained. The operator's exact submitted source is separately retained byte-for-byte. Tests exercise the observed 13-count drift without early release, fixed goals, individual acknowledgments, partial failures, health/read faults, Enter/Ctrl+C and bounded sample storage. No automated test opens a real motor port.

## Direction and replay

The large powered wheels are the front axle; small casters have no motor actuator. `configs/rig.json` now has `reverse_enabled: false` following the operator's clarification, so simulated forward motion leads with the large wheels. Positive UART polarity on the actual cart still needs the physical cart check. Restart the simulator and generate a fresh plan after source, calibration or direction changes.

## Verification and recovery

Inspection tests cover no-write behavior, identity/calibration rejection, partial reads and connection failures, torque preservation, midpoint conversion, and protection of existing reports. Hold tests cover goal seeding before enable, failed goal verification, pre-enable movement, uncertain torque enable, drift, Ctrl+C and partial release failure. Observation tests add health and unexpected-goal faults, lost torque, console failures, interruptions during release, visible countdown and parked-cart attestation. All automated tests use fake buses.

Original servo files and imported LeRobot source remain unchanged. New product entry points are `packages/takeone/motion/commission.py` and `hold.py`; no old functionality was removed. Before-edit copies of changed configuration/tests/docs and later verification records are retained in this task's recovery/output files. Physical execution must remain a supervised opt-in action.

The observation update preserves the original two-second hold path and adds explicit observation options to the same entry point. Its only motor writes remain fresh raw position goals and torque enable/disable. Copies of the pre-update hold module, its tests, this document and the README are retained in `work/arm-observe-before/` under the commissioning task directory. New test reports do not overwrite previous evidence.
