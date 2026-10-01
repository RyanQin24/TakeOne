# Generative VFX intake implementation plan

## September 17 renderer ownership approval and autonomous delivery

Latest team instruction overrides any earlier merge authorization: keep this
work isolated, do not merge, and retain published PRs as drafts. Local feature
implementation and verification may continue without task-boundary questions.

Basil explicitly approved retaining ChatCut for effects while qualifying
TAKE ONE's existing renderer for final assembly/export. He also authorized
continuing between tasks and publishing coherent, verified batches without
asking after every step. This supersedes the older no-push limit and the
native-ChatCut-export prerequisite for the approved route only. Original
preservation, exact timing/color checks and reviewed-derivative gates remain.
No new subscription, unbounded paid generation, hardware run or public sharing
of private media follows from this approval. Native ChatCut export remains
unqualified rather than relabeled as passing.

- [x] Task 2: qualify the existing renderer through actual editor operations.
- [ ] After qualification, implement the separate script/footage-informed VFX
  planner and compatible generation/review/assembly path in further reviewed
  batches. Preserve unfinished status until each path has evidence.
- [ ] Publish tested changes as cohesive feature PRs with setup, tests, and
  limitations documented. Keep director repairs separate from editor features.

## September 17 approved completion sequence

Basil approved the following follow-up after reviewing the personal-footage
background-people demo. This supersedes the earlier no-paid-request limit for
the bounded operational comparison only, not permission for new subscriptions.

- [x] Recheck isolated worktree and run the unchanged editor baseline: 166 tests
  pass in 42.304 seconds on September 17. No hardware accessed.
- [x] Run the bounded model/settings comparison (not production qualification). Maximum four new short jobs;
  target maximum 15 ChatCut credits, checked against actual ledger after each.
  Repeat the successful people prompt, then test a background change and a
  localized effect. Reserve the fourth call for an evidence-based reason.
  Compare first/middle/end, wave behavior, framing, duration, audio, cost and
  latency. Keep the original silent source for every generation.
- [x] Research one challenger, Runway Aleph 2, without buying access. The current
  discovered ChatCut schema does not expose it. Seedance remains blocked for
  the tested real-person input; no refusal retries or safety-filter evasion.
- [x] Reproduce native timeline/export qualification with current supported
  tools. Preserve exact expected cut frames and original color tolerances.
  Do not implement an automatic executor on a still-failing exporter, silently
  select a replacement renderer, or patch the vendor application.
- [x] Once those gates pass, implement the separate VFX planner in the existing
  editor, keeping Caesar's scene-script instructions intact. Consume actual
  source spans and observations, propose changes and protected content, include
  start/end times and a no-effect choice, and validate all proposals before any
  generation. A deterministic mock is not a live semantic planner.
- [ ] Integrate one path through generation, reviewed derivative intake,
  explicit timeline placement and native export. Keep original audio and
  originals; record any timing transform. Do not weaken the existing one-frame
  duration check to admit the previous six-second demo.
- [ ] Verify varied shot lengths, playback/audio sync, undo, provider failure,
  restart reconciliation and absence of duplicate paid jobs. Publish only after
  separate shipping verification; Windows acceptance still needs the team's
  actual environment and is not implied by Mac tests.

Operational evidence stays outside Git at
`~/Movies/takeone-vfx-selection.N40lMf/`. This is an execution roadmap, not a
claim that the full automatic adapter or VFX planning model is implemented.
If qualification needs a significant architecture change, stop at that gate
and request the smallest necessary decision while preserving completed work.

Execution checkpoint: three new Omni jobs (`d66486cae1`, `166f92e952`,
`8c39aaee7a`) cost 7.95 credits; 83.68 remain. Fourth call not used. Repeat
guests and background replacement are promising sampled demos; localized
butterfly misses the requested 5 s cutoff. All three exceed source duration
by about 49 ms and are not approved derivatives. Fresh native export still
places hard cuts one frame late and exceeds source-color tolerances. The
read-only timeline fingerprint matches its prior baseline, so no speculative
TAKE ONE code fix was made. Downstream unchecked tasks remain blocked pending
a supported provider fix or explicit rendering-ownership decision. No new
model subscription, planner, automatic adapter, push or merge in this batch.

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans. Track steps with checkboxes.

**Goal:** Prepare a real short augmentation test and implement the existing editor's safe intake of reviewed generated derivatives while paid generation access is pending.

**Architecture:** Keep ChatCut as the proposed external editor/generation path. Reuse TAKE ONE's existing media import, operation journal and project service, with a small derivative intake route. This slice does not build a second renderer, claim an AI planner, submit cloud jobs or automatically replace a filmed take.

**Tech stack:** Existing Python standard library, editor API/reducer/SQLite, unittest and installed FFmpeg/ffprobe. No new dependencies.

**Spec:** Caesar's `/Users/basilliu/Downloads/TAKE-ONE-AI-Editor-Engineering-Spec.md`, section 18, and Basil's September 16 approval of augmentation-first qualification. Keep scene scripting separate from VFX instructions. The full approved workflow remains: visible effect proof, separate VFX planning, application integration, complete workflow tests.

## Global constraints

Latest September 17 research follow-up: an authorized personal phone-clip test
now adds two seated background guests. First Omni output swapped the subject's
waving arm; second constrained the correct image-right arm and is the better
demo, not exact-preservation approval. Jobs `a61a4cac4b` / `011867f62c`, 5.30
credits total, 91.63 remaining; no further jobs queued. Both raw outputs last
6 s vs the 5.950544-second input. Preserve the existing duration gate; do not
pass the demo to approved-derivative intake merely because generation completed.
Local evidence: `~/Movies/takeone-people-test.3L6z0J/REVIEW.md`. Model selection,
repeatability, explicit duration normalization and end-to-end integration remain
open. Earlier "background people untested" text is a historical checkpoint.

September 17 research checkpoint, separate from the implementation constraints
below: Basil approved a bounded Gemini Omni test after Seedance refused the
licensed actor input. Omni job `5d463df262` produced a visible portal/city
background for 1.77 credits, leaving 96.93. The eight-second team before/after
is at `~/Movies/takeone-cinema-test.47zzRx/TEAM-DEMO-before-after.mp4`.
Output aspect ratio changed from 2.4:1 to 16:9 with lost side content and
nonzero generated audio, so **do not mark preservation approved or weaken
the existing derivative aspect-ratio check**. Source hashes are unchanged.
See editor README and local `REVIEW-OMNI-2026-09-17.md` for measured evidence.
Adding background people, dialogue, production integration and Windows remain
open. Proposed next experiment is one consented native-16:9 single-subject clip
plus one or two fictional background extras; not submitted or queued. Keep
scene scripting and VFX planning separate, and retain the current architecture.

- Preserve originals byte-for-byte. Never alter TakeRecord or claim the robot captured generated content.
- No hardware access, credentials in output, paid requests, uploads, purchases, push or merge in this code task.
- New paths run without hardware or cloud, with explicit simulated provider evidence.
- No em dash in authored text. Do not edit generated files or CHANGELOG.md.
- Keep existing Director, heuristic planner, UI and renderer unchanged; do not present their existing behavior as semantic AI editing.
- A successful provider job is not evidence of visual preservation or timeline application.
- No automatic substitution or reuse of old action/audio anchors. Import is not application or final export.
- Preserve the existing dirty editor README. Work in the existing isolated worktree, not main.

## Task 1: Reviewed derivative intake through the existing editor API

**Files:** Create `packages/takeone/editor/vfx.py`, `tests/editor/test_vfx.py`; modify `packages/takeone/editor/api.py` and, only if needed for atomic duplicate detection, `packages/takeone/editor/service.py`. Register the new module's appropriate layer in `tests/editor/test_layering.py` without weakening that invariant. Do not add a general workflow framework.

**Interfaces:** `POST /api/editor/projects/{project_id}/vfx/derivatives` imports a reviewed local generated video into the project's media library and operation history, never the timeline. Return `schema_version`, `ok`, `media_id`, `reused`, `status: "reviewed_derivative"`, `placed: false`, and the lineage. Repeating identical content and lineage must not create a second operation, including after service reload. Conflicting provenance for already-imported bytes is rejected, not silently relabeled.

Review-discovered dependency: `repository.operations` defaults to a 10,000-item page. Internal replay and provenance lookup must not silently truncate long journals. Extend `service.py` and, if necessary, `repository.py` with paginated/targeted reads while retaining appropriate bounded HTTP history responses. Add real journal coverage for derivative import/retry/reload beyond sequence 10,000. Do not hide this with an arbitrary project-size restriction.

The fix reproduction also exposed truncated SSE backlog sequence detection in `api.py` and native journal export in `export/native.py`. Correct those existing consumers with narrow regressions: SSE responses remain bounded and resume using the real latest sequence, while native export includes its complete journal consistent with its snapshot. No rendering behavior or wire-schema change is authorized by this repair.

Input shape:

```python
body = {
    "path": "/allowed/generated.mov",
    "name": "Floating ingredients - reviewed candidate",
    "source_media_id": "m-source",
    "source_sha256": "a" * 64,
    "source_start_s": 1.0,
    "source_end_s": 7.0,
    "output_source_space": "rec709",
    "provider": "chatcut",
    "model": "seedance-2-5",
    "model_version": "provider-not-reported",
    "job_id": "generation-123",
    "prompt": "Edit the source by adding floating ingredients.",
    "settings": {"taskMode": "edit", "resolution": "720p", "outputFormat": "mov"},
    "cost": {"amount": 6.0, "unit": "credits", "status": "reported"},
    "rights_evidence": "CC BY 3.0; attribution stored with source",
    "review": {
        "reviewer": "local-operator",
        "decision": "approved",
        "notes": "First, middle and last frames compared; action retained.",
        "preserved": {"people": True, "action": True, "camera_motion": True,
                      "geometry": True, "text_logos": True},
        "audio": "reviewed"
    }
}
```

Name is optional; all other fields are required. `cost.amount` may be null only when status is `unknown`; do not invent free generation. Unknown final charge is retained honestly. `audio` is `reviewed` or `silent_source`; the latter is an operator assertion, not automated silence detection. These are explicit operator attestations, not automatic visual QA.

`output_source_space` is a required operator-declared value from the existing `COLOR_SPACES` vocabulary. Validate and retain it in lineage and the generated MediaItem; never inherit the original capture encoding. Reject absent or unsupported values before mutation. The review notes should identify the basis for the output encoding. A Rec.709 candidate from an Apple Log source must be imported as Rec.709 without changing the original source's encoding or bytes. This field declares encoding, not a conversion or proof of provider color fidelity.

Validate unknown/missing fields, nonempty bounded strings, strict finite numeric values (reject booleans), lowercase SHA-256, bounded JSON settings, all required true preservation checks, `decision == approved`, and source range inside registered source duration. Only unchanged-duration augmentation is supported: output duration must match source span within one output frame. Reject time changes rather than transferring anchors. Output aspect ratio must match source within rounding tolerance (relative 1%); resolution/fps can differ and are recorded. The full decoded media must be valid, with finite bounded duration and normal video dimensions, before import. Use bounded FFmpeg execution and reject missing/undecodable output. Don't make a source file's mere audio-stream presence mean its audio is audible.

Resolve both source and output against allowed roots before reading, reject identical source/output paths or hashes, and rehash source against registered and supplied hashes. Preserve source hashes before/after candidate verification. Record source identity/range, provider/model/version/job, prompt/settings/cost, rights/review, candidate hash and actual probe under IMPORT_MEDIA operation metadata `vfx_lineage`. Generated bytes live in the existing project library, with a verified hash; don't depend on a temporary provider download path. Copy once without overwriting and remove only newly-created partial output on failure. Build no proxy for this slice. Reuse current service/journal; preserve unrelated changes and reject finalized projects without partial import.

Final-review requirement: file extensions do not establish self-contained media.
Restrict supported demuxers before FFprobe/FFmpeg can follow references; a
renamed concat/playlist manifest must not read referenced files outside allowed
roots or be copied as if it were a complete video. Test the real API with a
disguised relative-reference manifest and outside-root symlinked payload. Reject
without state/journal/library changes; do not collect or resolve linked media.

- [x] Write failing tests before implementation. Use real API, reducer, SQLite and tiny locally generated FFmpeg video fixtures. External generation is represented only by clearly labeled job metadata; no fake cloud success.

```python
result = api.post("/api/editor/projects/demo/vfx/derivatives", body)
assert result["status"] == "reviewed_derivative"
assert result["placed"] is False
assert len(service.state("demo").timeline.tracks) == 0
assert file_digest(original) == original_digest
assert result["lineage"]["output_sha256"] == file_digest(candidate)
```

- [x] Run `.venv/bin/python -m unittest tests.editor.test_vfx -v`; record expected failing behavior before implementation.
- [x] Implement strict validation and intake through the existing operation path. Include tests for unapproved/missing preservation review, unknown charge, invalid ranges/NaN/bool, mismatched or modified source, path escape/symlink, identical source, wrong duration/aspect, corrupt output, duplicate replay and conflicting lineage. Rejected requests leave state and library unchanged. An ordinary prior import of identical bytes must not acquire invented VFX provenance.
- [x] Verify a real in-process loopback HTTP request reaches the endpoint and persists lineage, then repeat with a reopened repository/service. Keep test servers on ephemeral loopback ports and clean them up. If candidate intake needs concurrency coordination, test simultaneous repeats without duplicate operations.
- [x] Run focused tests, full editor suite once, Ruff lint and format for changed Python files. Self-review. Commit only owned code/tests with no co-author. Write test evidence and concerns to the task report.

## Task 2: Qualify TAKE ONE assembly through its real editor path

**Scope:** The approved renderer-qualification stage, not a new renderer or a
claim that the full AI editor is implemented. Latest approval above supersedes
the historical constraint to leave a defective renderer untouched; narrow
reproduced fixes are permitted. All other Global constraints apply, except
the old publication ban. No generation or cloud calls are needed.

**Files:** Add `tests/editor/test_render_qualification.py`; if it improves
reproduction, add a thin `tests/editor/run_render_qualification.py` runner.
Only fix a reproduced defect in the existing `render/ffmpeg.py`, `compile.py`,
or render executor/job code. Do not restructure unrelated modules. Controller
owns existing dirty README/plan updates; do not commit those in this task.

**Interfaces:** Use `EditorAPI`, `EditorService`, `ProjectRepository`, actual
operations and the existing render job/export path. Follow
`tests/editor/run_milestone1.py`, `tests/editor/test_vfx.py`, and
`docs/editor/render-engine.md`. No direct FFmpeg replacement for the product
render path. FFmpeg can generate fixtures and decode results for measurement.
Use temporary projects, local media and loopback only; no robot or user DB.

- [x] First reproduce end to end with synthetic red/blue source clips carrying
  distinct 440/880 Hz audio and a separate 660 Hz bed. Use four unequal edit
  spans of 1.5, 2.5, 2.0 and 3.0 seconds at 30 fps. Vary source in-points.
  Render through the product API/jobs, not a hand-authored output filter.
- [x] Measure decoded output: 270 frames / 9 seconds; hard cuts exactly at
  frames `[45, 120, 180]`; source-interior RGB mean absolute error `< 3` out of
  255 with neutral correction/no creative look. State source and output color
  encodings explicitly, test tagged 601/709 sources, and compare to a properly
  decoded reference. Do not silently widen these gates.
- [x] Exercise an existing dissolve and original embedded sound plus a timed
  bed/fades. Confirm the mixed picture is unchanged from the same edit without
  bed, embedded source frequencies survive, bed is absent outside its window,
  and fades are monotonic. Compare timestamps/frame samples, not just file
  existence. Retain the same `< 0.1` RGB mean error for audio-only changes and
  the prior bed-amplitude criteria: `< 0.001` outside, `> 0.02` inside.
- [x] Verify repeat render/cache, undo and replay after repository/service
  reload, master/preview distinction and unchanged original SHA-256s. Add a
  fractional-duration/VFR source case and explicitly report any remaining
  frame quantization limit; do not claim exact VFR identity from a CFR test.
- [x] For each observed bug: save the failing test/output, implement the
  smallest existing-path fix, then rerun the failed case. If tests already
  pass, record qualification rather than inventing a production change.
- [x] Run focused new tests, the complete editor tests once, scoped Ruff and
  diff checks. Retain test reports outside Git and synthetic results in a
  temporary/Movies qualification directory. No private footage committed.
- [x] Self-review, commit only the task's code/tests, and report measured
  checks, exact commands and unresolved limitations to the controller for
  independent review. No push from the worker.

Reference measurements/fixtures: local
`~/Movies/takeone-qualification.FWzKht/isolate.py` and `isolation-results.json`.
Read them as historical measurement examples; do not mutate them. Tests must
generate their own small portable fixtures rather than depend on that folder.
Caesar's original Downloads specification is currently unavailable; existing
`docs/editor/architecture.md`, `render-engine.md`, this plan's intake contract
and the explicit user approval supply the scoped implementation requirements.

## Task 3: Separate, source-bound VFX proposals

**Scope:** After Task 2's review passes, add the proposal stage without changing
the existing auto-edit behavior. A proposal does not generate media, approve
preservation, edit the timeline or control hardware. Use the existing Responses
provider/model configuration, not a new model selection. Live execution is
explicit and unavailable without a configured key. No paid calls in this task.
This task's enumerated code changes supersede the historical blanket
unchanged-Director/renderer wording above for the shared transport seam only;
the renderer itself remains unchanged in Task 3. Use the actual model settings
already in `configs/director-planning.json`, not a new subscription or endpoint.

**Files:** Create `packages/takeone/editor/plan/vfx.py`,
`packages/takeone/editor/plan/vfx_provider.py`,
`packages/takeone/editor/vfx_planning.py`, and
`tests/editor/test_vfx_planning.py`. Extend `editor/api.py`, the existing
`jobs.py` pool and repository only for the proposal route and durable request
records. Register the new top-level `vfx_planning` module at layer 9 in
`tests/editor/test_layering.py`, preserving every existing boundary assertion.
A small
extraction inside `director/provider.py` may reuse its existing strict Responses
request/transport validation without copying that implementation; preserve all
director behavior and cover it with its existing tests. Controller owns docs.
Keep VFX runtime instructions separate from the director's scene/script skills.

**Interfaces:** Add `POST /api/editor/projects/{id}/vfx/plan` with
`request_id` (UUID), `expected_version` (integer), `script` (bounded string),
and `sources` (1-12 entries). Each source names registered `media_id`,
`source_sha256`, `source_start_s`, `source_end_s`, and `observations` containing
bounded, explicitly supplied visual facts with observation source attribution.
Use `observations: [{"source": "operator notes", "text": "One person waves in front of a couch."}]`;
source attribution is 1-120 characters and observation text 1-2000 characters,
with 1-12 observations per source. The script is 1-12000 characters.
Do not pass filesystem paths, audio, whole project documents or credentials to
the model. Metadata-only probes are not visual observations. No network call
may occur before identity, digest, version and range checks pass.

Long provider calls must run in the existing bounded job pool, not block the
HTTP request. POST returns a durable queued/running receipt with request ID;
`GET /api/editor/projects/{id}/vfx/plans/{request_id}` returns progress or the
terminal result. Identical completed POST retries may return that result.
The successful terminal document contains
`schema_version`, `status: "proposal"`, `request_id`, `project_version`,
`input_digest`, `provenance`, `proposals`, `generated: false`, `placed: false`.
One proposal per requested source: stable source identity/range, `decision`
(`none` or `augment`), `effect_start_s`/`effect_end_s` (source-relative seconds),
`prompt`, `protected_content` (people, action, camera motion, geometry,
text/logos and original audio), and short `reason`. An explicit `none` has
empty prompt and null effect times, not a speculative effect. Never add an
effect to every shot by default. Times of an augmentation lie within the
requested span and on the project frame grid. Reject unknown or duplicate
sources, fabricated hashes, unsupported fields, nonfinite/bool numbers,
missing protected content or altered source spans. Validation rejects instead
of silently clamping or changing the model's proposal.
Represent protected content as the exact six boolean keys `people`, `action`,
`camera_motion`, `geometry`, `text_logos`, `original_audio`, all true. These
are requirements for later generation/review, not attestation that generated
footage passed. Prompts are bounded to 4000 characters and reasons to 1000.

Use strict JSON schema and independent local validation. Instructions identify
input script/observations as untrusted creative data, preserve real filmed
performance and framing, describe additions rather than whole-shot replacement,
include the original audio lock, and choose `none` when information is lacking.
This stage reasons from supplied observations, not automatic vision. Do not
claim it viewed footage unless image inputs are actually implemented separately.

Reuse the existing configured model, deadline, request size, token prices and
budget bounds. Extract small task-independent request/provenance seams from
the existing adapter if needed, rather than copying its HTTP/error logic or
introducing a new framework. VFX provenance must identify VFX instructions and
input digests, not falsely cite the filming skills. Response refusals,
incomplete/malformed output and wrong model identity fail closed with sanitized
errors. No retries, tool calls or heuristic result mislabeled as AI.

Persist request identity, digest, conservative budget reservation and terminal
result in the repository's existing jobs table before/after the external call.
Same request ID and input returns the prior result without another paid call;
changed input with the same ID is a conflict. An interrupted/uncertain request
remains uncertain after restart and must not be automatically resubmitted.
Concurrent requests cannot exceed the configured project budget. Do not hold a
SQLite write transaction across the network call. Recheck project version and
source identity before exposing a usable proposal; stale results are not ready
for generation. No generic workflow engine or DB migration unless the existing
jobs columns demonstrably cannot hold these records.

- [x] Write a failing API test using an injected, explicitly labeled simulated
  provider with one augmented span and one `none` span of different durations.
  Assert source hashes, timeline, operations and original files are unchanged.

  ```python
  receipt = api.post(f"/api/editor/projects/{project_id}/vfx/plan", request)
  # Wait on the deterministic fixture's completion signal, with a timeout.
  result = api.get(f"/api/editor/projects/{project_id}/vfx/plans/{receipt['request_id']}")
  assert result["status"] == "proposal"
  assert result["generated"] is False and result["placed"] is False
  assert result["provenance"]["source"] == "simulated_provider"
  assert result["proposals"][1]["decision"] == "none"
  ```

- [x] Run `.venv/bin/python -m unittest tests.editor.test_vfx_planning -v`
  and record the missing-route failure before implementation.
- [x] Implement the route, separate proposal instructions/schema/validator and
  shared existing transport seam. Require injected provider evidence to remain
  simulated; default missing-key behavior returns unavailable, not fake AI.
- [x] Test invalid requests/responses before mutation, refusal/timeout,
  input-instruction injection as data, stale project/source, missing key,
  concurrent repeats, budget exhaustion and retry/reload without duplicate
  network submissions. Test a complete real loopback request and persisted
  reopen using synthetic media and a deterministic provider fixture.
- [x] Run focused tests plus the affected director-provider tests and complete
  editor suite once. Ruff/diff checks and self-review. Commit only task-owned
  code/tests; report red/green evidence and untested live-model behavior.

A later integration task connects validated proposals to the existing ChatCut
generation receipts and reviewed derivative intake, preserving explicit review
and original audio. It depends on this contract and on Task 2 qualification;
neither proposals nor synthetic provider tests finish that integration.

Task 3 checkpoint: `427b271` plus freshness fix `3ed70cd`, scoped independent
re-review PASS. Fresh full verification at `3ed70cd`: 1043 product tests,
29 simulation tests, 295 browser tests, integrity and full lint/format pass.
The editor frontend's nine tests also pass. Live model/schema/billing behavior
and generation/review/placement remain unverified or unfinished. Publication
is a separate gate; this checkpoint does not mark the full AI editor complete.

## Controller work: real reference and access qualification

- [x] September 16: keep the paid plan unpurchased pending Basil's decision. September 17 supersedes this access blocker: Basil reports setup complete; pre-job UI shows 105 credits and the single authorized generation succeeds. No purchase was made by the agent.
- [x] Prepare one 6-second reference from licensed cooking source, preserving original files and attribution. Inspect beginning/middle/end before proposing exact prompt. Use direct FFmpeg, not a custom ops wrapper.
- [x] Submit exactly one authorized augmentation request through the official ChatCut connector after access is enabled. September 17: job `36be44fc50` completes. Connector exposes no quote; final charge remains unknown after browser credit-history timeout. No blind retry or second generation.
- [ ] Do not build the full automatic ChatCut adapter on unverified generation receipts. After real output, validate and review the result, then qualify timeline insertion/export before extending the production path.
- [x] Review the code task independently. Update existing editor README and old context CURRENT_STATE/ENVIRONMENT with actual evidence and remaining milestones. No claim that this bounded intake completes the full AI editor.

## Checkpoint evidence

Later September 17 cinematic follow-up: Basil reviewed the cooking proof and
requested researched human movie-style tests, conservatively and autonomously.
One licensed four-second actor source edit was submitted (`3f2e121836`), then
failed non-retryably with `input_video_real_person`. No output exists and the
second attempt was not submitted. Provider eligibility needs resolution before
further human-footage generation; do not disguise faces or blindly retry.
Ledger now verifies prior cooking charge 6.3 credits; new test has no visible
additional debit and 98.7 credits remain. Exact source, references, request and
failure receipt: `~/Movies/takeone-cinema-test.47zzRx/`. No production provider
switch or architecture change is selected. Full generation/integration gates
remain open. See editor README for sources and the next bounded decision.

September 17 update: raw generation fully decodes but fails preservation and
duration checks. It removes real food, adds sound and shortens 6 seconds to
5.708333 seconds. Do not approve intake or native replacement. A separately
labeled local composite isolates green scallions over the original as a rough
effect proof, not a new application renderer. Both composite/comparison decode
at 6 s / 180 frames; source hashes remain unchanged. Sampled visual QA complete;
Basil/team review is the next checkpoint before any second paid job. Details
and limitations: editor README and local `REVIEW-2026-09-17.md`. Full generation
qualification, automatic integration and native insertion/export remain open.
The no-paid-request restriction above describes the original code task;
Basil separately authorized this one paid operational test. No code, native
timeline, push, merge or external message changed during the media test.

Historical September 16 evidence:

Local implementation commits: `2281985`, `f86e4e4`, `a4abc2d`. Independent task
review and final scoped re-review pass. Final fix restricts demuxers before
probing/decoding, including a real outside-root access regression.
Parent verification: 166 editor tests in 42.691 seconds, 9 frontend tests,
frontend build, editor lint/format pass. Broader results and known fixture
failures are recorded in `docs/editor/README.md`; whole-branch readiness is not
claimed. No provider generation, cloud upload,
subscription purchase, push or merge. Real reference and unsubmitted request:
`~/Movies/takeone-vfx-proof.cC8MLC/`. Keep unfinished generation/integration gates
open; this is not the full approved AI editor.
