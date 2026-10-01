# ChatCut Qualification Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the code task and its review. The controller runs the live experiments separately.

**Goal:** Make the existing ChatCut diagnostic path repeatable from TAKE ONE's Python environment and detect unsafe target/state assumptions without changing the editing architecture.

**Architecture:** ChatCut remains the external editor and exporter. Add one opt-in, read-only Python qualification probe, not a production adapter, renderer, server or autonomous editing engine. Reuse the observed local stdio connector and leave Director/UI/hardware contracts untouched.

**Tech Stack:** Existing Python >=3.12, standard library, unittest, pinned Ruff; ChatCut Desktop 0.3.16 and its discovered MCP 0.1.6 bridge for live checks.

**Spec:** `docs/editor/README.md` qualification record and Sections 1, 3, 9 of `/Users/basilliu/Downloads/TAKE-ONE-AI-Editor-Engineering-Spec.md`. The user's latest direction keeps ChatCut and authorizes small compatible additions without repeated approval. This plan implements only bounded qualification support, not the full editor specification.

## Global Constraints

- ChatCut remains the editor and exporter. No alternate backend, native-renderer expansion, private upload, paid generation, hardware command or third-party app patch.
- Use only explicit local executable paths and direct subprocess argument lists, never shell execution, credential extraction or copying the launcher contents.
- Probe calls are read-only: initialize, tools/list, get_active_project, read_project, preview_timeline and inspect_item. No generic public mutation method or automatic retry.
- Fail closed on wrong project/timeline, incomplete pagination, malformed responses, provider errors, disconnects and bounded timeouts. Do not print provider stderr or raw error messages containing possible credentials.
- Existing frame/color failures remain measured limitations, not silently relaxed acceptance gates. A successful probe proves read access and state detection, not full C0 or export fidelity.
- Preserve originals and unrelated working-tree changes. Never author em dashes, modify CHANGELOG or add agent co-authors.
- No new runtime dependency, database, service, UI route or Director contract.
- No push, PR merge or vendor message in this implementation batch. Local feature commits are permitted; external delivery remains separate.

## Task 1: Read-only Python connection and state check

**Files:**
- Create `packages/takeone/editor/chatcut_probe.py`.
- Create `tests/editor/test_chatcut_probe.py` and, if needed, `tests/editor/chatcut_peer.py` for a fake stdio process.
- Controller updates `docs/editor/README.md` after live verification.

**Interfaces:**
- `ProbeError` is the public bounded failure type with sanitized human-readable messages.
- `probe(command: list[str], project_id: str, timeline_id: str, timeout_s: float = 10.0) -> dict` starts the explicit local command, initializes MCP, discovers every tool page, checks the target, reads the whole requested timeline and each placed media item, and closes the child process on every path.
- The result contains `schema_version: 1`, `project_id`, `timeline_id`, `server_info`, complete `tools`, complete `snapshot`, and `fingerprint` (SHA-256 over stable canonical snapshot JSON). Keep volatile transport request IDs outside the fingerprint. Include full item inspection results so changes to fades, gain, crops and attached transitions are observable, not just clip placement.
- `main(argv=None) -> int` backs `python -m takeone.editor.chatcut_probe` with required `--server`, `--project-id`, `--timeline-id`; optional `--timeout-s`, `--output`, `--compare`. Output files use exclusive creation, never overwrite. A previous report with another target, invalid format or changed fingerprint causes nonzero exit; no repair/mutation is attempted. Mark the result explicitly as read-only qualification rather than production readiness.

### Required behavior and tests

- [x] Write tests before implementation. Use a real subprocess fake MCP peer, not a mocked successful probe. The peer only implements observed response shapes and fixtures; keep fault controls out of production code.
- [x] Demonstrate RED with `python -m unittest discover -s tests/editor -p test_chatcut_probe.py -t tests/editor -v` before implementation; record the missing-feature failure.
- [x] Initialize protocol `2024-11-05`, send initialized notification, follow all `tools/list` cursors. Fail on repeated cursors, duplicate/inconsistent tool names or missing required tools. Save input schemas without invoking unapproved names.
- [x] Validate identity via `get_active_project` and `read_project`; reject mismatches rather than calling target_project. Read the expected timeline and reject different returned IDs. Validate nonempty structured data rather than accepting a text success message.
- [x] Follow preview pagination to exhaustion, preserve all entries/tracks, reject repeated offsets or total/state changes. The observed live result uses `structuredContent.state`, `structuredContent.timeline.entries`, `totalEntries`, `tracks`, and optional `nextOffset`. Inspect every actual item ID, not gaps. IDs are literal UUIDs from observations; no guessing or matching display names.
- [x] Compare snapshots deterministically. Test an externally changed audio gain or attached transition (same clip count/placement) changes the fingerprint. Repeated identical state must compare equal. Require one visible timeline for this qualification path, or fail with a single-timeline explanation, because native export uses the viewed timeline rather than reliably honoring the tool working target.
- [x] Bound all reads and clean up child resources. Tests cover response timeout, EOF, malformed JSON, mismatched IDs, tool isError, pagination loop and missing structured snapshot. Never replay a request on timeout. Stderr is not included in exceptions/reports. No secrets in stdout on failure.
- [x] Test CLI success, changed state, wrong target, invalid prior report, invalid/NaN/infinite timeout, and refusing an existing output file. Failure returns nonzero and gives a short useful error, without traceback or raw provider error text.
- [x] Implement minimally. A single reader thread/queue is acceptable for portable Windows pipe timeouts. Use bounded line/message sizes and notification handling; terminate/wait/kill cleanup must not hang or leave a reader blocked on its child.
- [x] Run focused tests, then the existing editor suite. Run Ruff check and format check on changed Python files. Commit only the Task 1 implementation and tests after passing checks; leave controller docs/plan uncommitted for its final update.
- [x] Self-review and report RED/GREEN command outputs, commit, and actual limitations. Do not invoke live ChatCut or another agent; the controller owns live state and reviews.

Representative behavioral expectations (derive fixtures independently):

```python
first = probe(peer_command, "project-1", "timeline-1", timeout_s=1)
assert first["schema_version"] == 1
assert len(first["tools"]) == 5  # fixture: two tool pages, not a production constant
assert first["project_id"] == "project-1"
assert first["timeline_id"] == "timeline-1"
assert len(first["fingerprint"]) == 64
# Separate peer case changes only the inspected audio gain.
changed = probe(changed_gain_peer_command, "project-1", "timeline-1", timeout_s=1)
assert changed["fingerprint"] != first["fingerprint"]
```

## Task 2: Live qualification and integration handoff (controller)

**Files:** Local generated evidence under `~/Movies/takeone-qualification.FWzKht/`; update `docs/editor/README.md` and older checkout pointers only after observations.

- [x] Run the probe against the existing dedicated single-timeline synthetic project. Re-run with `--compare`; identical state must pass without duplicate media/jobs.
- [x] Make one bounded diagnostic audio gain change through the established native tools, run compare and require divergence detection, then restore the exact prior gain after readback. This tests detection, not concurrent compare-and-set or a production conflict UI.
- [x] Verify the original multi-timeline project is rejected by the probe; return Desktop to the dedicated diagnostic project afterward.
- [x] Export the same diagnostic timeline at 480p and 1080p through ChatCut. Check expected duration, dimensions, rational frame rate, frame count, full decode and unchanged originals. Keep known frame/color issues distinct from file accessibility.
- [x] Review Task 1's diff, fix/retest any findings through the implementer, and perform final review. Update docs with actual commands and evidence; do not call the full AI editor done.
- [x] Run root verification with output outside Git when relevant runtime dependencies are available. Document actual pre-existing failures without conflating them with this isolated read-only module. Do not alter hardware/calibration to make a test green.

## Loop and completion condition

For each failure: reproduce, trace the failing boundary, change one controllable cause, rerun the focused test and regression check. Do not repeat a known vendor defect indefinitely. This batch is complete when the portable probe, offline failures, live read/repeat/divergence checks and preview/final artifact checks are implemented, reviewed and honestly recorded. Full C0, real footage, VFX reasoning and Windows physical testing remain separate, explicit gates.

Completed September 15: task review, two scoped task fixes, final broad review
and its single scoped fix wave are closed with no outstanding review finding.
Final focused/editor counts are 43/135; live comparison and repository-wide
lint/format checks pass. Root verification's 28 inherited cinematic subtest
failures remain recorded in the editor README, so completion of this bounded
qualification plan is not whole-repository merge readiness. Branch and local
evidence are retained; nothing was pushed or merged remotely.
