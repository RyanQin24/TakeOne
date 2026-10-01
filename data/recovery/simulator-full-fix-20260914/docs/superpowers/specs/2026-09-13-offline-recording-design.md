# Offline recording preparation

Approved scope: Basil's September 13 request to continue the proposed simulated
recording flow, verify it and finish the independent work without waiting for
the on-site team's phone details. This is partial package 06, not its real-device
acceptance. Ryan has requested timed zoom and DollyZoom. His September 13 update
confirms Samsung Android is in use; iPhone 16 is a candidate, not a selected rig.
The exact Samsung model and recording app/control interface remain unconfirmed.
Research Windows USB video and command-controlled zoom separately. This update
does not select an app or expand the offline slice into a real device adapter.

## Outcome and approach

One explicitly offline page in the existing app exercises start request,
simulated acknowledgement, stop, finalization, validation and playback of a
synthetic test clip. It also runs an offline text question through the existing
voice service so recording suppression is observable end to end. No microphone,
provider, camera or motor is opened. The existing voice page stays visually intact.

Of three possible paths, use the reusable recorder lifecycle with a simulated
device now. Waiting for a phone would prevent independent testing. Choosing a
native app or remote camera product now would settle an unknown team decision.

Product implementation belongs under packages/takeone/recording. A small service
owns take-specific state and a SQLite store; it does not replace the Director's
production state machine or advance real productions to Review. A concrete
simulated phone supplies acknowledgements. Media generation/inspection uses local
FFmpeg/ffprobe with bounded subprocesses. App routes and a thin page consume it.

## Contracts

- Every take has a UUID, immutable start request identity/fingerprint, original
  read-only Director/voice context, simulator source, event history and zoom intent.
- Start, stop and recovery requests are idempotent. Conflicting reuse fails.
- State distinguishes starting, recording, finalizing, ready, failed and unknown.
  A start request is not acknowledgement. Stop acknowledgement is not a saved file.
- Persist transitions and their events together. Restart marks unfinished work
  unknown; it never restarts a device, job or old clock deadline. Explicit simulated
  recovery retires the unfinished take without inventing a completed clip.
- One unresolved take and one bounded media finalization at a time. Slow media
  work stays outside voice locks; no inference or media processing enters motors.
- A ZoomRamp states start_factor, end_factor and duration_ms. Values are finite,
  positive and checked against explicit SIMULATOR limits of 1x to 4x and 250 to
  10000 ms. Interpolation clamps to endpoints; the derived factor-per-second rate
  is signed. These bounds are not iPhone capabilities. Invalid or unsupported
  intent is rejected, not clamped silently. DollyZoom remains unsupported because
  coordinated physical translation and calibrated optics are absent.
- Synthetic clip duration follows the requested test timeline, not the elapsed
  time between browser clicks. Manifest fields distinguish simulated media time
  from actual host request/acknowledgement times and include the producer epoch.

## Voice and HTTP integration

Reuse the loopback server, strict request parsing and existing voice owner token,
scope, generation and expiry checks. A recording page explicitly creates an
offline voice session. Capture requests suppress local output immediately and
close the server voice gate before simulated device work. Gate observations are
source=fixture, never recorder; recorder_ready stays false and live remains
unavailable. An active take cannot be released by the old manual idle/stopped
fixture controls. Stop/recovery routes remain available while questions are quiet.

Bind the recording to its originating voice owner and scope. Late results cannot
affect replacement owners or other takes. Read-only accepted Director context can
be retained when supplied; standalone testing is allowed and explicitly labelled.
No Director production revision, accepted script, plan or real take is changed.

The recording page retains only its own offline owner and pending request recovery
identity in per-tab sessionStorage until confirmed End, to survive a reload. It
does not persist transcripts, auto-start a session or auto-replay a mutation.
Restore is explicit and first checks server ownership. Storage failure is visible;
after confirmed End or a definitively replaced runtime the stale identity is removed.

All media routes resolve server-owned take IDs, not arbitrary paths. Deny unsafe
Host/Origin, missing/wrong token, malformed bodies, path traversal and media that
is not validated. Never expose a voice token in URLs, manifests or persisted logs.
After restart, validated synthetic files remain available via an explicit local
test session; unfinished takes require explicit recovery. Historical context is
not silently rebound to a new production.

## Media evidence and failure behavior

Generate a small unmistakable test-pattern MP4 with synthetic audio. Store it in
a unique take directory outside Git, first as a partial artifact. Validate full
decode, nonempty content, duration, expected video/audio streams and checksum
before publishing the final path. Do not overwrite existing originals. Persist
actual probed metadata and mark real_media_verified=false even when the synthetic
artifact is valid. A missing tool, disk error, corrupt clip or partial transfer
cannot reach ready or enable playback. Never serve another file as a fallback.

Explicit simulator scenarios cover delayed acknowledgement, start timeout,
disconnect/unknown stop, stop timeout, save failure and corrupt media. Deterministic
clock injection drives timing tests; no repeated wall-clock retries until green.
On acknowledged stop, a failed save may release the voice gate while the take stays
failed; an unconfirmed stop keeps it quiet until explicit recovery.

## UI and verification

The recording page is a restrained utility companion to the approved voice UI:
existing neutral charcoal/system typography, no decorative cards or dashboard,
one clear status and primary action, collapsed test options, accessible controls
and visible offline provenance. A small link makes it discoverable. It displays
zoom start/end/duration, requested/acknowledged states, failure/recovery, and a
playable synthetic clip only after validation. Media does not autoplay.

Use TDD, real temporary SQLite and loopback HTTP, actual FFmpeg decode checks,
browser desktop/mobile walkthroughs and the complete seven-check verifier. Tests
cover duplicate/conflicting IDs, stale owners, restart, quiet questions and late
replies, delayed/failed acknowledgements, file integrity and invalid zoom values.
Retain evidence outside Git. Update package 06 as in_progress and write its
implementation record. Correct the old package 05 merge-hold wording with the
already verified PR #1 outcome. Do not implement camera perception, physical
motion, live voice, actual take critique or editing.
