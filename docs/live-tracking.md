# Live person tracking from Shot Studio

The **Follow a person** panel is below **Real robot** in the simulation UI.
It starts a separate real-camera tracking process. The world and phone previews
remain simulated; the live OpenCV camera image opens in a separate window.

## Cart camera and framing calibration

The active tracking source is the USB **Live Streamer CAM 313** mounted on the
cart. FFmpeg selects it by its exact DirectShow device name and supplies the
newest 640 x 360 BGR frame. Numeric camera indexes are not used.

Before tracking, stand where the robot should settle and frame your upper body
the way it should appear in the shot, then run:

```powershell
.\scripts\Calibrate-CartTracking.ps1
```

The calibration window opens only the camera. It opens no serial ports and sends
no motor commands. Hold still until at least 15 valid frames are shown, then
press Space. TakeOne stores the median shoulder midpoint and shoulder width as
resolution-independent fractions in `configs/tracking.json`. Esc or Q cancels
without changing the saved target.

The body controller uses shoulder width as its cart distance target and the
horizontal shoulder midpoint as its steering and shoulder-pan target. Its
vertical center is recorded for framing evidence, but the supplied controller
does not command vertical arm motion.

## Start tracking after the camera check

1. Start or restart the app with `scripts/TakeOne.ps1 -Command simulator` and
   refresh `http://127.0.0.1:8766/`.
2. Choose **Robocart · body tracking** or **Roboarm only · face tracking**.
3. In Robocart mode, select or clear **Enable phone + light arm tracking**.
   The checkbox defaults to enabled, matching the supplied script. When cleared,
   neither arm is connected, initialized, torqued or sent goals. Only the cart
   and camera are opened. Roboarm-only mode always uses both arms and no cart.
4. Press **Start live tracking**. This runs real hardware immediately using the
   script's initial goals. The wrapper maps the scripts' preserved camera index
   to the exact named cart-camera receiver in `configs/tracking.json`. Ports are
   COM5 for the cart, COM9 for the phone arm and COM8 for the light arm.
5. Press **Stop tracking**, press **Esc** in the browser, or **Q** in the live
   camera window. Stop remains available during startup. Change modes/options
   after the process has stopped.

Normal robot playback and tracking cannot start concurrently. A shared OS file
lock also prevents another Shot Studio server instance from opening the devices.
The launcher checks configured USB identities before opening the script's ports.
Unmanaged scripts started elsewhere are outside this process ownership system.

## Preserved logic and integration boundary

`scripts/tracking/robocart_tracking.py` and `roboarm_tracking.py` are exact copies
of the supplied attachments, checked by SHA-256 before each launch. The existing
`motor_UART.py` is copied unchanged from the original TakeOne directory. Tracking
gains, thresholds, targets, model selection, requested camera number, serial framing,
calibration dictionaries, startup order and tracking loops have not been edited.

The worker replaces the scripts' requested camera number at the IO boundary with
the named DirectShow cart-camera receiver. A one-frame queue discards backlog so
the tracking loop receives the newest available frame. It also scales the
preserved script's 1280 x 720 body target to the active frame size and applies
the operator's saved framing target before the tracking loop begins.

The first script uses MediaPipe pose landmarks and tracks the arms only while
the cart is idle. The second uses face detections and controls both arms. Their
different initial shoulder-pan goals are preserved: cart mode phone/light
3058/2984, arm-only mode 2034/1880. These scripts use their own dictionaries,
not Shot Studio's derived arm mappings. In the first script the existing call
`set_speed(Phone_ARM, Light_ARM_IDS, Max_Robarm_speed)` is also preserved exactly.

`packages/takeone/motion/tracking_worker.py` executes the original source with
adapters for camera lifetime, the servo SDK and MotorUART. With arms disabled,
the SDK adapter acknowledges script calls without constructing real arm ports
or SDK objects. This suppresses both startup and tracking arm IO without editing
the script's `bool_Enable` assignment or control loop. With arms enabled, the
arguments are forwarded unchanged. Shoulder-pan goals are recorded in
`worker.log` with their port, motor ID, value and SDK result so a detected person
can be distinguished from a successful arm command.

## Stop behavior

The wrapper prevents new tracking writes after Stop is observed, requests a cart
zero command, exits the camera loop and closes the camera and opened ports. It
also handles script initialization failures and the arm-only script's missing
outer `finally`. It does not disable arm torque or replace the last arm goals;
an arm can still finish moving toward its most recently commanded goal.

The owning browser sends a heartbeat every 500 ms. Closing it requests Stop;
loss of heartbeats for 5 seconds also requests Stop. Other viewing tabs do not
renew the owner lease. Closing the simulator stops its tracking process. Source
reload is deferred while either tracking or normal robot playback is active.

After 3 seconds without a cooperative exit, the supervisor terminates the
tracking process. The worker also has a shutdown deadline for loss of its parent.
The UI explicitly labels forced termination as **stop unconfirmed** because a
dead process is not proof of a physical cart stop. The supplied cart watchdog
behavior is not replaced or requalified by this integration.

## Runtime and models on this computer

`configs/tracking.json` selects the existing Python environment at
`../../TakeOne/.venv/Scripts/python.exe`, resolved from the project root.
This keeps the simulation and robot playback dependencies unchanged. The
non-actuating dependency check is:

```powershell
Set-Location 'C:\Users\nonst\Documents\Python\TakeOne_Astra\TakeOne'
.\scripts\Check-Tracking.ps1
```

This imports libraries and checks source hashes without importing either user
script or constructing a camera or motor. The inspected environment provides
OpenCV 5.0.0, MediaPipe 1.0.1, NumPy 2.5.3, pyserial 3.5 and `scservo_sdk`.
If relocating the project, point `python` at an environment with those imports
and run the check before starting tracking.

Both existing model files were copied into `.runtime/tracking/models/`:
`pose_landmarker_lite.task` and `blaze_face_short_range.tflite`. This is the
configured worker's working directory, independent of where the app was started.
The original scripts download missing models on Start; the supplied download
logic is unchanged. The local model cache and tracking run output are gitignored.

## Logs and verification

Each run creates `data/runs/tracking-<run_id>/worker.log` and `run.json`. The
panel's **Tracking run log** disclosure gives the directory. The worker log
contains original script output, errors and lifecycle events. The final manifest
includes selected mode, arm setting, source hash, exit code and whether cleanup
completed. These are process/command records, not measured cart motion.

Focused verification covers all three mode combinations using the byte-preserved
scripts with fake camera/model/serial dependencies, unchanged initial goals,
arm suppression, startup cancellation, cart zero on stop, cleanup, worker crashes,
forced termination, browser lease loss, local HTTP authorization and mutual
exclusion. Browser-client checks cover double clicks, Stop during startup, stale
polls, ownership and page-close Stop. No simulation, physical tracking session,
camera access or motor movement was performed during integration.

Validation on 17 September 2026: 16 Python integration/lifecycle tests and
15 JavaScript tracking/panel and existing robot-client tests passed, as did
focused lint, formatting, JavaScript syntax and source hash checks. The two
real subprocess tests run only harmless Python fixtures, including one that
deliberately ignores control input. They do not import or run tracking code.

Browser automation was unavailable for visual inspection. An isolated mock
panel can be opened by running `node apps/rehearsal/tests/tracking-ui-preview.mjs`
and visiting the printed local URL. Its Start/Stop actions are mocked and it
does not expose any real tracking API or start a simulation. Close that test
server with Ctrl+C when finished.


## Windows arm USB startup recovery

If Windows reports `Cannot configure port` with device-not-functioning error 31,
tracking now closes any partial serial handle and retries opening up to three
attempts, waiting 0.5 then 1.0 seconds. Each attempt validates the configured USB
identity. Stop interrupts those waits. Access-denied errors are not retried, and
neither motor writes nor an active tracking session are replayed by this recovery.
The existing same-baud check continues to avoid a redundant SDK close/reopen.

On September 20, COM9 failed with the same error in both the tracking runtime and
the separate diagnostic runtime, while COM8 opened. A full phone-controller reset
(disconnecting both USB and motor power before reconnecting) was followed by a
successful user-started tracking run and five successful connection cycles, each
reading all expected phone motors at 1 Mbps. This is evidence of recovery, not a
guarantee against future USB/controller faults. For a recurring failure, support
the arm and fully disconnect both power sources; an ordinary USB-only reconnect
may not completely restart the controller.

Read-only repeat-test evidence: `data/verification/tracking-phone-cold-start-20260920.json`.
The preceding worker and tests are saved under
`data/recovery/tracking-usb-startup-20260920/`.
