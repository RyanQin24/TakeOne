# iPhone zoom timing

## Native focal-length control (September 20)

The configured iPhone 17 Pro Max reports `focalLength: {min: 24, max: 360}`
from `/lens/zoom/description`, and both `focalLength` and `normalised` from
`/lens/zoom`. Blackmagic's documented PUT accepts an integer `focalLength`.
TakeOne uses that native path when the device identity matches calibration,
the reported minimum matches the operator's measured wide-end focal length at
normalized zero, and a valid focal-length readback is available. It retains the
measured normalized mapping for devices that do not meet these conditions.

Capabilities are read again on Start filming, before preparation or motor
commands. The capture configuration contains the reported range; the saved
calibration is unchanged. Readbacks use the same units as the commands. Native
commands are rounded to whole millimetres as the API specifies.

The HackTheNorth second shot holds 24 mm for 0–2 seconds, zooms to 180 mm from
2–3 seconds, and holds until 5 seconds. This is authored timing, not a measured
wireless response guarantee. Verification used read-only handset requests and
mocked control tests; no new recording or motor run was performed.

Reference: [Blackmagic Camera Control manual](https://documents.blackmagicdesign.com/DeveloperManuals/BlackmagicCameraControl.pdf), Lens Control API.

The historical mapping and command-timing measurements below describe the
previous normalized-control path, which remains the fallback.

TakeOne sends the prepared shot's focal curve through the operator-measured
zoom mapping. The current handset is measured at 24 and 48 mm. Intermediate
framing is estimated; no physical lens selection or optical continuity is
verified by the REST acknowledgement.
The Zoom in/out presets now default to 24-to-48 mm and 48-to-24 mm, respectively,
so a newly prepared default shot stays within that measured range. Existing
reviewed plans retain their authored focal lengths and must be prepared again.

## September 19, 2026 correction

The previous loop sent PUT and GET for every zoom update, then slept for a
whole update period. Recording and format checks also blocked that loop.
Each REST request incurred another HTTPS handshake because this iPhone closes
the connection after its response. Sparse camera cues were held until the next
cue rather than interpolated.

The corrected implementation:

- Interpolates the reviewed samples against the robot's monotonic shot clock.
  Identical adjacent samples retain authored holds. Late updates use the latest
  target, without replaying a backlog or changing the reviewed motor timing.
- Aims for 20 zoom updates per second. Network time is included in each period.
- Prepares at most two upcoming HTTPS connections while commands are being
  sent. Each connection is certificate checked before any command is sent.
  Commands remain sequential, with no automatic retry of an uncertain PUT.
  Unused sockets are closed and old idle sockets discarded before use.
- Reads zoom back at the initial position, periodically during a ramp, and at
  the final ramp endpoint. Other samples explicitly say `http_acknowledged`
  and have `observed: null`; they do not claim measured positions.
- Checks recording and format in a separate thread. Failures still set the
  shared stop event, and capture cleanup still stops its own recording.

Before/after source mapping: `PhoneTake._run` now owns connection preparation;
`_run_zoom` handles scheduling, `_target_at` interpolates cues, and `_health`
monitors the recording. `BlackmagicCamera.request` uses `_connect` for pinned
connections and `_request_connection` for the optional zoom prefetch queue.
The original files were copied to `data/recovery/zoom-cadence-*` before edits.

## Actual handset evidence

The final camera-only test used 1920x1080, 60 fps, HEVC on the configured
iPhone 17 Pro Max. It recorded an eight-second linear 24-to-48 mm ramp:

- 145 accepted zoom commands, including the initial pre-record position.
- 144 commands during the ramp, approximately 18 per second.
- Median acknowledgement interval: 49.8 ms; maximum: 217.8 ms.
- Initial, periodic and final zoom readbacks; final target confirmed.
- Recording start and stop confirmed; no camera error; no robot movement.
- Report: `data/phone-tests/50902f5a41e2ead5833aeaf5/phone-capture.json`.

The earlier recorded robot run had eight changing zoom commands over roughly
eight seconds, with a median acknowledgement interval of 1.11 s. These are
different runs under variable Wi-Fi conditions, not a controlled speedup test.

This is command timing evidence, not a visual smoothness measurement. The movie
has not been transferred or inspected. A 60 fps recording does not imply
60 Hz REST zoom control. Wireless delays can still produce visible steps.
The iPhone's served `lensControl.yaml` exposes position commands, but no timed
zoom ramp or physical-camera lock in the zoom API. Keep a single physical lens
selected on the handset and visually check the test before filming a moving
robot take. Do not relabel calibration or change lenses to hide a framing jump.

## Repeat a camera-only test

Keep Blackmagic Camera open and the local TakeOne server running. The following
starts a real eight-second recording, changes zoom from the lowest calibrated
focal length to 48 mm, and stops. It never opens motor ports. Phone ownership,
format, color setup and calibration checks still apply.

```powershell
$phoneStatus = Invoke-RestMethod 'http://127.0.0.1:8766/api/phone/status'
$phoneHeaders = @{ 'X-TakeOne-Phone-Token' = $phoneStatus.token }
Invoke-RestMethod 'http://127.0.0.1:8766/api/phone/test-record' `
  -Method Post -Headers $phoneHeaders -ContentType 'application/json' `
  -Body '{"seconds":8,"end_focal_mm":48}' -TimeoutSec 30
```

Omit `end_focal_mm` to retain the existing fixed-lens recording test.
Refresh Shot Studio and prepare the shot again before the next robot run so
the run snapshot includes the updated zoom rate.

## Verification

The final focused runs passed 73 tests across phone cadence, TLS certificate
pinning, routes, lens timelines, orientation, lens curves, camera integration
and mocked robot playback. No real motor ports were opened by those tests.
Ruff lint and formatting passed for the changed Python files.

`scripts/TakeOne.ps1 -Command test` was also run. All 335 browser tests,
integrity checks and repository lint passed, but the full gate did not pass.
The broad Python/simulation runs overlapped source edits and triggered the
planner's stale-source guard; other failures included missing media executables
and existing test expectations. The browser syntax gate stops on stale editor
CSS tokens, and repository formatting reports five other files. The 73 focused
checks were run again after the functional edits in fresh processes.
Full results are in `data/verification/summary.json`; the previous evidence was
preserved in `data/recovery/zoom-verification-20260919-142652`.
