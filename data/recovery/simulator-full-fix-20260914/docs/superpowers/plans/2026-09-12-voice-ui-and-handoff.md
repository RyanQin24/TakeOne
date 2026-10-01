# Voice UI Simplification and Handoff Plan

> **For agentic workers:** Execute task-by-task with test-first changes and independent review. Basil approved this direction and local implementation on September 12. Publication, live spending, microphone use and merging still need their separate approval.

**Goal:** Make the voice page a simple conversation interface, then share the tested foundation and progress to real voice integration.

**Architecture:** Keep the existing VoiceController, LiveMediaSession, Python service and recorder authority. Change presentation within the existing TakeOne app, not the Director, robot control or application framework. Fix the separately recorded counter-limit service defect in its own scoped change.

**Tech Stack:** Existing vanilla HTML/CSS/JavaScript, Node tests and Python environment. No new UI library, animation library, model or service.

**Spec:** The approved UI design below supplements [the approved voice specification](../specs/2026-09-12-voice-conversation-design.md). The original specification continues to own privacy, offline/live separation, ownership and recording rules. Basil approved the simpler direction and asked to proceed; do not request repeated design approval.

## Evidence and what changed

- Local implementation HEAD inspected: `d59d94e5796e3125313165f17045608b8e093aa6` on `feat/voice-conversation`.
- Read-only remote check during this review returned main `6036010366c23cfdfccb020d43275be9e5f2322f`, already the branch's integration baseline. Recheck before publication; do not assume it remains unchanged.
- Ryan's feedback relayed by Basil: make the UI less "vibe coded". No more specific preference is attributed to Ryan.
- Basil supplied `/Users/basilliu/Downloads/123123.png` and [OpenAI's GPT-Live-1 demo](https://openai.com/index/introducing-gpt-live-1-in-the-api/) as a simpler reference. It establishes a visual preference, not working TakeOne microphone/provider integration or a request to copy OpenAI branding and legal text.
- The existing Director and voice CSS use the same background `#191b18`, panel `#252a21`, accent `#d7e7b4`, paper `#eae9df`, and Segoe UI/Arial stack. The logo and sidebar styling were also reused.
- The Director home already has a large editorial heading. The voice implementation extended that treatment with a new slogan, a large empty transcript panel and several diagnostic cards. Matching theme did not establish that this was the right layout for a conversation task.
- The voice branch changed the existing Director screen only to add a voice navigation link and its spacing. It did not replace Caesar's Director UI. This follow-up should not do so either.
- The last completed verification was 304 tests and seven checks passing, with actual offline browser evidence. Those results cover the old layout, not this proposed redesign. One counter-exhaustion scope-refresh error remains documented.

## Approved UI design

Purpose: let a creator start a voice session, see its actual state, interrupt or end it, and optionally inspect the transcript. Basil also needs access to offline integration tests. These are different levels of detail, not different applications.

Use the reference's simple hierarchy inside TakeOne's existing navigation:

1. Small title: **Voice rehearsal**. No slogan, oversized question mark or editorial hero.
2. One restrained dark panel with a compact state indicator and one short explanation.
3. An explicit **Offline test / Live voice** mode choice. Default remains Offline test; never switch to paid mode automatically. Offline start is labelled **Start offline rehearsal**; live start is labelled **Start voice session** and remains disabled until the existing gates permit it.
4. A compact production selector: optional for offline, required for live. Only one start action is visible for the selected mode.
5. During a session, keep **Interrupt** and **End session** visible beside the current state. Ending or interrupting preserves the existing conservative cleanup/reconnect behavior.
6. The transcript is secondary and expandable, without a fixed 650-pixel paper card. In offline mode, starting reveals the typed question field and labelled fixture result so the test remains usable.
7. Put recording-event simulation, reply delay, synthetic tone and transport/backend/recorder diagnostics under a collapsed **Test controls and connection details** disclosure. Do not remove those controls or their tests.
8. Keep recording silence, connection errors and recovery actions visible outside that disclosure. If offline cleanup needs Stop confirmed, expose that control immediately; hiding diagnostics must not hide the only recovery path.
9. Show microphone/provider disclosure before live connection. Keep fixture provenance visible. Do not copy the reference's OpenAI Terms/Privacy consent text as TakeOne's policy.
10. No decorative fake waveform. An idle indicator may be static. Any connecting animation represents connection state only, not measured speech. Audio-reactive visualization is not required for this pass and must not acquire a microphone for visual effect.

Retain existing TakeOne fonts and navigation. Use a simple charcoal content panel with a restrained primary button, not a second marketing design. No new images, fonts, dependencies, glass effects, gradients or page-load animation. Respect reduced motion and keyboard focus.

Rejected alternatives: merely recoloring the existing page would retain its competing sections; building a separate standalone demo would split navigation and duplicate a product surface. The proposal simplifies the current page while keeping its tested backend.

## Global constraints

- This plan changes no motor, arm/cart, calibration, Director ownership or recorder authority contracts.
- A hidden or disabled UI control cannot replace server-side validation.
- `recording_requested`, uncertainty and lost authority remain quiet. Never hide an active stop/cleanup requirement to make the page look simpler.
- Fixture mode performs no provider call or microphone acquisition and cannot acknowledge a real recording.
- Keep source-labelled transcript text. Speech and text cannot command production or hardware.
- Preserve exact-owner cleanup, stale-result rejection, bounded history and existing session-duration requirements.
- No push, PR creation, merge, live spending or microphone test is authorized by this planning turn. Publication and live acceptance need their respective approval.
- Keep new test evidence outside tracked `data/verification`. Do not modify generated files, CHANGELOG.md, saved footage or credential stores.
- Use apply_patch for authored changes and never add an em dash or agent coauthor.

## Task 1: Simplify the voice presentation and prove its recovery flow

**Files:** Modify `apps/rehearsal/dist/voice.html`, `voice.css`, `voice.js`; test in `apps/rehearsal/tests/voice-view.test.mjs`. Preserve `voice-controller.js`, `voice-media.js`, Python routes and Director UI unless a concrete regression requires a separately scoped change.

**Interfaces:** Consume the existing controller snapshot (`mode`, `connection`, `quiet`, `quietReason`, `pending`, `transcript`, `runtime`, `recordingLatchActive`) and existing `startOffline`, `connectLive`, `interrupt`, `disconnect`, `ask` and `simulateRecording` methods. Produce simpler view state only; no new wire fields.

- [x] Basil approved the simpler hierarchy and local implementation. Keep the current screenshots as the before-state, not a promised final design.
- [x] Extend the existing authored-view test harness to represent native details visibility. Add a stable `testControls` ID to the existing fixture disclosure, with no `open` attribute. Reuse the current controller-backed `view()` harness, not a disconnected idealized mock.
- [x] Add consumer-visible view tests: initial mode exposes only offline start; choosing live changes the visible action without making a request; diagnostics start collapsed; cleanup makes its recovery control visible even when diagnostics are collapsed. Use the authored view and real controller, and verify native disclosure visibility in the actual browser. Do not add tests that grep marketing copy or forbid old source strings; removal of the oversized hero is checked visually.

- [x] Add view assertions for mode-specific start controls and disclosure-before-live. Default must expose offline start, hide live start, make no media call and leave live readiness false. Selecting live must not start a session, bypass missing prerequisites or silently return a fixture reply.
- [x] Extend the existing Requested -> Disconnect -> Stop confirmed -> new session regression: with test details collapsed, cleanup must reveal a visible Stop confirmed action; normal start and question remain disabled until it succeeds. Existing tone interruption, literal transcript labels and keyboard/navigation tests remain required.
- [x] Run `node --test tests/voice-view.test.mjs` from `apps/rehearsal`; record the intended RED results before editing presentation.
- [x] Replace the hero and card grid with the proposed panel. Retain existing control IDs where practical. Move diagnostics rather than deleting behavior. Example disclosure markup:

```html
<details id="testControls" class="test-controls">
  <summary>Test controls and connection details</summary>
  <!-- Existing fixture controls and readiness details remain here. -->
</details>
```

- [x] Keep routine copy mode-aware. A live recorder observation must not be described as simulated; a disconnected session must not show a stale "rehearsal open" explanation. Render one primary status, with separate actionable errors, rather than several competing status cards.
- [x] Run `npm test` and `npm run check` in the rehearsal app. All 60 web tests passed; no shared contract changed, so Python verification belongs to Tasks 2 and 3.
- [x] Exercise the served page at desktop and 390-pixel width: start, typed fixture reply, interruption, requested/unknown recording, cleanup and fresh start. Check tab order, disclosure behavior, visible Interrupt/End/recovery controls and no horizontal overflow. Do not acquire media.
- [ ] Actual 200% browser zoom and runtime reduced-motion emulation: not established by available browser controls. The authored reduced-motion rule was inspected. Responsive resizing is not zoom evidence.
- [x] Capture before/after screenshots of idle, offline answer and quiet/recovery states, clearly labelled offline. Show Basil the result before publication. Record actual observations in the implementation guide; do not reuse the previous layout's test claims as new evidence.
- [x] Commit this scoped UI change with its tests after approval and verification. Commit `799eab8`; independent task review approved without findings. Not merged into the team's main.

## Task 2: Fix the remaining counter-exhaustion error

**Files:** Modify `packages/takeone/voice/service.py`; test in `tests/test_voice_api.py`. Preserve retirement rules in `state.py` unless the reproduced result establishes a separate defect.

**Interfaces:** The existing authenticated snapshot HTTP route calls `VoiceService.snapshot(token)` and `_refresh_binding()`. At MAX_INTEGER, an interruption retires the state; changing scope immediately afterwards currently raises. The first snapshot should instead succeed with bounded generation and a quiet retired state.

- [x] Reproduce through the existing loopback HTTP fixture with an injected `MAX_INTEGER` Director generation and a genuinely pending backend question. Wait for the backend's entered event, change the injected Director revision, then request the authenticated snapshot. Root observed `RemoteDisconnected` on the first snapshot with a `set_scope` retirement exception, followed by quiet bounded state on retry. The original counter-only sample was incomplete: cancelling without pending work does not advance or retire the identity. The regression must use bounded waits and release its backend worker in `finally`.

- [x] Run `.venv/bin/python -m unittest discover -s tests -p test_voice_api.py -v` and record RED. The new pending-worker test alone failed in the 27-test API run, then passed after the fix with exact-owner cancellation and successful subsequent reconciliation.
- [x] In `_refresh_binding`, re-read retirement after `_cancel_pending_locked`. Only call `set_scope` and replace context when the state remains eligible. Still detach/close live media and run the existing cleanup path; do not return early past cleanup or weaken retirement.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p 'test_voice_*.py' -v`, Ruff lint and format checks. All 79 voice tests passed, including existing stale-owner, stale-result, trusted-stop and rejected-recorder-lease cases.
- [x] Update the implementation record to close this specific issue only after the loopback regression and scoped review pass. Commits `74e8b91` and `10bddb7`; scoped review required one shared retirement predicate and rereview confirmed the finding addressed.

## Task 3: Verify and offer the branch for integration

**Files:** Update `docs/ai-director/implementation/05-rehearsal-voice.md` with the new evidence and screenshots' local locations. Do not add private transcripts or saved media to Git.

- [x] Recheck remote main before integration. The September 12 read-only check still returned `6036010`. Recheck again before any later publication; no fetch, rebase or merge was performed.
- [x] Run the full verifier from the voice worktree with an external evidence directory. All seven checks exited 0 on `10bddb7`: 221 product + 28 simulation + 60 web = 309 tests. Evidence: `/tmp/takeone-voice-simplify-qWVu8N/verification-final`.

  After whole-branch review fixes in `83e7240`, the final run also passed all seven checks: 223 product + 28 simulation + 75 web = 326 tests. Latest evidence: `/tmp/takeone-voice-simplify-qWVu8N/verification-ownership-final`. Keep the earlier run as historical evidence, not the final count.

```bash
voice_handoff_evidence=$(mktemp -d /tmp/takeone-voice-handoff-XXXXXX)
.venv/bin/python scripts/verify.py --output-dir "$voice_handoff_evidence/verification"
```
- [x] Run `.venv/bin/python -m ruff check apps/rehearsal/server.py`, `.venv/bin/python -m ruff format --check apps/rehearsal/server.py`, and `git diff --check` against the inspected integration base. All passed.
- [x] Review the complete feature diff, then test any resulting fixes. Whole-branch review found two stale-owner cleanup races; `83e7240` fixes both with loopback HTTP/controller/authored-view regressions. One scoped rereview confirmed both addressed and no new breakage. Robot/calibration, saved team evidence and the authoritative Director implementation remain unchanged.
- [ ] Report the scope to Basil: simplified UI, offline behavior verified, actual live voice and physical capture still unverified. Ask for explicit publication approval if it has not been given by then.
- [ ] After approval, push `feat/voice-conversation` and create a PR against TakeOne main. Include screenshots and verification summary; leave live mode disabled and do not merge automatically. No Discord send without approval.

## Subsequent milestones, not authorized implementation in this plan

4. **Live voice on Basil's laptop.** First inspect and agree the actual Director conversation adapter. Configure approved access and a finite test duration. Define an isolated recording-event test setup without allowing fixture provenance to acknowledge a real recorder or pretending `recorder_ready=True` establishes integration. Then test a real spoken response, interruption, disconnect and silence on simulated events. Keep public/demo claims explicit about the simulated recorder. This requires a separately approved integration design and live test, not just an API key or a UI toggle.
5. **Real recording handoff.** Identify the capture owner and wire notification before record-start plus confirmed stop/unknown state, with timestamps in the voice clock domain. Ryan/Caesar validate actual capture silence and failure behavior on-site. Their arm/cart test update does not establish completion of this interface.

No VLA work, new Director, cart controller, broad UI redesign or robot test is added to Basil's scope.

## Focused design critique

Heuristic assessment of the current local screenshots, authored markup/CSS and previously recorded browser behavior, not a new user study or accessibility certification. The requested frontend-design helper is not installed under that name; the available intentional-frontend principles were used with critique's cognitive-load, scoring and persona references.

**Anti-pattern verdict: fails the task-fit check.** The oversized slogan, uppercase section labels, large empty paper area and repeated diagnostic cards make a practical conversation control look like a generated marketing workspace. The green palette alone is not the defect: it is inherited from TakeOne.

| Heuristic | Score /4 | Observation |
|---|---:|---|
| System status | 3 | Visible state and errors, but several repeated summaries compete |
| Real-world language | 2 | Transport, fixture and audio-gate terms dominate creator-facing copy |
| User control | 3 | Interrupt and cleanup exist; End session is too visually secondary |
| Consistency | 3 | Existing palette, font and brand match; content hierarchy does not fit voice |
| Error prevention | 3 | Explicit offline and disabled live gates; no physical acceptance implied |
| Recognition | 3 | Controls labelled, but too many require scanning |
| Efficiency | 2 | Keyboard support exists; page is unnecessarily tall for the task |
| Minimalist design | 1 | Hero, fixed-height transcript and several always-visible panels |
| Error recovery | 3 | Recovery tested, but diagnostic language and placement need improvement |
| Help | 2 | Plenty of explanation, insufficient prioritization |
| Total | 25/40 | Acceptable foundation; significant presentation improvement needed |

Cognitive-load checklist: fail single focus, chunking, hierarchy, one decision at a time, minimal choices, progressive disclosure; pass related grouping and low recall demand. Six of eight failures. This describes the overexposed offline test screen, not six backend bugs.

What works: truthful fixture/live distinction; existing brand consistency; tested interruption and recovery controls. Preserve those strengths.

Priority issues: P1 competing creator/testing modes and unclear main action (`distill`); P2 oversized hierarchy and unused transcript space (`arrange`); P2 technical and repetitive microcopy (`clarify`); P2 essential End/recovery actions visually subordinate (`arrange`). Final `polish` checks spacing and accessibility without inventing new decoration.

Persona walkthroughs: Jordan, a first-time creator, encounters "AUDIO GATE", six recorder states and three readiness statuses before understanding the live/offline distinction. Alex, a teammate testing integration, can reach the controls but has to scan a tall page to end the session; test tools should remain one disclosure away. Sam, a keyboard user, benefits from the tested focus behavior, but many diagnostic controls add unnecessary tab stops; collapsing them must not hide required recovery. No screen-reader or 200% zoom success is inferred from earlier keyboard tests.

The user-supplied reference resolves the main direction: simplify hierarchy, preserve behavior. Basil approved the direction and implementation. No additional aesthetic questionnaire is required.
