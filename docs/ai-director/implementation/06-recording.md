# Package 06 partial implementation: offline recording

Date: 2026-09-13. Status: **superseded on 2026-09-17**.

> The offline recording *page* this document specifies has been replaced by the
> Record page in prompt 16: a witness monitor beside the planned frame, a
> framing gate, and real iPhone capture through `packages/takeone/phone/`. The
> lifecycle described below - the single-writer state machine, the SQLite
> evidence trail, the idempotency ledger, the one-unresolved-take invariant and
> the voice quiet latch - is unchanged and still authoritative. Only the surface
> and the fixture affordances are gone.

## Historical September 14 call handoff

**Subsequent call decision:** Caesar owns the workflow and Shot Studio. Basil is
assigned video-editor work and is awaiting Caesar's documentation and plan.
Environment preparation is recorded in [the editor handoff](../../editor/README.md#september-14-ownership-and-preparation).
The questions below are retained as call context, not an instruction for Basil
to start a new recording adapter. No new camera or provider choice was made.

Caesar (`Zwc-11`) merged [recording PR #2](https://github.com/Zwc-11/TakeOne/pull/2)
at `2026-09-13T23:46:01Z`, merge commit `dabc047`. Voice PR #1 was already merged.
The latest inspected main is `0ddd15d`, following `aacb916` (production workflow
and unified UI) and `7916988` (historical cleanup and on-demand rendering).
This update is documentation only and does not establish current-main test or
physical readiness.

### What Basil has delivered

- Merged offline voice foundation and UI, with fixture-based conversation and
  recording-silence logic. Live microphone/provider voice is not accepted yet.
- Merged offline recorder: simulated start/stop acknowledgements, persistent
  takes, validated synthetic clips, playback, recovery and voice suppression.
- Camera-control research and the device acceptance checklist below. No camera
  app, programmable endpoint or phone model is selected by those notes.

### What changed on Caesar's side

The Director now authors exact movement settings and opens the saved script in
the studio. Multi-shot rehearsal includes staging, a shared timeline and
simulated repositioning. See [timeline/previs](03-timeline-previs.md) and
[movement authoring](04-director-movement-editor.md). The previous note that
nothing consumes the manifest is superseded; do not rebuild that bridge.

The studio, Director, voice and recording pages now share the updated UI. The
editor remains a separate local process. The simulator offers a movement library,
phone framing and timed zoom/Dolly Zoom cues, but these are not phone capture or
zoom transmission. Its iPhone 17 Pro Max profile does not confirm a device change
from Ryan's last Samsung / possible iPhone 16 report.

### Local follow-up work and evidence boundaries

Basil's unpublished `fix/offline-recording-validation` branch is preserved
through `b07f45e`. Its test repairs overlap Caesar's `afe088c` and subsequent
changes, including the coordination fixture's move to `tests/support`.
Do not apply that branch wholesale or restore the historical plan files removed
upstream. Reconcile only still-needed changes with the current owner first.

A local seven-check run at `463558c` passed 399 product, 29 simulation and
150 web tests, plus syntax, integrity, lint and formatting. A test-only follow-up
at `6d1fd36` passed eight focused motion-intent tests. These are dated local
results, not validation of the current main. Evidence is retained locally under
`/tmp/takeone-recording-xEzY8j`; no raw media or device receipts belong in this PR.

Independent review found an unresolved numerical issue in the older planner's
`planning.kinematics.pointing_basis`. With position `(0,0,0)`, reference right
`(0,1,0)` and look-at `(x,0,+1)` or `(x,0,-1)`, increasing positive `x` from
`0.9e-9` to `1.1e-9` flipped the returned right axis and the calculated roll error
from 0 to 180 degrees. The function remains unchanged at inspected main
`0ddd15d`. This is numerical evidence, not an observed robot rotation; it is
distinct from the new preview camera layer's horizon handling. Assign and
reproduce it on the current integration path before changing planner behavior.

### Decisions to leave the call with

1. Name Caesar's remaining Director/editor/robot tasks and Basil's next independent
   voice or recording task, with one owner for each integration boundary.
2. Confirm actual phone/model, app, Windows host and recording destination:
   phone-original footage or a stream recorded on Windows.
3. Identify supported start/stop/zoom commands, or explicitly agree that the
   first demo uses manual camera control. A remote slider is not a callable API.
4. Agree who tests live voice and actual captured-audio silence, who supplies a
   representative real take, and who owns on-site integration and recovery tests.
5. Assign the planner defect and current-head full verification separately from
   camera integration. Simulated success does not qualify physical motion.

No production fix, hardware experiment or new camera/provider choice is part of
this handoff. The existing offline failure tests remain the adapter foundation.

This slice plans and records a synthetic test timeline, acknowledges simulated
start and stop, validates a generated MP4, and exposes authenticated playback.
An offline text question demonstrates the existing voice gate. No microphone,
provider, camera, motor or physical recorder is opened. No Director production
revision, accepted script, shot plan or real take is changed. Package 06 is not
complete and live recording remains unavailable.

## Setup and walkthrough

Use the existing root environment and web dependency from `scripts/Setup.ps1`.
Install FFmpeg with ffprobe available on `PATH`; missing tools produce a failed
take with no playback. There are no new Python or npm dependencies. Start the
existing simulator server with `scripts/TakeOne.ps1 -Command simulator`, then
open `http://127.0.0.1:8766/record.html`. The voice page has a small navigation
link. End an existing voice rehearsal first: a foreign active owner is protected.

An isolated macOS/Linux rehearsal can use an explicit external Director database:

```bash
.venv/bin/python apps/rehearsal/server.py --port 8879 --director-db /tmp/takeone-recording-demo/director.sqlite3
```

1. Click **Start offline session**. The page does not connect on load. This
   standalone test uses fixture context, with `source=simulated` always visible.
2. Ask a text question. Its reply is labelled `source=fixture`. Enable the
   three-second reply delay to test a request that is still pending.
3. In **Test settings**, choose zoom start/end, timeline duration and scenario.
   Click **Start simulated take**. Local pending output is immediately discarded;
   the server closes its fixture gate before simulator dispatch. Start requested
   is distinct from recording acknowledged.
4. Click **Stop simulated take**. A stop acknowledgement starts finalization;
   it does not prove that a file exists. Questions stay quiet until confirmed
   terminal evidence releases the gate, or explicit recovery retires uncertainty.
5. A ready take offers **Load test clip**. Authenticated download must succeed
   before a video URL is attached. Use the native **Play** control; there is no
   autoplay. The clip is an unmistakable synthetic pattern and tone.
6. Use **End session**. If ownership is retained for unfinished capture, retry
   any saved request, recover the unfinished simulated take, then End again.

The page retains only its offline owner and exact pending recording request in
per-tab `sessionStorage`; it never persists transcripts. This deliberately keeps
the offline credential across reloads instead of expiring it with the page.
Reload offers explicit **Restore this tab’s session**, checks
`/api/voice/snapshot` ownership first and then reads take status. It does not
replay a mutation. A replaced runtime or
wrong owner discards the stale identity. Confirmed End clears it. A storage
failure stays visible because reload recovery then cannot be guaranteed.
Navigation stops local polling, listeners and playback while retaining recovery
identity; it does not silently disconnect a potentially unresolved capture.

If the initial creation response itself is lost, its once-returned owner token
cannot be reconstructed. End from the owning tab if available, or restart the
local test server and explicitly create a new session. This differs from a lost
recording response, whose request identity was saved before dispatch.

## State, timing and recovery

The take lifecycle is `starting`, `recording`, `finalizing`, `ready`, `failed` or
`unknown`. A UUID, original immutable start request/fingerprint, source, zoom,
original context and ordered events are persisted. Requested and acknowledged
host times are decimal-string monotonic nanoseconds associated with the event’s
producer epoch. The displayed timeline distinguishes request from acknowledgement.
It must not be compared with another device’s clock without measured mapping.

`ZoomRamp` uses dimensionless `start_factor` and `end_factor`, plus integer
`duration_ms`. Simulator limits are 1× to 4× and 250 to 10000 ms. Invalid values
are rejected, not silently clamped. The signed rate is factor per second and
interpolation clamps to its endpoints. These are simulator bounds, not measured
phone capabilities. The clip’s duration follows the requested synthetic timeline,
not elapsed time between browser clicks. Timed optical zoom is not implemented;
DollyZoom additionally requires coordinated translation and calibrated optics,
which this slice does not provide.

| Scenario or failure | Observable result and recovery |
|---|---|
| `normal` | Default start acknowledgement after 100 ms; stopping after acknowledgement finalizes and validates the synthetic clip. Stopping before acknowledgement retires the take as failed without media. |
| `delayed_start` | Start requested remains distinct until the default 2000 ms acknowledgement. |
| `start_timeout` | No start acknowledgement by the default 3000 ms deadline; unknown capture requires explicit recovery. |
| `disconnect` | Stop cannot be confirmed; questions remain quiet until recovery. |
| `stop_timeout` | Stop deadline expires without acknowledgement; explicit recovery retires the take. |
| `save_failure`, `corrupt_media` | Confirmed stop may release questions, but take stays failed and has no playable media. Start a new test take. |
| Lost recording response | Keep the exact request body and ID. **Retry saved request** reconciles acceptance without creating a duplicate take. |
| `finalization_busy` | A recovered writer is still exiting. Retry the saved stop while its envelope is valid; if explicitly rejected as expired, issue a fresh stop. |
| Failed poll or expired fixture evidence | Questions become quiet locally. **Refresh status** checks current evidence; ordinary read polling also resumes when the service returns. |
| Failed media download | No fallback clip is attached. Refresh and load the same validated take again. |
| Server restart | Unfinished takes become unknown; no old clock deadlines or media jobs resume. Explicit new offline ownership can recover prior-runtime work. Ready history remains available. |

Start, stop and recovery are idempotent within the current authenticated runtime.
Persisted take and operation identities survive restart, but old HTTP ownership
and accepted-envelope metadata do not; use the restart recovery flow above.
Exact accepted retries use their original generation and expiry, even when
current metadata changed. Changed
reuse fails as a conflict. New mutations fetch current server timing and owned
scope/generation; the page does not reuse its initial runtime timestamp.
Status is reconciled by voice snapshot sequence/generation, and local lifecycle
and question barriers reject late responses after capture, End or replacement.
Polling and expiry timers are stopped on End/unload. Blob URLs are revoked when
replaced, suppressed or destroyed. Recovery never invents completed media.

## Local routes and storage

All recording GETs except runtime, and all recording mutations, require
`X-TakeOne-Voice-Token`. Tokens never appear in URLs, manifests or persisted
server recording evidence. Unsafe Host/Origin, unknown body fields, malformed
identities, arbitrary paths and unvalidated media are rejected.

| Route | Purpose |
|---|---|
| `POST /api/voice/sessions` | Explicit `{schema_version: 1, mode: "offline"}` creation; returns the owner token once. |
| `GET /api/voice/snapshot` | Check current ownership, scope and generation, including explicit restore. |
| `POST /api/voice/questions` | Existing bounded offline fixture question, optionally `fixture_delay_ms`. |
| `POST /api/voice/disconnect` | End; `ownership_retained` requires capture cleanup before identity removal. |
| `GET /api/recording/runtime` | Current server time, request TTL and labelled simulator limits. Real recorder readiness remains false. |
| `GET /api/recording/takes` | Latest 100 synthetic takes, newest first, with current owned voice snapshot. |
| `GET /api/recording/takes/<UUID>` | One take and reconciled voice snapshot. |
| `POST /api/recording/start` | Existing strict voice envelope plus `request_id`, `zoom` and `scenario`. |
| `POST /api/recording/stop` | Strict envelope plus `request_id` and `take_id`. |
| `POST /api/recording/recover` | Same shape as stop; explicitly retire unfinished simulated work. |
| `GET /api/recording/takes/<UUID>/media` | Authenticated validated MP4 bytes; no query parameters or token in URL. |

The envelope contains `schema_version`, `voice_session_id`, `scope`, `generation`
and decimal-string `expires_monotonic_ns`. Runtime supplies decimal strings
`now_monotonic_ns` and `mutation_ttl_ns`. One unresolved take and one bounded
media finalization are allowed at a time. Media work stays outside voice locks.
Read/status polling renews idle fixture authority only when unresolved capture
does not own the gate. The old manual idle/stopped fixture controls cannot
release an active take. Gate observations remain `source=fixture`, never real
recorder evidence; `recorder_ready=false` and live capture stay unavailable.

By default the SQLite store is `data/director/recording/takes.sqlite3` and media
is in `data/director/recording/media/<take UUID>/`. With `--director-db`, that
`recording/` directory is a sibling of the chosen Director database. These
outputs under the default directory are ignored by Git. A custom database path
does not automatically ignore its sibling media directory; choose an external
temporary directory or an explicitly ignored worktree directory for test output.
Originals are never overwritten.

FFmpeg writes a unique partial MP4 using H.264 `testsrc2` video and AAC sine-wave
audio. Bounded generation and full decode validation check nonempty media, expected
streams, duration and checksum before publication. Stored manifests include
probed metadata, requested timeline, synthetic lineage and
`real_media_verified=false`. The download route rechecks actual size and SHA-256;
changed or missing bytes cannot be served as ready media.

Decode validation uses `-xerror -err_detect explode`: recoverable decode errors
must fail publication even when permissive FFmpeg decoding would exit zero.
`tests/test_recording_media.py` covers damaged-packet rejection by both the writer
and take lifecycle, using FFmpeg/ffprobe discovered through `PATH`.

Take context is the original read-only snapshot from its owner/scope at start,
including optional accepted Director context when the API caller supplied it.
The minimal page creates a standalone fixture session. A later session can read
historic synthetic takes without rebinding their context to a new production.
No request advances the Director state machine to real Review.

## Verification and remaining acceptance

The Task 3 client verification recorded 30 passing Node tests with complete
representative HTTP fixtures and injected request/timer/storage/media edges.
Task 1 and Task 2 separately exercised real SQLite, loopback HTTP, FFmpeg decode,
media integrity, restart and gate ownership, including 23 recording HTTP tests.
Client RED/GREEN evidence is under `/tmp/takeone-recording-xEzY8j/task3-*.log`.
The complete verifier passed once at `2026-09-13T07:44:08Z`: 283 product tests,
28 simulation tests, 121 web tests, JavaScript syntax, repository integrity
(1086 LeRobot files), Ruff lint and Ruff formatting. The exact seven commands,
exit codes and individual logs are indexed by
`/tmp/takeone-recording-xEzY8j/task3/summary.json`.

Served-browser acceptance exercised all seven scenarios, explicit session
creation/restore/End, delayed-question suppression, recovery, persisted take
identity and native ten-second clip playback to completion on desktop and a
390 x 844 mobile viewport. Actual browser failures led to three scoped fixes:
native timer receiver binding, revoking loaded/late playback on lost quiet-gate
evidence, and displaying stop requested until acknowledgement exists. Follow-up
browser checks confirmed each behavior. The app body fits the mobile viewport;
the browser's injected overlay still affects root-document scroll width, so this
is not a claim that extension-owned layout is clean. Final whole-branch review,
final-head verification and publication are tracked separately from these checks.

After those fixes, `/tmp/takeone-recording-xEzY8j/final-local/summary.json`
records all seven checks passing at `2026-09-13T16:42:16Z`: 283 product tests,
28 simulation tests and 129 web tests, plus syntax, integrity, lint and format.
The separately checked `apps/rehearsal/server.py` also passed Ruff in that run.
These results predate the final strict-decode correction and its damaged-packet
regressions. Fresh verification of the consolidated change, publication to a new
PR and PR/CI results remain pending. No absent CI job counts as a passing run.

Real acceptance still needs the selected phone and app/control interface,
capability discovery, explicit device ownership, real start/stop/file evidence,
camera and audio interruption behavior, measured zoom bounds, latency/clock
mapping, and operator-supervised failure recovery. Recorder silence must be
measured on the integrated device. Camera perception, physical motion,
DollyZoom, real take critique and editing are outside this offline slice.
Completing and publishing this branch does not imply a merge into main.

## September 13 camera update and Windows research

Ryan's Discord update supersedes the earlier iPhone-only assumption: the current
camera is his Samsung Android; an iPhone 16 may be tried. He requested Windows
webcam support and/or USB zoom commands. Exact Samsung model, OS versions, app,
lens and recording destination remain open. The offline recorder remains useful
for lifecycle, voice suppression, media validation and failure rehearsal on
either platform. Its simulated acknowledgements cannot be relabelled as device
evidence when an adapter is added.

Ryan also supplied [this servo listing](https://www.amazon.ca/dp/B0FVS5HD2V).
The shared preview advertises STS3215 servos; the page could not be fetched here.
A seller link is not evidence of the installed arm configuration, calibrated
limits, payload or stop behavior. No hardware mapping is changed by this update.

Research checked September 13, 2026. These are candidates, not selected dependencies
or tested rig capabilities:

| Candidate | Evidence | Remaining gap |
|---|---|---|
| DroidCam OBS | Vendor documents Android and iOS USB video into OBS on Windows, plus Pro remote zoom/focus/exposure controls. Android needs USB debugging and possibly device drivers; iOS needs Apple USB drivers and trust. | The documented remote may use Wi-Fi even while video uses USB. This does not establish a supported command API, USB-only control, zoom-factor feedback or timed ramps. Device/lens availability varies. |
| Camo | Vendor documents iPhone-to-Windows USB video and Android USB video with debugging enabled. | Webcam transport does not establish a programmable zoom API. Its separate iOS producer SDK targets commercial partners/collaborators; it is not evidence of a public Windows zoom-control endpoint. |
| Apple Continuity Camera | Apple documents iPhone webcam use with a Mac. | Not the team's Windows solution. USB-C alone does not imply generic webcam or camera-control support. |

Sources: [DroidCam OBS usage](https://droidcam.app/obs/usage/),
[Camo setup](https://camo.com/support/camo/camo-getting-started),
[Camo SDK scope](https://camo.com/support/camo-sdk/overview-camo-sdk),
[Apple Continuity Camera requirements](https://support.apple.com/en-us/102546).
No app was installed, purchased or tested with a phone during this research.

Recommendation, not a team decision: test DroidCam OBS on the already available
Samsung first, then the candidate iPhone 16 if needed. Keep Camo as a video-path
alternative. Do not implement against undocumented zoom endpoints or screen-click
automation. A supported programmatic control path must be demonstrated before
promising a callable `zoom_in/out` or timing accuracy.

If the team accepts recording on Windows, OBS is a candidate recording endpoint:
its built-in WebSocket interface can automate recording. It must remain
authenticated and restricted to the local/trusted control environment. This
would record the received stream, not prove a phone-original file was saved.
OBS source cropping/scaling is not phone lens zoom. Neither webcam transport nor
OBS recording alone implements DollyZoom. See the [OBS remote-control guide](https://obsproject.com/kb/remote-control-guide)
and [recording request protocol](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md).

### Next evidence, before choosing the adapter

1. With the robot parked and an operator present, record the actual phone, OS,
   app/plugin versions, lens, cable, Windows version and recording destination.
   Start with a static subject and no robot movement.
2. Prove Windows USB video and a saved, decodable clip. Measure resolution, frame
   rate, audio routing, latency, disconnect behavior and whether capture survives
   app backgrounding/phone interruption. Preserve the original file and checksum.
3. Prove zoom independently: a documented command from code, accepted/achieved
   values, zoom range and steps, optical versus digital behavior, lens switching,
   and whether control still works with Wi-Fi disabled. A working remote slider
   is only manual-control evidence.
4. Only after command control works, measure a bounded ramp in both directions:
   requested endpoints/duration, observed endpoint error, start latency, jitter
   and cancel/disconnect behavior. Agree tolerances from the shot requirement;
   do not inherit the simulator's 1x-4x or 250-10000 ms limits.
5. Select one adapter and connect its real start/stop/file evidence to the
   existing recorder and voice gate. Preserve offline failure tests. Verify
   silence from the actual captured audio, not only a UI indicator.
6. DollyZoom comes after camera control: on-site calibrated translation and
   focal-length/framing coordination, shared timing and an operator-approved
   motion envelope. A smooth digital zoom alone is not that acceptance test.

Basil can own the command/API investigation, recording adapter and offline tests
after the endpoint is chosen. Ryan and Caesar supply device evidence and perform
rig tests. The offline PR is merged. Agree the next integration boundary using
the call checklist above; do not guess a phone protocol or duplicate the studio.
