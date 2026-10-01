# Remote voice/conversation slice for TakeOne

Date: 2026-09-12. Status: written specification approved by Basil for implementation.
No voice implementation or live-provider verification is
claimed by this document.

**Historical specification:** Consult the [package 05 implementation record](../../ai-director/implementation/05-rehearsal-voice.md) for delivered behavior, enforced limits, preservation-audit changes and current acceptance evidence. The design targets and pre-implementation baseline below are not a report of the shipped slice.

## Authority and ownership

Basil reports that Caesar accepted this division: Caesar is working on packages
01-03; Basil owns the voice/conversation portion of package 05, developed in
TakeOne with simulated scene and recording events. The on-site pair has the
robot. Their presence does not establish ownership or completion of every
camera and recorder integration.

This implements the narrow scope Basil approved, not all of
[package 05](../../ai-director/prompts/05-rehearsal-voice.md). The existing
[delivery plan](../../ai-director/delivery-plan.md),
[implementation rules](../../ai-director/implementation-rules.md), and
[Director decision](../../ai-director-decision-2026-09-12.md) remain the shared
baseline. Later explicit team decisions take precedence.

Reviewed application baseline: `0da7950d79df5cf777da41f1decdfb64bacd7365`.
Develop on `feat/voice-conversation` in an isolated worktree. Preserve the
original AUTEUR repository and do not wholesale merge its code or private docs.

## Observable first result

In the existing local TakeOne app, a creator opens the voice page, explicitly
connects the microphone, asks for help, sees the conversation text, hears a
response, interrupts it, and disconnects. An explicit offline mode exercises
conversation events and the audio gate without a provider, microphone, camera,
or robot. Offline fixtures are visibly labelled and never presented as real
AI-generated speech or observations.

The creator can test recording-request, start-uncertain, recording, and
stop-confirmed scenarios. A recording request immediately silences ordinary
speech, cancels pending conversational work, and prevents late results from
speaking. A planned line containing "cut" or "stop" cannot control recording
or movement.

Live conversation requires explicitly configured access and an approved live
test. Missing access leaves live mode unavailable. It does not switch to a
different provider or secretly use fixture replies.

## Architecture and selected approach

Use a small voice page served by the existing application, backed by a focused
voice module in `packages/takeone`. Keep the existing Python/vanilla JavaScript
stack. This page is an integration surface inside TakeOne, not another product,
server fleet, or Director implementation.

The alternative is embedding all controls directly in Caesar's evolving
Director screen. Defer that UI placement until packages 02-03 stabilize; keep
the voice module usable by that screen without changing the shared contracts.

Retain the team's selected GPT-Live 1 with client delegation. The provider
handles spoken conversation; TakeOne supplies verified context and validates
delegated results. Do not introduce a separate speech-recognition, reasoning,
and speech-synthesis pipeline or select another model in this slice.

The application server handles permanent credentials and authenticated session
setup. The browser handles microphone permission, media transport, transcripts,
and local playback. Backend task authority stays on the server. A browser
transcript or provider delegation is never an authenticated operator command.

Normal page load and imports perform no provider call, microphone acquisition,
camera discovery, serial-port access, or device connection. Live connection is
an explicit user action with a visible connected state and disconnect control.

## Boundaries with Caesar and the capture team

Reuse the existing Director session ID, runtime epoch, revision, cancellation
generation, plan ID and take ID. Do not replace its session owner, transaction
rules, job identities or SQLite schema.

The voice module consumes a small context snapshot containing those identities,
the accepted script or an explicit unavailable value, and source-labelled scene
observations. It requests conversational help from a supplied backend boundary.
It does not generate a competing authoritative script, mark a plan accepted,
advance production phases, or save an actor's chosen line independently of the
Director. Line changes return proposals for the existing owner to validate.

For local rehearsal, fixtures provide the missing script/scene integrations.
When Caesar's package 02 interface arrives, connect it at this boundary instead
of retaining duplicate script logic. A missing live backend is reported as
unavailable even if the voice transport connected successfully.

The recording boundary consumes source-labelled lifecycle events with runtime,
session/take identity, increasing event sequence, and recording state. Fixture
events exercise the same gate through explicit offline mode. They cannot
acknowledge a real recording or modify a production session's phase.

The capture integration must deliver recording-request notification before it
asks a device to start, and provide confirmed stop or unknown/fault status.
Until that connection is implemented and verified, report the real recorder
audio gate as unintegrated. Polling a UI phase alone cannot establish immediate
silence at recording start. Agree this handoff with the recorder owner before
claiming capture-safe integration.

## State, cancellation and silence

Keep connection state, conversation request state and the recorder audio gate
separate. A connected provider does not mean playback is permitted.

The audio gate starts closed until it has fresh, trusted context showing that
ordinary conversation is permitted. Recording request, starting, recording,
finalizing, unknown recording state, lost lifecycle connection, and application
restart close the gate. Only a current, correctly scoped confirmation that
recording has stopped can release the recorder latch. Opening a new tab or
changing a selected session cannot override uncertainty about an active take.

Closing the gate performs local playback suppression first, suspends microphone
transmission, invalidates pending speech, and requests cancellation of
provider/backend work. Do not depend on a
prompt telling the model to be quiet or on a cloud round trip. A late provider
response remains inaudible even when the provider did not acknowledge cancel.
Do not replay buffered speech when the gate reopens.

Interruption, session/plan/take revision changes, disconnect and cancellation
invalidate the active conversational request. Propagate cancellation to the
backend and reject late results at the return boundary. Do not claim an external
job stopped merely because its result was discarded locally.

Allow one active conversational request; do not accumulate a queue of obsolete
questions, cues or audio. Retain at most 32 completed conversation turns and
32 KiB of transcript context per voice session, evicting the oldest complete
turns first. Reject oversized inbound messages rather than allocating an
unbounded transcript. Keep the existing 16 KiB application request limit unless
a specific provider handshake requires a separately bounded route.
Use explicit local clock domains for deadlines and separate provider media
offsets from local monotonic times. Do not compare timestamps across devices
without their clock mapping.

## Scope of coaching and review

This slice can speak verified line suggestions and discuss supplied review
results. It does not implement visual beat evaluation, pose tracking, corrective
robot motion, real take analysis, recording, editing or generated effects.
Missing/uncertain observations remain unknown. It must not invent that it can
see the actor, that a recording succeeded, or that a physical change occurred.

Keep routine speech silent during capture, while leaving the independent
operator control/stop path untouched. Speech silence is not an emergency-stop
implementation. Recorded dialogue is content, not control authority.

## UI and privacy

Reuse the app's visual language and add only the voice controls, readable
transcript, context/source label, connection status, quiet-gate reason and clear
error/retry/disconnect actions. Provide keyboard-accessible controls and live
status announcements without repeatedly reading every transcript fragment.

Show an AI-voice disclosure and explain the selected provider before microphone
connection. Do not acquire or transmit microphone audio in offline mode. Stop
media tracks and close the live session on explicit disconnect and page exit;
do not reconnect automatically after an uncertain failure. Require a finite
positive maximum connected-session duration in live configuration and make
expired sessions explicit. If the limit or live permission is missing, do not
open a paid session. No live duration or spend limit is selected by this design.

Do not log or commit credentials, audio, full private transcripts or provider
authorization payloads. Keep short conversation context in memory for the
active voice session; persistent production changes belong to the Director.
Retain only non-sensitive test evidence locally unless sharing is authorized.

## Verification and acceptance

Use failing tests before implementation. Exercise real voice/gate state logic
and HTTP/browser boundaries, replacing only external provider, media and device
edges. Use deterministic clocks for deadline cases; distinguish those results
from measured device latency.

Required cases:

1. An explicit fixture conversation completes through the served voice page and
   remains labelled offline; live mode without configuration returns unavailable.
2. A recording request suppresses current and queued speech before any provider
   response; starting, uncertain state and finalization remain quiet.
3. A late completion after interruption, revised script, changed take, recording
   request, disconnect or runtime replacement cannot speak or change state.
4. A wrong-session, old-sequence or wrong-take stop acknowledgement cannot
   reopen playback. A current stop confirmation permits only fresh speech.
5. Provider failure, microphone denial, media disconnect and backend timeout
   produce explicit recoverable errors without fabricated success or automatic
   paid retries. Disconnect releases the owned local media resources.
6. Spoken/scripted "cut" and "stop" do not invoke recorder or motor operations.
7. Delayed backend work is bounded, cancelled when possible and discarded when
   stale; it never blocks the existing device timing path.
8. Browser workflow, accessibility, responsive layout and existing simulator/
   Director routes are checked. Existing product and simulation tests remain
   part of verification, not replaced with voice-only checks.

Run the repository verification entry point and report every check separately.
The inspected clean clone has a known preservation-audit failure: its runner
requires ignored workstation-specific `archive/recovery` and `lerobot` evidence.
Do not invent those files or report a skipped audit as preservation success.
Resolve the portable-check/workstation-audit distinction explicitly before
claiming a clean all-checks result.

Fresh isolated-worktree baseline on September 12: 76 product Python tests,
26 simulation Python tests and 12 web/GLB tests passed; syntax, Ruff lint and
format checks passed. The preservation audit failed on the missing ignored
manifest, so the overall verification command exited 1. These are baseline
results before voice implementation, not voice acceptance evidence.

For an authorized live test, record selected provider/model, connection outcome,
interruption behavior and measured conversational latency without publishing
private content. A fixture audio gate does not prove silence at a real camera;
that requires the capture integration and an on-site test.

## Delivery and limits

Leave the implementation and evidence record under
`docs/ai-director/implementation/05-rehearsal-voice.md`, clearly distinguishing
this partial package from the full visual rehearsal coach. Keep package 05
incomplete until its full dependency and acceptance requirements are met.

No live provider spending, media upload, microphone test, robot actuation,
deployment, push or merge is authorized merely by this specification. Continue
independent offline implementation when a provider or team interface is missing.
Confirm the live test's configured credentials, permissioned sample and budget
separately; do not search unrelated credential stores.

## Provider references checked September 12

- [GPT-Live 1](https://developers.openai.com/api/docs/models/gpt-live-1):
  selected voice model; account access remains unverified.
- [Client delegation](https://developers.openai.com/api/docs/guides/live-delegation):
  the application owns context, task state and permissions; spoken interruption
  does not automatically cancel backend work or guarantee playback silence.

Use current official API event and transport contracts during implementation.
Do not treat GPT-Live as an alias for the distinct Realtime API.
