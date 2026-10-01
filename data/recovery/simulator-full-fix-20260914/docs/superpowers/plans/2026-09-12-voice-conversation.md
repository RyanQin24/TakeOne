# Voice Conversation Implementation Plan

**Historical plan:** Current behavior and verification evidence are recorded in the [package 05 implementation record](../../ai-director/implementation/05-rehearsal-voice.md). The subsequent [UI simplification and handoff plan](2026-09-12-voice-ui-and-handoff.md) records its own approval; consult the implementation record for the delivered UI and remaining acceptance. Preserve this document as implementation history.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Execution and the written specification are approved; do not request repeated design approval.

**Goal:** Add TakeOne's remote voice/conversation slice with an offline rehearsal, explicit live-provider boundary, cancellation and a recording quiet gate.

**Architecture:** A focused Python voice module serves the existing local application. Browser media and playback remain separate from the Director's authoritative state. External providers and recording events are injectable boundaries, never alternate planners or motor tools.

**Tech Stack:** Python 3.12+, existing Python 3.13 development environment, standard-library HTTP/concurrency, vanilla browser JavaScript and Node tests; GPT-Live 1 WebRTC over documented REST calls.

**Spec:** `docs/superpowers/specs/2026-09-12-voice-conversation-design.md`

**Integration refresh:** During implementation the team published `9b3a88c`, adding creative planning and replacing the Director UI. The unpublished voice branch was rebased onto that version with its existing feature patches unchanged. Use the current read-only creative-script context and current app styling. Do not invoke the creative planner's paid, state-mutating line requests from voice. The approved voice ownership and hardware boundaries are unchanged.

**Second integration refresh:** The team subsequently published `6036010`, including the recovery manifest and LeRobot source plus a source-clone audit repair. Integrate that baseline before Task 4. Its `data/verification` outputs are now saved versioned evidence. Preserve the existing audit in the normal checks; the earlier mandatory audit split below is superseded. Give the existing verification commands a small optional output-directory argument so fresh local results can be kept outside that evidence tree. This does not require downloading LFS payloads or altering hardware/source originals.

## Global Constraints

- Product code lives in `packages/takeone`; preserve Caesar's packages 01-03 and all robot/control/calibration code.
- Voice uses GPT-Live 1 with client delegation; no second planner or silent provider substitution.
- No live calls, microphone acquisition, media uploads, motor access, pushes or merges during automated work.
- Imports and page load perform no provider call, microphone acquisition, camera discovery, serial-port access, or device connection.
- Recording uncertainty fails closed. Local playback suppression precedes cloud cancellation; stale results cannot reopen playback.
- Transcript content never grants authority to recording, scripts or robot actions.
- Use existing runtime epoch, session/revision/cancellation/plan/take identity; name clock domains and reject stale scopes.
- Retain at most 32 completed conversation groups and 32 KiB transcript context; reject oversized individual events.
- Keep normal JSON requests within 16 KiB; permit a separately limited 64 KiB SDP handshake only.
- Fixture mode must be explicit and visibly labelled. Missing live configuration or backend is unavailable, not fake success.
- Use `apply_patch` for authored files. Never author an em dash, add agent co-authors, or edit auto-generated files.
- Keep package 05 incomplete: visual coaching, real camera/recorder integration and real take review are not this slice.

## Task 1: Scoped voice state and recording gate

**Files:** Create `packages/takeone/voice/{__init__,contracts,state}.py` and `tests/test_voice_state.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class VoiceScope:
    runtime_epoch: str
    session_id: str
    revision: int
    cancellation_generation: int
    plan_id: str | None
    take_id: str | None

@dataclass(frozen=True)
class RecordingEvent:
    scope: VoiceScope
    sequence: int
    state: str  # idle, requested, starting, recording, finalizing, stopped, unknown
    source: str  # fixture or recorder
    observed_monotonic_ns: int
    expires_monotonic_ns: int

class VoiceState:
    def __init__(self, scope: VoiceScope, *, mode: str, clock= time.monotonic_ns): ...
    def observe_recording(self, event: RecordingEvent) -> dict: ...
    def set_scope(self, scope: VoiceScope) -> dict: ...
    def interrupt(self, reason: str) -> dict: ...
    def begin(self, request_id: str) -> int: ...  # returns cancellation generation
    def complete(self, request_id: str, generation: int, text: str, *, source: str) -> bool: ...
    def append_transcript(self, speaker: str, delta: str, start_ms: int, end_ms: int) -> None: ...
    def snapshot(self) -> dict: ...
```

The snapshot exposes `scope`, `mode`, `generation`, `quiet`, `quiet_reason`, `pending_request_id`, `transcript` and `transcript_bytes`. Use immutable typed identities and explicit wire serialization. Runtime/session/take IDs use canonical UUIDs; nullable plan ID preserves the existing SHA-256 plan format. No provider or transport imports in this task.

- [ ] Write literal, behavior-driven tests first. Initial state is quiet; a fresh matching idle observation permits conversation, then `requested` closes the gate and invalidates an outstanding response. Assert `complete(...)` returns false for the old request and cannot append a reply.

```python
state.observe_recording(event(scope, 0, "idle"))
generation = state.begin("request-one")
state.observe_recording(event(scope, 1, "requested"))
self.assertTrue(state.snapshot()["quiet"])
self.assertFalse(state.complete("request-one", generation, "Old reply", source="fixture"))
```

- [ ] Run `.venv/bin/python -m unittest discover -s tests -p test_voice_state.py -v` and capture the expected missing-feature failure.
- [ ] Implement gate and cancellation logic. Initial idle can release startup uncertainty only before a recording latch. Once latched, only matching current stopped evidence can release it. Idle, stale sequence, future/expired evidence, changed session selection and unrelated take stop cannot clear a latch. `set_scope` preserves uncertainty and invalidates pending work; do not rewrite the identity of an outstanding recording latch to the new selection.
- [ ] Test deadline expiry at `snapshot`, `begin` and `complete`; a healthy UI must not keep replaying expired observation authority. Fixture observations never open live state. Interrupt invalidates one pending request, without pretending a provider actually cancelled.
- [ ] Implement bounded exact transcript fragments with speaker and provider-relative intervals. Fragments are not semantic commands. Keep display grouping revisable; bounds apply even to one long uninterrupted speaker. Reject invalid types, non-finite/negative intervals and overlarge fragments; preserve received whitespace.
- [ ] Test cancellation races logically with a deterministic clock, wrong request/generation, repeated request identity, scope revision, Unicode byte limits and scripted cut/stop text. Run focused tests, relevant existing Director tests and Ruff. Commit only this task and write its report with red/green evidence.

## Task 2: Local API, fixture backend and explicit Live transport

**Files:** Create `packages/takeone/voice/{service,provider,api}.py`, `tests/test_voice_api.py`, `tests/test_voice_provider.py`. Modify only voice routing/lifecycle seams in `apps/rehearsal/server.py` and `packages/takeone/cli.py` if needed.

**Consumes:** Task 1 `VoiceScope`, `RecordingEvent`, `VoiceState`.

**Produces:** `VoiceAPI.get(path)` / `VoiceAPI.post(path, body)` for `/api/voice/` routes; a `VoiceService` injected with Director read access, backend and provider. Existing `make_server` callers remain valid via optional keyword injection.

HTTP shapes are versioned JSON. Establish and document route payloads in the implementation record before Task 3 consumes them. Routes: runtime/configuration availability; create offline or live voice session; read snapshot; ask fixture/backend question; interrupt; disconnect; fixture recording event; create Live SDP session. All mutations carry voice-session ownership token plus current scope/generation, except create which binds to a current Director snapshot or the explicit fixture context. Fixture controls never mutate Director state. One active voice owner per application prevents competing tabs from bypassing recording uncertainty.

- [ ] Write HTTP tests against the actual loopback server. Prove explicit offline create -> ask -> response -> recording requested -> delayed response rejected -> correct stop -> fresh question, without modifying the Director database. Use a blocking test backend to expose cancellation during work.

```python
created = client.post("/api/voice/sessions", {"schema_version": 1, "mode": "offline"})
response = client.post("/api/voice/questions", question_payload(created, "Help with my line"))
self.assertEqual(response["source"], "fixture")
self.assertFalse(client.get("/api/health")["hardwareConnected"])
```

- [ ] Run the new tests red. Implement bounded synchronous request handling without holding a shared state lock across provider/backend I/O. Cancellation sets the backend cancellation event and invalidates acceptance. Permit one outstanding operation, enforce timeout/expiry, and prevent unbounded task/thread/session accumulation. No paid retries.
- [ ] Preserve Host/Origin/JSON checks. Reject malformed fields, stale runtime, wrong token/scope, oversized input and fixture events against live mode. Generate a private random voice ownership token; no capability to execute arbitrary URLs, shell, capture or motor functions.
- [ ] The offline backend returns a small labelled fixture script/line suggestion. The live backend boundary returns explicit unavailable until Caesar's script provider is injected. Live transport availability and Director-backend availability are separate facts. Do not run an extra reasoning model to fill that gap.
- [ ] Implement a standard-library HTTPS provider adapter from the official GPT-Live contract: `POST https://api.openai.com/v1/live/sessions` with server-owned `session` configuration, `model: gpt-live-1`, `delegation.type: client`, `store: false` and `transport: {type: webrtc, sdp}`. Strictly validate bounded returned opaque `session.id` and `transport.sdp`. Use a fixed host, timeouts, no redirects carrying credentials, no automatic retry and sanitized errors. No permanent key reaches the browser or logs.
- [ ] Live access requires explicit server configuration: enabled flag, project key and finite positive maximum session duration. Default disabled. No secret-store search. Enforce duration on the server independently of the browser. Clean up late successful session creation after local cancellation and expired/disconnected sessions through the documented hangup endpoint. Make failed/unconfirmed cleanup visible and prevent a second paid session while first ownership is uncertain.
- [ ] Verify exact Live endpoint/configuration/close fields in official documentation before coding them. Mock only outbound HTTPS in provider tests: assert payload, timeout, rejected malformed success, timeout, refusal, no retries and cleanup after a late result. Do not call OpenAI during tests.
- [ ] Recording/interrupt/context changes close the Live transport rather than unmute unidentified buffered speech. Tell the browser to suppress local playback and mic first, then close; reopening requires explicit fresh connection. Keep this conservative lifecycle visible to the user. Provider/client events cannot declare a real recorder stopped.
- [ ] Run focused API/provider tests plus existing HTTP/Director tests and Ruff. Commit and report exact wire shapes for Task 3, fixture/live distinctions and remaining integration limitations.

## Task 3: Voice page, browser controller and media cancellation

**Files:** Create `apps/rehearsal/dist/voice.html`, `voice.css`, `voice.js`, `voice-controller.js`, `voice-media.js`; create `apps/rehearsal/tests/voice.test.mjs` and `voice-media.test.mjs`. Modify `apps/rehearsal/package.json` syntax check and minimal navigation links only.

**Consumes:** Task 2 documented `/api/voice` JSON shapes; current Director read-only sessions. Python authority remains unchanged.

**Produces:** A working voice page served by the existing app, pure testable browser controller and injected media/network edges.

- [ ] Write Node tests for production controller behavior before implementation. Fakes replace only network, media tracks, audio sink, peer connection and clocks. Muting playback and disabling/stopping mic must occur synchronously before awaiting cancellation HTTP. Late track events, SDP responses and provider messages after generation changes must never play or reconnect.

```javascript
controller.recordingRequested();
assert.equal(audio.muted, true);
assert.equal(microphoneTrack.enabled, false);
resolveOldReply({text: "stale"});
await flushTasks();
assert.equal(controller.snapshot().speaking, false);
```

- [ ] Run `node --test tests/voice.test.mjs tests/voice-media.test.mjs` red in the rehearsal app. Implement an explicit fixture mode with no media permission request and a separate live mode requiring the disclosure/connection action. Fixture speech is visible text plus an explicitly synthetic local test tone if needed to verify playback suppression; never claim fixture text is provider audio.
- [ ] Implement WebRTC microphone/audio and `oai-events` setup using documented Live events. Wait for `session.started`; show input/output transcripts exactly as deltas, source-labelled. No `session.start` on an already-created WebRTC session; no Realtime event names. Keep transcript changes separate from action authority.
- [ ] Handle microphone refusal, unsupported media, autoplay rejection, SDP failure, lost data channel, expired backend and unknown recording state visibly. Local stop/mute is unconditional even if HTTP fails. Keep a bounded graceful-close timer and distinguish confirmed `session.closed` from unconfirmed cleanup. Page exit stops tracks and best-effort closes owned session. No automatic reconnect or queued speech replay.
- [ ] Manual interrupt ends the current provider connection to guarantee no stale audio; display explicit reconnect guidance and preserve bounded local transcript. Natural conversational interruption may be provider-supported, but do not claim that it cancels application backend work unless verified and signalled by the application.
- [ ] Match the current app's charcoal, warm-paper and muted-green palette with a focused rehearsal workspace: connection controls, transcript, quiet reason and fixture event panel. Reuse its existing font stack and tokens where practical. No framework migration, stock gradients or dashboard decoration. Mobile and keyboard flows must work.
- [ ] Run Node tests/syntax and existing app tests. Controller integration must expose no raw motor/recorder actions. Commit and report UI routes, test results and live test limitations.

## Task 4: Portable verification, full workflow checks and handoff

**Files:** Modify `scripts/verify.py`, `scripts/check_integrity.py`, `tests/test_verification.py`, root README and `docs/ai-director/README.md`; create `docs/ai-director/implementation/05-rehearsal-voice.md`. Update package 05 manifest only if its existing status format can truthfully represent partial work; never mark it complete.

**Consumes:** All implemented voice behavior and unchanged root baseline.

- [ ] Preserve the recorded pre-publication missing-manifest failure as historical evidence. On the integrated `6036010` baseline, first reproduce the lack of an output-directory option with an isolated subprocess test; the existing default would overwrite saved `data/verification` reports.
- [ ] Add a small optional `--output-dir` to `scripts/verify.py` and `scripts/check_integrity.py`. Pass the resolved output directory through to the audit. Preserve the existing default destination and all seven checks, including real preservation failures. Test custom paths from another working directory, unchanged default-path behavior in an isolated fixture, failure propagation and audit report placement. Do not add a verifier framework, skip the audit by default, fabricate manifests or commit fresh/private evidence.
- [ ] Run the full verifier with a fresh external temporary output directory and a direct fake-device dry-run. Record each check separately, including actual preservation results and unhydrated LFS limits. Keep new run artifacts separate from saved team evidence. Verify no imports opened ports. Root uses the existing browser connection and temporary Director database to exercise offline conversation, interruption, recording latch, wrong/late reply handling, reconnect messaging, keyboard flow and mobile layout. Never request the real microphone or enable paid sessions during automated checks.
- [ ] Inspect the whole diff and confirm no changes to robot/calibration or Caesar's Director implementation. Document exact boundaries for future context/backend/recording integrations and setup on macOS/Windows, including disabled-by-default live config. Report the unverified live path honestly.
- [ ] Write implementation evidence and update discovery docs without claiming full package 05 completion. Commit. Final independent review covers the whole branch; fixes get covering tests and scoped re-review. Leave branch local for the user to review; do not push or merge automatically.
