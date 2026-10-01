# Offline Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete one offline recording workflow with voice suppression, validated synthetic media, explicit zoom timing and reproducible failure tests.

**Architecture:** A take-specific service and SQLite store own the simulated recording lifecycle. An authenticated loopback bridge connects its fixture events to the existing voice gate; one thin page exposes the complete flow without changing Director production state.

**Tech Stack:** Existing Python 3.13 environment, Python standard library/SQLite, local FFmpeg and ffprobe, existing vanilla JavaScript/CSS and Node tests.

**Spec:** docs/superpowers/specs/2026-09-13-offline-recording-design.md

## Execution status and September 13 update

The original checklists below describe the task breakdown. Current completion:

- [x] Task 1 domain and synthetic media, including scoped review and fixes.
- [x] Task 2 authenticated HTTP and voice gate integration, reviewed and tested.
- [x] Task 3 page, documentation and three browser-driven fixes through ef628ac.
- [x] Desktop/mobile playback, seven scenarios, restore and quiet-state checks.
- [x] Research and handoff: current device context, primary sources and adapter
  acceptance are in the [recording handoff](../../ai-director/implementation/06-recording.md#september-13-camera-update-and-windows-research).
- [x] Full local verification after the three browser fixes: all seven checks.
- [x] Include final review's strict-decode correction and portable test-tool lookup;
  the [recording handoff](../../ai-director/implementation/06-recording.md#local-routes-and-storage) owns the invariant and regression references.
- [ ] Fresh final-head verification after the consolidated review corrections.
- [ ] AXI validation, publication and PR checks. Do not auto-merge.

The [verification record](../../ai-director/implementation/06-recording.md#verification-and-remaining-acceptance)
owns recorded validation and publication results; earlier green runs do not
verify the final corrections.

No camera app is selected by the research. Real device evidence and an agreed
control endpoint are prerequisites for a subsequent adapter task. This plan
does not authorize device installation, purchases or physical experiments.

## Global Constraints

- No microphone, provider, camera or motor is opened.
- Product implementation belongs under packages/takeone/recording.
- Gate observations are source=fixture, never recorder; recorder_ready stays false and live remains unavailable.
- No Director production revision, accepted script, plan or real take is changed.
- One unresolved take and one bounded media finalization at a time.
- Mark real_media_verified=false even when the synthetic artifact is valid.
- Simulator zoom limits are 1x to 4x and 250 to 10000 ms; these are not iPhone capabilities.
- No em dash, agent coauthors, CHANGELOG edits, original/calibration changes, new app/provider choice or hardware timing changes.
- Use apply_patch for authored files. Never manually edit auto-generated files.
- Keep private data, media outputs and verification evidence outside Git. Use /tmp/takeone-recording-xEzY8j for this turn's evidence.

## Task 1: Recorder domain, persistence and synthetic media

**Files:** Create populated `packages/takeone/recording/{__init__,contracts,repository,simulated,media,service}.py`; test `tests/test_recording.py` and `tests/test_recording_media.py`.

**Interfaces:** Produce `ZoomRamp(start_factor, end_factor, duration_ms)` with `factor_at(elapsed_ms)` and `wire()` including a signed derived rate. Produce `RecordingService(database: Path, media_root: Path, *, clock=time.monotonic_ns, notify=None, simulator=None, media_writer=None)` with `start(request_id, context, zoom, scenario='normal')`, `get(take_id)`, `list_takes()`, `stop(take_id, request_id)`, `recover(take_id, request_id)`, and `close()`. Returns JSON-safe snapshots with take_id/state/source/context/zoom/events/media/error. Constructor dependencies include a concrete simulator and media writer for injecting device/storage faults. An optional synchronous `notify(take, state)` hook allows Task 2 to close the voice gate before simulator work; no imports from voice or app. Expose a bounded public status/error type and exact media lookup for validated take IDs. Document any necessary interface refinement in the report.

- [ ] Write tests first for a real service with a temporary database and injected clock. The first tests should fail because the recorder functionality is absent, not due to unrelated setup.

```python
ramp = ZoomRamp(1.0, 3.0, 2000)
assert ramp.factor_at(1000) == 2.0
assert ramp.factor_at(3000) == 3.0
assert ZoomRamp(3.0, 1.0, 2000).wire()['rate_factor_per_s'] == -1.0
```

Cover zero/negative/bool/NaN/infinity/out-of-range factors and durations; no silent normalization. Use actual service calls to prove duplicate start returns the same take and conflicting parameters fail without a second row.

- [ ] Run `.venv/bin/python -m unittest tests.test_recording -v` and retain RED output.
- [ ] Implement the small contracts, SQLite transactions/events and simulated acknowledgements. Keep original context and IDs immutable. Use explicit scenarios normal, delayed_start, start_timeout, disconnect, stop_timeout, save_failure and corrupt_media. Delayed start remains starting until its deadline, and late acks do not revive stopped/retired takes. Record request and ack timestamps separately as decimal ns with an epoch. Restart cannot reuse old monotonic deadlines or restart work.
- [ ] Test and implement bounded synthetic media generation with subprocess argv lists (no shell), process timeouts and a single bounded finalization worker. FFmpeg generates testsrc2 video plus sine audio, then ffprobe and full decode inspect the partial file. Use a unique directory and refuse overwrites. Validate duration against the requested synthetic timeline, streams, size and checksum before publishing. Store artifact provenance and probed data; generation duration is not the host start-to-stop interval.

```python
take = service.start('start-1', {'source': 'standalone_fixture'}, ZoomRamp(1, 2, 500))
assert take['source'] == 'simulated'
# Advance the injected clock and poll using get until simulated acknowledgement.
# Stop then wait boundedly for the real FFmpeg worker; inspect persisted result.
assert result['state'] == 'ready'
assert result['real_media_verified'] is False
assert result['media']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
```

- [ ] Add real media tests: decode generated MP4, correct streams/duration, original hash unchanged after another take, corruption rejected, failed writer leaves no ready media, missing executable yields explicit unavailable/error. No raw media committed. Use test doubles only at subprocess/device failure edges, never replace the lifecycle/store under test.
- [ ] Test all listed fault scenarios, stop before delayed start, duplicate stop, conflicting operation IDs, start blocked while unresolved, explicit recovery, restart during starting/recording/finalizing, and ignored obsolete finalizer result.
- [ ] Run focused tests, root verifier to a fresh `task1` evidence directory, lint/format and diff check. Commit only Task 1 files and report TDD commands/results, contracts and limitations.

## Task 2: Voice-owned recording HTTP integration

**Files:** Create `packages/takeone/recording/api.py` and `voice_bridge.py`; modify `packages/takeone/voice/service.py`, `packages/takeone/voice/api.py`, and `apps/rehearsal/server.py` only as required for narrow public integration hooks; add a scoped default recording-output ignore to `.gitignore`; create `tests/test_recording_api.py`.

**Interfaces:** Consume Task 1 service/snapshots. Provide local routes under `/api/recording/`: runtime, takes list, start, stop, recover and take status/media. Mutations reuse `X-TakeOne-Voice-Token` and the existing voice envelope plus explicit request_id/take_id/zoom/scenario fields. GET status/media require the token. Runtime may expose public unavailable/simulator limits only. Return voice snapshots alongside take results so the page can reconcile generations. Media downloads use authenticated fetch, not tokens in URLs. Construct the recorder in a `recording/` directory under the passed director_database parent, with a distinct SQLite file and media directory, so test databases isolate outputs. Add `/data/director/recording/` to `.gitignore` for the ordinary launcher; external test paths stay outside Git. Preserve make_server positional callers and close owned recorder workers on shutdown.

- [ ] Read actual VoiceService ownership/refresh/fixture observation behavior before adding a hook. Write real loopback tests that create offline voice through the current HTTP endpoint, then start a take using its exact scoped envelope.

```python
# Existing HTTP test helpers create a real ThreadingHTTPServer and temporary DB.
assert before['snapshot']['quiet'] is False
assert started['snapshot']['quiet'] is True
assert runtime['recorder']['ready'] is False
assert started['take']['source'] == 'simulated'
```

- [ ] Run `.venv/bin/python -m unittest tests.test_recording_api -v` and retain expected RED output.
- [ ] Implement public owner validation and fixture-only notifications. Capture the originating identity and context, then close its gate before simulator activity. Do not call observe_recorder or declare recorder readiness. Ensure the old fixture idle/stopped endpoint cannot reopen the gate while a take is active. Release it only after confirmed stop/recovery; save failures remain failed while confirmed stopped voice may reopen. Avoid holding VoiceService locks over FFmpeg, SQLite polling or worker joins.
- [ ] Parse strict JSON schema, bounds and envelope; reject unknown fields, live mode, stale/wrong owner, scope/generation/expiry, unsafe Host/Origin and arbitrary file paths before side effects. Preserve idempotency through HTTP retry despite generation change caused by the original operation, while still authenticating the current owner. A token alone cannot mutate another owner's take. Return bounded, useful errors and refreshed metadata where ownership allows it.
- [ ] Implement status/list and media retrieval by stored UUID. Only validated synthetic files can be retrieved, with no-store/nosniff and bounded bytes. Check immutable content identity before serving and keep files outside static routes. Reopened explicit test sessions can list completed synthetic takes; old unfinished work needs explicit simulator recovery and never grants physical readiness.
- [ ] Tests cover pending offline question cancelled on recording request, no late reply after stop, quiet throughout delay/unknown/finalization, successful fresh question after confirmed recovery, stale callbacks against new owners, rejected manual stopped/idle while recording, no tokens in persisted artifacts, path traversal/wrong Host/Origin/token, failed/corrupt media refusal and restart behavior. Verify original Director revision/context unchanged.
- [ ] Run focused recording/voice/HTTP suites, root verifier to a fresh `task2` directory, lint/format and diff check. Commit only task files and report exact API examples for Task 3.

## Task 3: Minimal recording page and team documentation

**Files:** Create authored `apps/rehearsal/dist/recording.html`, `recording.js`, `recording-client.js`, `recording.css`; modify the voice navigation link only in `voice.html`; update web syntax command in `apps/rehearsal/package.json` without adding a dependency; create `apps/rehearsal/tests/recording.test.mjs`. Update README, `docs/ai-director/implementation/06-recording.md`, package 06 in `work-packages.json` and stale merge status in implementation/05-rehearsal-voice.md.

**Interfaces:** Consume the Task 2 authenticated recorder routes and existing voice session/question/snapshot APIs. Use only offline mode. Reuse voiceEnvelope where suitable; never make an additional live provider/media path. The page retains only its own offline owner and pending request recovery identity in per-tab sessionStorage until confirmed End. No transcripts are persisted. Suppress pending outputs on recording request and discard late results with a lifecycle identity. On reload offer explicit Restore, check existing ownership first and never auto-replay a mutation. After confirmed End or a definitively replaced runtime discard the stale identity. Storage failure is visible. New sessions can show persistent synthetic history after explicit session creation, not silently reconnect voice.

- [ ] Write Node tests for actual client/controller behavior with injected HTTP boundaries: explicit start, record closes questions immediately, acknowledgement updates state, stop/finalizing cannot create premature playback, error/retry uses same request ID, recovery, reload offers explicit restore without a mutation, stale restored owner rejected, storage failure, late response ignored after end/replacement, polling stops, no unsolicited connection or microphone use. Use complete representative JSON snapshots, not tests for literal source text.
- [ ] Run `node --test apps/rehearsal/tests/recording.test.mjs` and retain RED evidence.
- [ ] Implement the page using the existing restrained charcoal style and native controls. Purpose: Basil/on-site team testing recorder integration; tone: minimal utility; constraints: existing stack, no dependencies, accessible desktop/mobile; differentiation: truthful take timeline and clearly labelled synthetic playback. The approved voice page receives only a small navigation link. Use visible 'Offline recording test', current state, source and errors; one primary start/stop action; zoom start/end/duration and scenario under native details. Include an offline text question to prove gate behavior, saved-take list and video controls only for validated media. No autoplay, decorative dashboard/cards, fake waveform or camera permission prompt.
- [ ] Ensure asynchronous responses cannot reopen ended sessions, stale status cannot replace newer take state, every displayed error allows the relevant safe recovery, and blob URLs/listeners/timers are cleaned up. Ambiguous network delivery reconciles by existing request ID, never creates a fresh duplicate take.
- [ ] Update package 06 as in_progress/offline slice verified, not complete. Document actual setup, routes, data directory, requested-vs-acknowledged state, zoom units/simulator-only limits, synthetic media lineage, failure scenarios and missing real-device work. Record original context snapshot semantics and that this does not implement DollyZoom. Correct package 05's old merge hold using PR #1/e727e426 evidence, keeping historical failed-run notes.
- [ ] Run Node tests/syntax and the complete root verifier to fresh `task3` evidence. Commit task files and report. Root then performs actual served-browser desktop/mobile verification, final whole-branch review, full final-head verification and AXI validation/publication to a new PR. No merge into main is implied by finishing this new slice.
