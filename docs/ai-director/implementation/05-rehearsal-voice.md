# Package 05 partial implementation: rehearsal voice

Date: 2026-09-12. Status: **in progress - offline voice slice verified locally**.

**Publication, September 13:** [PR #1](https://github.com/Zwc-11/TakeOne/pull/1) merged at `2026-09-13T02:43:04Z`, commit `e727e42654166c8b114ba7624790cec2518a6abc`, after the complete final-code verifier passed. The prior merge hold is cleared. Evidence: `/tmp/takeone-published-verification-BjLaZg/verification/summary.json` and the [final public verification note](https://github.com/Zwc-11/TakeOne/pull/1#issuecomment-5650335977). The failed runs and earlier merge-hold statements below remain historical evidence for their individual checkpoints. The [coordination correction](#readiness-and-deterministic-coordination-review-follow-up-september-12) and [subsequent focused verification](#focused-test-and-recovery-notice-follow-up-september-12) describe the intervening fixes. Integration does not complete package 05 or establish live-device acceptance.

This record covers a narrow contribution to package 05. It does not complete the visual rehearsal coach, camera or recorder integration, real take review, or live GPT-Live acceptance. No microphone, provider, camera, hardware or physical recording action was used for this evidence.

**Current UI:** Basil approved a second, closer-to-reference pass: neutral charcoal, a borderless gray status area, centered content, a white pill start button, and a small **Back to Director** link instead of the sidebar. Mode and production selection now live under **Session settings**. Current mode, live disclosure, recording silence and recovery remain visible outside the collapsed settings. The controller and backend are unchanged by this visual pass. See the reference-style follow-up evidence below for its verification and handoff status. Earlier review and test results remain historical evidence, not live voice acceptance.

The full run at `2026-09-13T00:34:11Z` reported 226 of 227 product tests and all 28 simulation tests passing. The failed test was `CoordinationTests.test_blocked_arm_does_not_block_cart_writer_or_resume_motion`, with a cart write-deadline fault. Syntax, preservation audit, Ruff lint and formatting passed. The web check initially lacked the existing `three` dependency; after `npm ci --no-audit --no-fund` in the gate checkout's `apps/rehearsal`, a complete `npm test` passed all 98 web tests. Full-run evidence is outside Git at `/tmp/takeone-axi-full-D2Ufhb/verification`. No robot limits or motion code were changed, and live microphone/provider/recorder behavior remains unverified.

## Delivered behavior

- `/voice.html` provides an offline-first, source-labelled text rehearsal in the existing local application.
- A creator can select read-only Director context, start the explicit offline fixture, request a line suggestion, interrupt pending work, simulate recording lifecycle events and disconnect.
- The gate is quiet by default. Requested, starting, recording, finalizing and unknown states suppress local playback and microphone transmission before asynchronous cleanup. Only a fresh, correctly scoped stopped event can release a recording latch.
- Late backend, provider, media and stale-snapshot results are generation and scope guarded. They cannot reopen playback or mutate production.
- A cancelled backend success is rejected against its exact original owner and pending request before refreshing or applying state. A response whose slot has already retired contains no transcript snapshot and cannot cancel a later question, including one under the same owner.
- Disconnect preserves the offline owner's Stop confirmed control while a recording latch remains. Stop reconciliation completes cleanup and permits a new explicit session; it never reopens the disconnected conversation.
- Transcript text has no recording, script or robot authority. Fixture events cannot claim a real recording.
- **Corrected 2026-09-17:** the selected live provider is Gemini Live, configured in `configs/voice-live.json` and minted through `voice/live_tokens.py`; the GPT-Live WebRTC path on `/voice.html` is a legacy diagnostic. Missing provider, backend or recorder configuration remains visibly unavailable, with no fallback planner or provider.

The browser groups conversation for display, while the authoritative Python state retains source-labelled transcript entries only in memory for the active voice session. It does not persist private transcripts.

## Local workflow

1. Start the simulator and open `http://127.0.0.1:8766/voice.html`.
2. Optionally open **Session settings** and select an existing Director production. This reads the current brief and accepted script without changing them. Settings can stay collapsed for a standalone offline test.
3. Leave **Mode** on **Offline test**, then select **Start offline rehearsal**. The question and expandable transcript appear, labelled **OFFLINE FIXTURE TEXT**. No microphone permission is requested.
4. Enter a question and select **Ask**. The small deterministic fixture returns a labelled text suggestion.
5. Open **Test controls and connection details**, enable **Delay fixture reply for interruption testing**, ask a question, then select **Interrupt**. The late fixture answer is discarded.
6. Within the test details, use Requested, Starting, Recording, Finalizing and Unknown to close the conversation gate. These controls do not operate a recorder.
7. Select **Stop confirmed** to supply a fresh fixture stop and permit only a new question.
8. The optional synthetic tone is generated locally after a user action. It is not provider audio and may be blocked by browser audio policy.
9. Select **End session**. If it reports unconfirmed cleanup after a Director revision changed, the controller accepts current scope metadata while staying quiet; select **End session** again to retry explicitly. If recording cleanup remains, **Stop confirmed** stays visible even with test details closed. Complete that simulated stop before starting a new session. Reconnection is always explicit.

If offline recording evidence expires, the page becomes quiet and disables questions. When fresh evidence permits conversation again, the notice reflects that recovery; only a fresh question can produce a reply. An unresolved recording latch still requires **Stop confirmed**.

Choosing **Live voice** in **Session settings** changes the visible mode label and start action and exposes the microphone disclosure. Closing settings does not hide that disclosure. Choosing a mode does not start a connection. The live start remains disabled until the existing provider, conversation backend, real-recorder readiness, selected-production and disclosure requirements are met. The shipped local setup does not meet those integration requirements. **Back to Director** returns to the existing production workspace.

## Setup and launch

Voice adds no provider SDK. The root simulation lock remains `requirements-simulation.lock.txt`, and LeRobot's separate environment is not required for offline voice.

On Windows from `C:\TakeOne`:

```powershell
.\scripts\Setup.ps1
.\.venv\Scripts\python.exe -m takeone.cli simulator --port 8766
.\.venv\Scripts\python.exe scripts\verify.py --output-dir C:\TakeOne-verification
```

`Setup.ps1` creates `.venv` with `uv venv --python 3.13`, installs `requirements-simulation.lock.txt` plus the editable `.[dev]` package, runs `npm ci --no-audit --no-fund` in `apps/rehearsal`, and regenerates the existing simulation model. It does not need a PowerShell execution-policy change for the direct Python verification command.

The equivalent initial macOS/Linux setup uses the platform Python path:

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-simulation.lock.txt -e '.[dev]'
(cd apps/rehearsal && npm ci --no-audit --no-fund)
.venv/bin/python -m takeone.simulation.model
.venv/bin/python -m takeone.cli simulator --port 8766
.venv/bin/python scripts/verify.py --output-dir /tmp/takeone-verification
```

Setup and model regeneration are not needed again solely for the voice documentation or verifier routing change when the pinned environment is already current. Relative `--output-dir` values resolve from the caller's working directory. Omitting the option preserves the existing `data/verification` destination.

## Disabled-by-default live configuration

The ordinary simulator command constructs GPT-Live with `enabled: false`, a 10-second HTTPS timeout and no paid-session duration. The default conversation backend is absent and `recorder_ready` is false, so live controls remain unavailable.

The existing provider transport flags are:

```text
--voice-live-enabled
--voice-live-timeout-seconds <positive integer, at most 60>
--voice-live-max-duration-seconds <positive integer, at most 86400>
```

`OPENAI_API_KEY` is read only by the server-side provider. The enable flag, key and a finite maximum duration are all required even for transport availability. These flags do not install a conversation backend or certify a recorder. Full live availability additionally requires the trusted Python integrations below, explicit disclosure in the browser and a selected Director production.

This live path was not executed. GPT-Live account access, WebRTC behavior, provider hangup effectiveness, conversation quality, measured latency and spend remain unverified.

## Integration handoffs

### Director context

`VoiceService` reads the existing Director owner and `SessionRepository.creative(connection, session)`. It reuses the Director runtime epoch, session, revision, cancellation generation, plan and take identities. Only a creative revision approved at the current Director revision is exposed as available. Existing provenance, including `curated_sample`, is retained.

This boundary is read-only. Voice must not automatically call `CreativePlanning.request_lines`, `CreativePlanning.submit`, approve a script, change a phase or save an actor choice. A future line change remains a proposal for the existing Director owner to validate.

### Conversation backend

Supply `VoiceService(..., conversation_backend=backend)` where `backend.answer(context, question, cancellation_event)` returns non-empty bounded text. The service runs one backend operation at a time on one worker, propagates the cancellation event and rejects late or stale results. Pass the configured service through the keyword-only `voice_service` argument of `apps.rehearsal.server.make_server(...)`; existing positional callers remain unchanged.

The backend is separate from provider media transport. It must consume only supplied read-only context, must not invoke the creative planner automatically and must not mutate Director state. The shipped server supplies no live conversation backend.

### Recorder and capture

The [offline recording handoff](06-recording.md) owns the simulated take bridge,
its recovery flow and fixture-gate integration. The device integration contract
below applies to a future real recorder.

The recorder owner must notify the voice integration before asking a device to start, then provide increasing lifecycle observations through `VoiceService.observe_recorder(event)`. The event must be a typed `RecordingEvent` with the full `VoiceScope`, sequence, state and `source="recorder"`. Supported states are idle, requested, starting, recording, finalizing, stopped and unknown.

Before constructing the event, the recorder integration must normalize both `observed_monotonic_ns` and `expires_monotonic_ns` into the exact monotonic clock domain used by the configured `VoiceService.clock`. `RecordingEvent`, `VoiceState` and `VoiceService` perform no cross-clock translation: freshness is compared directly against that clock, and the supplied expiry is stored directly. Never pass raw timestamps from a different producer clock. A cross-device mapping must conservatively bound its measured uncertainty so it cannot extend recording authority beyond established freshness. Reject or withhold the event whenever the mapping uncertainty cannot establish `observed_monotonic_ns <= VoiceService.clock() < expires_monotonic_ns`.

Constructing `VoiceService(..., recorder_ready=True)` is a separate, explicit integration declaration. Observing one recorder event does not set readiness. Browser and provider events cannot invoke the trusted recorder hook, and the fixture HTTP route can never claim recorder provenance.

Live creation starts without recorder authority. After that creation, the browser waits up to 5 seconds for fresh, accepted recorder evidence on the same voice identity, checking snapshots at 100 ms intervals with only one request outstanding. Interrupt, Disconnect and page exit cancel this wait, abort its HTTP request and discard any late observation. Readiness alone grants no media authority. Fresh recorder evidence permits muted microphone/SDP preparation; playback and microphone transmission still require active transport plus the provider's session-start event. Recorder lease expiry remains independent of transport readiness. Exported lease duration comes directly from evidence accepted by the recording gate, so future, expired, replayed or unrelated observations cannot extend it or consume the next valid sequence.

An uncertain GPT-Live creation or cleanup blocks another paid session. `VoiceService.reconcile_live_cleanup(provider_session_id=None)` is a trusted operator/integration hook only after external confirmation; it is not an HTTP route. `VoiceService.close()` cancels local work and attempts provider cleanup, and the rehearsal server calls it once during shutdown.

The capture owner still needs to implement and verify physical notification timing, exact-domain clock normalization, mapping uncertainty bounds, device stop behavior and failure recovery. Until those boundaries are integrated and verified, `recorder_ready` must remain false and raw device observations must not enter the trusted hook. Offline gate tests are not evidence that camera audio is silent.

### Future visual coaching and take review

No camera observation, pose tracking, actor beat evaluation, real recording, saved take, footage review, editing or generated effect is implemented here. Those consumers must provide source-labelled, scoped evidence and preserve the same fail-closed recording gate. They must not reinterpret transcript text as production authority.

## Enforced limits

- Normal voice JSON requests are limited to 16 KiB. The SDP handshake has a separate 64 KiB route limit; offer and answer SDP values are limited to 60 KiB.
- Questions are limited to 4 KiB UTF-8. Inbound transcript fragments are limited to 16 KiB. Delegated commentary returned to GPT-Live is conservatively limited to 500 UTF-8 bytes.
- The state retains at most 32 transcript entries and 32 KiB. It permits one active conversational request, at most 1,024 request identities and at most 256 observed scopes before requiring a fresh session.
- Cancelling a request at the maximum supported generation retires the session without incrementing past the bounded wire identity. Retirement stays quiet and still accepts a correctly scoped trusted stop to reconcile an existing latch. Fixture stop evidence cannot release a live latch.
- The default backend timeout is 6 seconds and accepts only finite positive values up to 60 seconds. A worker that ignores cancellation occupies the single slot until it exits; no unbounded queue or replacement worker is created.
- Fixture recording evidence expires after 5,000 ms and is renewed on a 2,000 ms cadence. Authenticated browser mutation deadlines use a fresh 15-second server-monotonic lease.
- Provider responses are limited to 128 KiB, provider session IDs to 512 UTF-8 bytes and the permanent key to 4,096 characters. Provider create and hangup do not automatically retry or follow redirects.

## Verification evidence

Task 4 first added an isolated subprocess test and observed the old runner ignore `--output-dir`: it exited successfully but wrote `summary.json` under the fixture repository's `data/verification` directory. The completed test suite covers caller-relative custom paths, unchanged default destinations, all seven checks, failed-check exit propagation, audit argument routing and preservation-report placement on both success and failure.

The final command was:

```bash
.venv/bin/python scripts/verify.py --output-dir /tmp/takeone-voice-task4.pTKTH6/verification-final
```

All seven checks passed:

1. Product tests: 217 passed.
2. Simulation tests: 28 passed.
3. Web tests: 47 passed.
4. JavaScript syntax checks: passed.
5. Preservation audit: passed, 1,086 LeRobot files checked, 6 generated metadata paths skipped by the existing policy, no nested Git history present and zero failures.
6. Ruff lint: passed.
7. Ruff formatting check: passed across 74 files.

The original pre-publication source clone remains historical evidence: its default verifier exited 1 because the private preservation manifest was missing while the other checks passed. Integration baseline `6036010366c23cfdfccb020d43275be9e5f2322f` publishes the manifest and ordinary LeRobot source. The current real audit was not skipped.

Git LFS was not installed and large LFS payloads were not hydrated or downloaded. A passing audit proves the current source bytes and authenticated pointer-byte preservation covered by the manifest. It does not prove the unavailable payload bytes or nested Git history.

A direct `.venv/bin/python -m takeone.cli dry-run` completed in `virtual-time-replay` with simulated feedback for both arms, `serial_ports_opened: false` and `physical_commands_sent: false`. Its new run directory was moved to `/tmp/takeone-voice-task4.pTKTH6/dry-run/20260912T204510Z-robot-c2eedaac`; no generated run or verifier evidence was staged.

## Actual browser evidence and final UI fixes

Root-owned browser checks exercised the served offline page without microphone or provider access. An approved Director editorial sample remained read-only with `curated_sample` provenance. Literal question text containing "cut" and "stop" produced a labelled fixture response and no production action. A delayed response stayed absent after interruption. Requested, starting, recording, finalizing and unknown states kept the input quiet; a current stop confirmation allowed only fresh work. Ordinary page navigation released ownership so a new offline session could start.

In the final Task 3 build, the browser had an open offline gate when the exact owned test server was stopped. The input became disabled and the page reported "Recording state is unconfirmed. Local audio remains quiet." plus `Failed to fetch`. It did not retain a stale open state or reconnect to a provider. This is offline connection-loss evidence, not physical or live-provider evidence.

Desktop and 390 by 844 pixel layouts were inspected with no horizontal overflow, and keyboard focus was visible. The final fix wave adds a literal source-text separator, updates Interrupt when a synthetic tone starts or ends, and supplies mobile navigation with a visible close button, Escape dismissal, focus movement and restoration, a focus loop and breakpoint-synchronized inert state. Navigation starts inert before script initialization, so hidden mobile links cannot enter the initial tab order.

The authored view and controller have automated DOM/audio-edge tests for those behaviors and for Requested -> Disconnect -> Stop confirmed -> new offline session. Live setup tests consume wire snapshots generated by the actual Python API/service with injected provider and clock edges. These checks do not constitute actual browser, microphone or live-provider acceptance.

Root-owned post-fix browser checks observed the served authored UI at 390 by 844 pixels and desktop width. Initial Tab navigation skipped hidden sidebar links. Opening navigation focused the visible Close button; Escape and Close restored menu focus. Resizing between mobile and desktop synchronized inert state without horizontal overflow. Requested -> Disconnect kept the question quiet, disabled Start and other fixture controls, and left Stop confirmed available. Stop completed cleanup automatically, after which a new explicit offline session and question succeeded. Transcript source labels had literal separation, and synthetic tone playback enabled Interrupt; the interruption action completed without error. A delayed question followed by Requested and Unknown produced no late answer; Stop then allowed a fresh fixture answer. Question-to-Ask keyboard navigation and final clean Disconnect also succeeded. These are actual offline UI observations; they establish no microphone, provider, physical-silence or acoustic-latency acceptance.

The final fix wave also ran `.venv/bin/python scripts/verify.py --output-dir /tmp/takeone-voice-final-fix.r1dEJ3/verification`. All seven checks passed: 220 product tests, 28 simulation tests, 56 web tests, JavaScript syntax, preservation audit, Ruff lint and Ruff formatting. The audit again checked 1,086 LeRobot files, skipped 6 generated metadata paths under the existing policy and reported zero failures. New verification evidence remains outside the repository; versioned `data/verification` is unchanged.

## Simplified UI evidence, September 12

Commit `799eab8` replaces the oversized hero, fixed-height paper transcript and exposed diagnostic cards with one compact dark panel. It retains TakeOne navigation and fonts, explicit offline/live modes, source labels, interruption, End session, and visible recording recovery. Test controls and connection diagnostics start collapsed; later snapshots preserve user disclosure choices. There is no fake speech waveform, new dependency, controller rewrite or hardware change.

Task-level verification passed all 60 web tests, JavaScript syntax and whitespace checks. The new authored-view regressions first failed for visible starts in both modes and recovery hidden by collapsed details. They now exercise actual authored HTML/JavaScript with the existing controller, including live gates, disclosure, exact-owner cleanup and preservation of collapsed panels.

Actual browser checks on the served new assets covered desktop 1920x992 and mobile 390x844. Offline questions returned explicitly labelled fixture text. Interrupt discarded a delayed reply. Requested and Unknown suppressed questions. Requested -> collapse test details -> End retained visible Stop confirmed with normal Start/question disabled; confirmed cleanup then permitted a fresh session. Mobile start/reply, menu focus, Shift+Tab wrap, Escape focus restoration and inert-state changes also worked. No horizontal overflow was observed. The initial misleading cross beside idle readiness was corrected to a neutral static dot and inspected after reload.

New screenshots, saved locally outside Git as original JPEG bytes:

- `/Users/basilliu/Downloads/TakeOne-voice-simple-SswdYf/01-offline-idle.jpg`
- `/Users/basilliu/Downloads/TakeOne-voice-simple-SswdYf/02-offline-answer.jpg`
- `/Users/basilliu/Downloads/TakeOne-voice-simple-SswdYf/03-offline-recovery.jpg`
- `/Users/basilliu/Downloads/TakeOne-voice-simple-SswdYf/04-mobile-offline-idle.jpg`

Actual 200% browser zoom was not established by the available browser controls; responsive resizing is not equivalent evidence. The authored reduced-motion CSS rule remains present, but runtime reduced-motion emulation was not performed. Neither check is recorded as passed. No microphone, provider or physical recorder was used. Browser viewport overrides were reset after testing.

## Counter-exhaustion fix and fresh verification

Commit `74e8b91` fixes the first authenticated snapshot after a pending request is cancelled by a Director scope change at `MAX_INTEGER`. The loopback HTTP regression reproduced a dropped connection before the fix. `_refresh_binding()` now rechecks retirement before setting scope/context while preserving the existing provider detachment and cleanup path. The first snapshot returns 200 with quiet, retired and bounded state; the released stale question returns 409 and a subsequent snapshot remains available. Review follow-up `10bddb7` shares one small retirement predicate between the two checks. Scoped re-review confirmed the finding addressed with no new breakage. The focused voice suite passed 79 tests, with Ruff lint and formatting clean.

The full verifier ran on this code using an external evidence directory:

```bash
.venv/bin/python scripts/verify.py --output-dir /tmp/takeone-voice-simplify-qWVu8N/verification-final
```

At `2026-09-12T22:43:11Z`, all seven checks on `10bddb7` exited 0: 221 product tests, 28 simulation tests, 60 web tests, JavaScript syntax, preservation audit, Ruff lint and Ruff formatting. Total: 309 tests. The audit checked 1,086 LeRobot files, skipped 6 existing generated metadata paths, and found no failures. LFS payloads and nested Git history remain outside that audit's verified evidence, as explained above. The separate rehearsal-server Ruff checks and `git diff --check` against integration base `6036010` also passed. The preceding successful run remains separately preserved under `verification`.

After restarting only the root-owned loopback server on port 8768 with the same external fixture database, a fresh browser session started offline, returned a source-labelled fixture answer and ended cleanly. No live connection or hardware action occurred. Remote main was checked read-only and still returned `6036010366c23cfdfccb020d43275be9e5f2322f`; no push or merge was performed. Versioned verification data, calibration, LeRobot source and the authoritative Director implementation are unchanged by this branch.

## Final ownership review follow-up

Whole-branch review of `6036010..5c19028` found two Important races using focused offline probes that the preceding 309-test suite did not cover:

- The server could build an old disconnect response from a replacement owner's shared state after releasing its cleanup lock, disclosing that replacement session's transcript/context to the old request.
- In the browser, a delayed response to the first of two End actions could overwrite a newly started session's connection state and stop its polling, despite rejecting the stale snapshot payload itself.

Commit `83e7240` fixes both races and directly equivalent cleanup returns. The server rechecks the original token/session under its lock before serializing disconnect, interrupt, fixture/trusted-recorder returns or a rejected live-creation error. Superseded results return `stale_result` without a snapshot, context or transcript. The controller guards cleanup completion by its originating owner and lifecycle before changing state, notices, media or timers. Success, unconfirmed cleanup and error completions are covered; the authored-view regression verifies overlapping End actions cannot disable a replacement rehearsal. No UI redesign or new ownership framework was added.

Meaningful RED cases used real loopback HTTP service/API/Director state with bounded cleanup holds, the real controller with injected HTTP/media edges, and the authored view. GREEN passed 81 Python voice tests and 75 web tests. Scoped independent rereview confirmed both findings addressed, with no new breakage or out-of-scope observations. These injected cases do not establish any real-provider disclosure, actual private-footage incident or physical-capture safety.

The latest complete verifier ran on `83e7240`:

```bash
.venv/bin/python scripts/verify.py --output-dir /tmp/takeone-voice-simplify-qWVu8N/verification-ownership-final
```

At `2026-09-12T23:01:13Z`, all seven checks exited 0: 223 product tests, 28 simulation tests, 75 web tests, JavaScript syntax, preservation audit, Ruff lint and Ruff formatting. Total: 326 tests. Audit counts and preservation limitations are unchanged: 1,086 files checked, 6 generated metadata skips, no failures, no nested Git or hydrated LFS-payload verification. The separate server Ruff checks and full-base whitespace check also passed.

Root restarted only its loopback server on the final code and observed offline question/reply, Requested -> collapsed details -> End -> visible Stop confirmed -> new session/reply -> End/reload. The page was left idle with no active owner/latch and default viewport. Network-delay races are covered by deterministic automated regressions, not claimed as browser-injected delays. Nothing was pushed, merged, sent to Discord, recorded physically, or tested with a real microphone/provider. Publication awaits Basil's separate choice.

## Reference-style follow-up, September 12

The second visual pass removes the sidebar, green tint, decorative outlines and dividers. It uses native, initially collapsed session settings and static decorative dots, not an animated or measured speech waveform. The original font stack, accessible labels, visible keyboard focus, explicit offline/live starts and existing controller remain. The offscreen skip link is also clipped until focused, preventing it from leaking into full-page captures after scrolling.

The new authored-view assertions first failed because mode and production selectors were still exposed on idle. The changed view passed all 9 view tests and all 75 web tests; JavaScript syntax checks passed. The obsolete custom mobile-menu test is replaced with coverage that collapsed settings preserve mode and cannot hide the live disclosure. A scoped independent review found no issues in the visual diff.

Actual browser checks covered desktop and 390x844 mobile layouts, no horizontal overflow, source-labelled offline questions/replies, Back to Director navigation, keyboard opening of Session settings with visible focus, live-unavailable disclosure outside closed settings, and Requested -> Unknown -> closed details -> End -> visible Stop confirmed -> fresh session. Live remains unavailable in the local setup. No microphone, provider, camera or hardware action was used. Viewport overrides were reset. Actual 200% zoom and runtime reduced-motion emulation remain unverified.

The first full verifier for this visual pass is preserved at `/tmp/takeone-voice-borderless-QfZMkh/verification`. Six checks passed; product tests reported one failure in the existing wall-clock blocked-arm/cart coordination test. Its simulated cart rejected a dispatch deadline before the test reached its intended nonzero-motion assertion. A focused three-test run also encountered deadline/peer-lease failures; a subsequent unchanged focused run passed all three. This is timing-dependent test evidence, not an all-green full-suite result or a physical robot observation. No motion implementation or hardware timing limit was changed by the visual pass.

A scoped diagnostic review reproduced the pre-motion failure through the real cart runner with an injected virtual-clock sleep overrun. Both multiprocessing tests depend on the laptop satisfying production timing defaults. Making them deterministic while preserving shared epochs and process isolation requires a coordinated test clock across the supervisor and workers, a separate motion-test change. Increasing physical limits, accepting a run that never exercised motion, or retrying until green would not fix this. The timing flake remains open and is explicitly included in the handoff; the final UI-only rerun passed 75 web tests, syntax and whitespace checks.

The local team packet is `/Users/basilliu/Downloads/TakeOne-voice-handoff-C1emGA/`: desktop idle, source-labelled offline conversation and mobile idle JPEGs, plus a copy-paste Discord message and integration checklist. Screenshots are original browser captures kept outside Git. Nothing has been pushed, merged or sent to Discord for this follow-up.

## Gate review recovery fixes, September 12

This review round inspected the five reported voice defects against gate starting HEAD `604c1bc39ff68b86930f9550d3bd837b633cd2fd` and reproduced each before changing production code. Changes are limited to the voice controller, service, regression fixtures/tests and this record. The authored UI and source labels remain unchanged.

| Finding | RED evidence and root cause | Fix and regression coverage |
|---|---|---|
| R1 | A real Director revision followed by Requested returned `stale_scope`, but the controller retained revision 0 because its local latch rejected the authoritative snapshot. | Monotonic metadata is accepted independently of offline local latch suppression. Stop and End recover with revision 1. Trusted live stop metadata is accepted while explicit reconnect remains required; stale, mismatched and fixture-stop evidence cannot release the live latch or reopen audio. |
| R2 | Both a backend-raised `TimeoutError` and worker completion before the timeout handler returned `operation_pending` on the next question, despite completed work. | Shared cancellation invalidates logical work and retires already-completed non-accepting futures. Tests cover fresh questions and replacement sessions, plus the existing rule that genuinely running uncancellable work retains the sole slot. |
| R3 | Holding live attachment after provider identity storage, then disconnecting and replacing the owner, let the old request detach the replacement transport. | Creation result, attachment, rejection and cleanup checks bind the original token, voice session, cancellation operation and provider identity. The replacement remains active and answers a question, including when the injected provider reuses its opaque ID. Existing uncertain-creation cleanup blocking remains covered. |
| R4 | Replayed and wrong-scope non-idle events cancelled worker work at both recording boundaries but left `pending_request_id` set after the completion callback. | Both boundaries use shared worker cancellation and logical invalidation. Rejected evidence creates no latch or renewed authority; the stale answer is discarded and a fresh question succeeds. |
| R5 | Held polling snapshot and renewal replies scheduled another timer after End/destroy or replaced the fresh session's timer. | Polling and renewal continuations check their originating owner and polling lifecycle after I/O. Success and failure completions cannot restart ended polling or alter replacement state. Existing authored-view coverage keeps offline Stop confirmation available during retained cleanup. |

The gate checkout had no local environment. A worktree-local `.venv` was created with the installed Python 3.13 and populated from `requirements-simulation.lock.txt` plus editable `.[dev]`. The focused verification asserted that the imported voice service came from this checkout. No original-worktree editable install, system package change or global configuration change was used.

RED used real loopback HTTP/API/service/Director execution with deterministic result-delivery and attachment holds. Browser RED used the real controller and service-produced wire fixtures with injected HTTP/media edges and controlled timers. The first Python RED run also exposed a cascading failure when a second timeout subcase could not create an owner after the first stranded slot; those cases were separated and both then independently reproduced `operation_pending`. Local logs are preserved in `.cache/voice-review/python-red.txt`, `timeout-red.txt` and `browser-red.txt` within this worktree. These ignored logs supplement the committed reproducible regressions; they are not versioned acceptance artifacts.

After applying all fixes, one focused verification round passed **85 Python voice tests and 77 browser voice tests**, with zero failures:

```bash
.venv/bin/python -m unittest tests.test_voice_api tests.test_voice_state tests.test_voice_provider
node --test apps/rehearsal/tests/voice*.test.mjs
```

GREEN output is in `.cache/voice-review/python-green.txt` and `browser-green.txt`. This round did not run the complete repository test or lint suites, push, create a PR or operate CI; those phases belong to the outer executor. The known wall-clock blocked-arm/cart coordination timing-test flake described above remains unresolved and was not rerun or altered here. Existing originals and versioned evidence were preserved. No runtime provider, microphone, recorder, camera or hardware call was made. Package 05 and live acceptance remain incomplete.

## End-first cleanup recovery follow-up, September 12

Review of gate starting HEAD `9c47865cd2d8085d81218c6a63b93536e2bf52c5` confirmed a remaining R1 path: End before the first post-revision poll discarded the authenticated `stale_scope` error snapshot. Polling was retired, Start and recorder controls were disabled, and the still-visible End button kept sending obsolete scope metadata. The previous Requested-first regression did not exercise this cleanup error boundary. Interrupt, media-failure cleanup and failed-setup cleanup shared the omission.

The controller now uses a small shared cleanup-error reconciliation helper. It checks the originating owner object, lifecycle, local barrier and destruction state before accepting a validated monotonic snapshot. This error path updates authoritative metadata and conservatively retains recording latches without restoring playback, changing local transcript/pending state, renewing authority timers or retrying an operation. The End notice directs an explicit retry; confirmed cleanup clears its stale error. Ordinary snapshot acceptance, explicit live reconnect, source/freshness checks, Stop recovery and polling retirement remain intact. No layout or source-label changes were made.

RED used a production bound to an offline session on the real loopback server. The fixture revised the real Director production, recorded the 409 `stale_scope` End response and a successful explicit retry, then created a fresh session and obtained a fixture answer over HTTP. The authored view/controller replayed those real wire responses at its HTTP edge. Before the fix, it retained revision 0 after End, with Start/recorder controls disabled and polling stopped. Separate injected cleanup tests also retained revision 0 for End, Interrupt, media failure and setup failure. Five tests failed for that expected reason; nine existing/expanded old-owner and barrier cases passed. RED output is preserved locally in `.cache/voice-review-end-first/red.txt`.

After all changes, one focused verification round passed **85 Python voice tests and 86 voice web tests**, zero failures, using this pipeline checkout's pinned `.venv` and an assertion that its imported voice service belongs to the current worktree:

```bash
.venv/bin/python -m unittest tests.test_voice_api tests.test_voice_state tests.test_voice_provider
node --test apps/rehearsal/tests/voice*.test.mjs
```

The authored-view GREEN case clicks End, observes quiet retained cleanup without an automatic retry, clicks End again using revision 1, starts a fresh session and receives source-labelled fixture text. Additional coverage rejects metadata from delayed replacement-owner errors and newer local barriers at all four cleanup paths, including errors whose snapshots would otherwise pass identity validation. Existing recording latch and polling regressions also passed. Local GREEN logs are `.cache/voice-review-end-first/python-green.txt` and `web-green.txt`; these ignored logs supplement the committed reproducible tests. This is authored-view execution with injected DOM/media edges and real loopback wire evidence, not a new visual browser or live-provider acceptance claim.

No complete repository test/lint suite, push, PR or CI phase was run. The independent robot timing-test flake remains unresolved for the outer test phase. No motion policy, originals or earlier versioned evidence was changed. No real microphone, provider, recorder, camera or hardware was used. Package 05 and live acceptance remain incomplete.

## Readiness and deterministic coordination review follow-up, September 12

Review starting from `a03fa33` confirmed all three remaining findings. The missing backend check was a server-boundary validation omission; the preservation failure was local argument shadowing; the coordination failures were a test-clock ownership problem. Existing voice fixes and the approved UI remain intact.

The RED run in this gate worktree reproduced both original CoordinationTests failing with `Cart dispatch deadline missed`, including an empty nonzero-command list in the blocked-arm test. This corroborates the earlier full-run failure recorded above. The real loopback HTTP regression returned 200 and created transport despite an absent conversation backend. The real preservation script, copied unchanged into temporary worktree fixtures with actual nested Git repositories and snapshot evidence, raised `AttributeError: 'list' object has no attribute 'output_dir'` for default and custom routing. `.cache/review-readiness/red.txt` retains the failures, including an initial test-class placement error that was corrected before the fix verification.

`tests/fixtures/coordination_clock.py` now supplies one cooperative virtual clock to the unmodified RobotRunner supervisor, Coordination health checks, actual spawned device workers, ArmRunner, CartRunner and simulated arm feedback. Time advances to the next scheduled wake only after the active participant yields. Real condition-wait timeouts fail a stalled fixture; bounded process joins separate completed worker teardown from virtual device deadlines. The former `tests/test_robot_motion.py` BlockingArm/BlockingFactory test setup maps to BlockingArm/ClockedFactory in this helper; its prior source remains recoverable from `a03fa33`. Production coordination code, device timing constants, peer/supervisor leases, motor policy and qualification are unchanged.

The revised tests require three distinct worker PIDs, a shared epoch and actual nonzero commands. The healthy case must finish both arms at their final goals and settle successfully. The blocked-phone case requires a nonzero phone command before the 400 ms read block, nonzero cart writes both before and during it, an actual lease-expiry fault, cancellation observed by all workers, and a nonempty zero-only shutdown covering the configured 100 ms window. Shutdown must finish before the phone read returns; no phone command may follow the start of the block and no cart motion may follow shutdown. The resumed read must still fail the unchanged IO budget. Additional deterministic cases inject a 25 ms cart wake overrun and a 6 ms write, requiring genuine dispatch-deadline rejection after motion and write-timeout rejection before motion, respectively. Neither case may resume motion, and both must deliver a zero-only shutdown window. These are causal simulation tests, not host scheduling or physical capability evidence.

Live creation now rejects an absent conversation backend before querying provider readiness or changing paid-session creation state. The HTTP regression supplies a ready provider stub and fresh trusted recorder evidence, requires `503 backend_unavailable`, no provider creation/cleanup, no stored provider identity or cancellation operation, and unchanged generation. Configuring the backend then permits the same owner's transport setup and cleanup. Availability reporting remains distinct. Existing positive creation, expiry, cleanup and replacement-owner race fixtures now explicitly configure their stub backend. The preservation script retains its parsed Namespace by naming the loop variable `git_args`; integration coverage checks successful and failing reports at both output destinations, relative routing from another working directory, nested Git history/status and byte-preserved imported evidence. Fixture manifest paths use portable POSIX separators.

This review used its own Python 3.13.12 `.venv`, installed from `requirements-simulation.lock.txt` and editable `.[dev]`; an import assertion confirmed the service belongs to this worktree. After all initial fixes, the focused command below passed 112 of 113 tests. The remaining test assertion searched only supervisor/cart errors even though the light worker correctly detected the phone lease expiry first. It now checks all real worker errors while still requiring lease-expiry evidence; the affected test then passed on its own. Logs are `.cache/review-readiness/green.txt` and `blocked-evidence-green.txt`. After making fixture manifest paths portable, the preservation integration test also passed all four subcases; its log is `preservation-portable-green.txt`. The diff whitespace check passed.

```bash
.venv/bin/python -m unittest tests.test_robot_motion tests.test_repository_integrity tests.test_voice_api tests.test_voice_state tests.test_voice_provider
.venv/bin/python -m unittest tests.test_robot_motion.CoordinationTests.test_blocked_arm_does_not_block_cart_writer_or_resume_motion
```

The assigned review-phase boundary leaves full verification, authoritative lint, npm setup, publication and integration to the outer executor. This is not a complete seven-check verifier pass: final acceptance still requires that executor to run the complete `scripts/verify.py` with this worktree's pinned environment, a fresh allowed external evidence directory, and inspection of all seven results. Merge remains held until that evidence supports it. No UI/browser change, real microphone/provider/recorder/camera call, hardware action, global configuration change, LFS hydration, or historical evidence modification occurred here.

## Focused test and recovery-notice follow-up, September 12

The subsequent test phase exercised `c2f1a8f` and corrected an offline recovery notice that still claimed the conversation was quiet after fresh recording authority reopened it. The authored-view regression in `apps/rehearsal/tests/voice-view.test.mjs` first failed on the obsolete expiry text, then passed with the controller correction. Already-expired replacement evidence still leaves questions disabled. Recorded checks passed 119 focused Python tests before this JavaScript correction and 87 voice web tests afterward. A real loopback browser check paused the owned server, observed expiry and disabled questions, resumed it, and confirmed an accurate recovery notice and a fresh source-labelled reply. The approved layout and live reconnect behavior remain intact.

Evidence is outside Git under `/var/folders/p3/6n3qk6y55kq9dz_4g2tlb_sc0000gn/T/no-mistakes-evidence/01M2C3TA4XE6CNN3HC47CJ7MZT/`: `walkthrough.md` indexes the browser checks, RED/GREEN logs, HTTP responses, preservation audit and retained causal coordination reports. These are focused offline results, not a complete verifier pass or hardware qualification. The documentation/lint phase subsequently passed Ruff lint and formatting for all 18 changed Python files, the configured JavaScript syntax check, syntax checks for the five changed web fixture/test files, and diff whitespace checks. It ran no tests. The complete final-code verifier and publication decisions remain with the outer executor.

## Remaining acceptance

- No microphone permission, real media track, provider call, upload, recorder, camera or hardware path was tested.
- Provider denial, media faults and stale identities have automated injected-boundary coverage, not real provider or device acceptance.
- Real recording silence requires an integrated recorder notification before device start plus an on-site measurement. Local playback suppression is not an emergency stop.
- Package 05 remains `in_progress` until visual coaching, real camera and recorder integration, real take review and the package-level demonstration have evidence.
