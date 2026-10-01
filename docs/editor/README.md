# TAKE ONE Editor — documentation

For importing computer videos, dragging shots into order and downloading the final MP4,
see [Manual editing](manual-editing.md).

## September 19 main integration preparation

The local `feat/editor-effects-flow` branch now incorporates team `main` at
`5384767` while preserving the reviewed effects workflow. This is an isolated
merge-preparation branch. It has not been pushed or merged into `main`.

The integration keeps the team's current neutral visual system and Record/iPhone
workflow, retains the September 14 recording handoff as historical context, and
preserves the legacy project-intent fallback alongside journaled intent for new
projects. Deterministic movement references use the committed Windows capture by
default and the independently recorded macOS arm64 capture on that platform.
No tolerance was relaxed.

Live browser acceptance found and fixed two UI seams introduced by combining the
four-stage navigation with the earlier editor shell. The stage rail now derives
equal columns without assuming eight stages. Embedded activity no longer scrolls
the Studio panel past its controls on load. Desktop and 390 px checks cover source
selection, a simulated effect proposal, the explicit reviewed-import gate,
project switching, scroll access and horizontal overflow. These checks use
synthetic local media and do not qualify provider output, hardware, Windows, or
real-footage preservation.

Fresh verification at the integration checkpoint passed 1,157 product tests,
29 simulation tests, 331 rehearsal browser tests, rehearsal syntax checks, the
repository integrity audit, Ruff lint and Ruff formatting. At that checkpoint,
the editor-specific gate separately passed 24 frontend tests, its TypeScript/Vite
production build and an npm audit with zero findings. These counts predate the
final source-review tightening described in the current workflow below.

## September 18 post-gate source selection follow-up

Local no-mistakes run `01M2TJF99Q3NVPZ5H9B3RRHGZ8` returned `passed` at
`6eaad57b`, with rebase, push, PR and hosted CI skipped. Guarded custody recovery
retained both gate commits. The run still reported the actionable re-review
finding `vfx-selection-exclusivity-stream-ingest`; its pass is not proof that
this issue was resolved. Gate browser evidence separately demonstrates reviewed
import-only, explicit placement, 210 frames over seven seconds, source sound,
preserved hashes, unequal 2/3/2-second shots, undo and failure states.

The follow-up reproduced the remaining issue through Chrome and the live local
HTTP/SSE path: selecting a three-second Media item, then trimming another clip,
silently changed the effects source to that clip. Client state now distinguishes
explicit operator selection from automatic edit focus. Streamed operations keep
an explicit Media or timeline choice; automatic focus still follows edits when
no explicit choice exists. Opening a project clears both source selections and
resets the playhead, which also fixes the observed old timecode carried into an
empty film. No product architecture or provider changed.

The regression tests failed before their fixes. Pre-gate follow-up checks passed
all 23 frontend tests, TypeScript/Vite build, dependency audit with zero findings,
and Chrome checks for both explicit source types and in-app project switching.
A fresh simulated proposal also remained stale after undo and a divergent edit
reused its numeric version; the browser did not offer derivative import.
Synthetic trim operations were undone back to the original five-second fixture.

The explicitly approved second no-mistakes run
`01M2V0BJ8714P64FRQ79BW1R6Z` then reproduced one more project-switch race in its
local test phase: an in-flight poll could restore the prior project's completed
preview after the client cleared project-scoped state. That revision accepted
poll results only for the currently open project. The final source review extends
the same rule to project inspection, SSE callbacks, job polling, upload/auto-edit,
render/export and undo responses, so in-flight work cannot repopulate the shared
interface after a project switch. Fresh Node 24 checks at the earlier revision
passed all 24 frontend tests, and Chrome showed the empty project with no prior
preview, selected source or playhead offset. That documentation/lint pass also
confirmed the TypeScript check, zero-advisory dependency audit, and the complete
configured Ruff check/format scope. No post-follow-up full repository suite is
claimed; the larger suite totals below remain historical evidence from before
this follow-up. Rebase, push, PR and hosted CI remain skipped, and everything
remains local and unmerged. Live AI quality, generated foreground preservation
and Windows integration remain unqualified.

## September 18 final effects review fixes

Final source review found and corrected four integration defects without changing
providers or the editor architecture. Timeline and Media selections are now
exclusive, so the latest explicit operator choice supplies the proposal source
and its real range. Ordinary duplicate uploads remove only their newly stored,
unregistered copy under the project edit lock. A committed upload remains on
disk if event publication fails, and exclusive file creation prevents concurrent
uploads from overwriting a project original.

Proposal review now performs a fresh server GET when the project snapshot
changes, before opening review, and again before upload. Reviewed intake treats
`settings.proposal_request_id` as an optional binding: when present, the server
requires the persisted proposal to remain fresh and to contain exactly the same
augment source identity and range. Standalone/manual derivative intake remains
supported without an invented proposal link. An unchanged retry of an already
registered receipt still succeeds after later project edits.

Embedded source sound now remains aligned when its measured stream begins after
the picture or ends before it, including through retiming, hard cuts and
transitions. The exact compiler contract is owned by the
[render-engine documentation](render-engine.md#speed-curves). Regression cases
cover a four-second picture whose 440 Hz stream occupies seconds one through
three, followed by a separate 660 Hz shot, plus trimmed 2x speed and dissolve
paths with measured tone windows and frame counts. This is synthetic local
evidence, not hardware, provider-quality or Windows qualification.

## September 18 browser effects workflow

The isolated `feat/editor-effects-flow` branch connects the existing source-bound
proposal and reviewed-intake APIs to **Studio > AI > AI effects**. It does not
replace the existing automatic edit, select a new provider, or generate media
automatically. Keep the team no-merge hold in effect.

1. Select a timeline clip (its actual source range) or a source in Media. Supply
   the scene script/creative brief and observations of the footage.
2. Request effect ideas. The browser saves the request ID before submission;
   refresh checks that same request instead of starting another generation.
   Queued, running, unavailable, failed, uncertain and stale states remain
   distinct. A proposal can also recommend keeping the shot natural.
3. Copy an augmentation prompt and generate externally through the existing
   ChatCut workflow. Planning alone neither generates nor places a clip.
4. Choose **Import generated clip**. Play the original source span from its start
   through its end and the candidate from its start through its end. Preservation
   attestations remain disabled until both complete. Seeking invalidates that
   media's playback proof; a playback error or a different candidate resets the
   comparison and clears the checks. Inspect the original sound, then explicitly
   attest the five preservation checks and audio check. None is checked
   automatically. Record the actual provider, model, job, prompt, rights and
   review evidence. Unknown charge/version remain unknown, not invented
   estimates. If original audio needs restoration, prepare it using the recipe
   below before review.
5. **Approve and import** runs the restricted verifier and imports a reviewed
   copy into Media only. **Place on timeline** is a separate existing action,
   followed by preview/export/undo. Neither the upload nor the proposal silently
   replaces source footage. Changed project versions block stale review.

The new local multipart route is
`POST /api/editor/projects/{project_id}/vfx/derivatives/upload`: exactly one
`file` and one JSON `metadata` field. Metadata has the existing derivative
contract without `path` (optional `name`); the server chooses a private staging
path and calls the existing intake. Success/failure remove upload staging;
retries reuse matching verified bytes/lineage. Supplied paths, duplicate files,
incomplete review and incompatible media are rejected. Existing JSON intake
and ordinary media upload remain separate supported paths.

Actual Chrome acceptance used synthetic two- and three-second sources and a
two-second FFmpeg candidate, with an explicitly simulated proposal provider.
Refresh during planning produced one provider call. Review was blocked until
playback and explicit checks; import did not change the five-second timeline.
Separate placement produced a seven-second, 210-frame master with shot lengths
2/3/2 seconds, the yellow accent present only during its interval, and measured
440/660/440 Hz source tones (amplitudes above 0.124). Undo restored five seconds.
Original/candidate hashes and proposal lineage matched. Missing-provider UI and
incompatible-duration warnings were checked without cloud calls. The editor
and review dialog fit a 390 x 844 viewport without horizontal overflow.
Local evidence is outside Git at `/tmp/takeone-effects-browser.bdQlJs/`.
These fixtures prove wiring, not AI quality or preservation of real people.

Browser testing also reproduced two existing undo defects. Starting briefs
were stored outside the journal, causing reload rejection and disappearing
after undo. New projects now journal their starting intent atomically with
creation using the existing `SET_INTENT` operation. Unrelated undo/replay/reload
retain it; an explicit undo of that intent operation still removes it. Existing
inconsistent journals are not silently repaired. The browser now resets its
journal cursor and removes undone activity on a whole-state replacement, so a
new operation at a reused sequence is no longer ignored.

Editor development requires Node 22.12+ in the 22 release line or Node 24+;
Node 24 is recommended. The existing Vite/Vitest tools were updated to fix
observed dependency advisories, without changing React or runtime architecture.
Build/tests and dependency audit run under an ephemeral Node 24.21.0 here;
no global runtime change is required. Fresh checks pass 1,083 product tests,
29 simulation tests, 303 rehearsal browser tests and 17 editor frontend tests,
plus build, preservation/integrity audit, lint and format. The repository
verifier initially reported missing declared Three.js dependencies in this
worktree; installing the unchanged rehearsal lockfile and rerunning its
browser tests/syntax check resolved that setup failure. The original verifier
report retains its nonzero exit instead of being rewritten as a passing run;
the successful recheck is recorded alongside it. No tested source changed.
The single requested local no-mistakes gate follows these checks.
Live planning quality, actual externally generated preservation, Windows
acceptance and automatic external generation remain unqualified. No paid
generation, private-footage upload, hardware operation or merge was performed.

## September 17 measured audio bounds and probe resilience

The isolated handoff gate completed locally at `32520883`, with rebase, push,
PR and CI skipped. It added audio validation and cumulative read-only ChatCut
probe limits. Re-review found that video duration was not sufficient evidence
of audio duration. A real synthetic HTTP import/operation/export reproduced a
silent advertised tail: four-second video, two-second audio, accepted source
span 1-3 seconds. Before/after evidence is local at
`/tmp/takeone-audio-stream-repro.mng4s1/`; the corrected path rejects that span
with HTTP 409 before persisting it.

Follow-up changes record optional measured first-audio-stream start and duration
in ordinary and protected derivative imports. New music/SFX selections must
fit both the asset and actual audio stream, and unknown timing is rejected.
Historical probes omit absent fields, so older journals still load/replay;
an unchanged legacy derivative retry retains its original receipt rather than
rewriting provenance with newly available timing. Import originals into a new
project to obtain measured timing for new audio selections from legacy media.
Files whose stream timing cannot be measured remain usable as video, but are
not qualified for new standalone music/SFX selections.

The probe's cumulative limits cover discovery and both consistency scans:
1,000 pages, 10,000 entries/inspections and 8 MiB of incoming data. Serialized
reports must fit the same 8 MiB prior-report limit. These are diagnostics,
not generation controls. No provider, filming skills, hardware or dependency
configuration changed. Narrow reproduced editor fixes are within Basil's
standing approval; the earlier Ruff-only criterion applied to reference
reconciliation, not to all subsequent fixes. Verification/re-review of this
follow-up is recorded separately from the completed first gate. Fresh full
editor verification passes 215 tests with ResourceWarnings treated as errors;
the repository verifier's Python lint/format scope (`packages/takeone`, `tests`,
`scripts`) passes. Independent read-only re-review reports
no remaining findings, including reviewed derivative audio selection and
unchanged legacy receipt retries. The audio fix is isolated on
`fix/editor-audio-stream-bounds`, based on the retained handoff branch.

## September 17 offline effects handoff rehearsal

The existing proposal, derivative-intake and rendering APIs now have one
combined offline rehearsal in `tests/editor/test_vfx_handoff.py`. It uses
synthetic media and an explicitly simulated provider. One two-second span
receives a visible temporary effect; the following three-second shot keeps
its original media. This rehearses integration; no cloud generation is called.

Run from this checkout:

```sh
PYTHONPATH="$PWD/packages" .venv/bin/python -W error::ResourceWarning -m unittest tests.editor.test_vfx_handoff -v
```

The test measures a 150-frame master, the cut at frame 60, visible effect
presence/removal, original source sound and absence of candidate sound. It also
checks repeat proposal requests, intake retry after repository reload, replay,
render cache, undo back to 60 frames and unchanged source/candidate hashes.
Mapping candidate audio deliberately makes its original-audio assertion fail.
A timed source-audio marker also makes an incorrect start offset fail.
At this rehearsal checkpoint, backend intake remained separate from explicit
timeline placement and from a browser review flow. The current operator workflow
is documented in [September 18 browser effects workflow](#september-18-browser-effects-workflow).

For a manually reviewed candidate, use the direct local preparation path
before submitting it to derivative intake. Example for the tested two-second
source span beginning at 0.5 seconds:

```sh
ffmpeg -hide_banner -nostdin -loglevel error -n \
  -i candidate.mp4 -ss 0.5 -i original.mp4 \
  -map 0:v:0 -map 1:a:0 -t 2 \
  -c:v copy -c:a aac candidate-original-audio.mp4
```

Use a new output path. Video is copied; original audio is trimmed to the
declared source span and encoded as AAC. For an actually silent source, omit
the second input and use `-map 0:v:0 -an`; an audio-stream presence flag does
not prove audible speech or sound. Decode and review the prepared file before
attesting preservation. This recipe was measured on synthetic constant-rate
media; it is not a general time-warp or variable-frame-rate guarantee.

Keep the raw candidate and record the local transform in intake `settings`,
including `input_candidate_sha256`, `original_source_sha256`,
`original_source_start_s`, `duration_s`, `discard_candidate_audio`,
`video_codec` and `audio_codec`. Record the proposal request ID too. The
candidate hash and measured probe in lineage refer to the prepared output;
the transform records its raw input. This avoids labeling locally changed
bytes as the unmodified provider download. Preserve the actual provider job,
model, settings and final charge separately in the same lineage.

The existing one-frame duration and aspect-ratio gates still apply. An
ordinary placement of raw generated media plays that media's own audio;
intake does not automatically restore source audio. This preparation step
must happen before review/intake when retaining original sound is required.

Live planning quality, durable external-generation automation, validation of
real generated preservation and Windows acceptance remain unfinished.
The rehearsal stays on the separate local `test/editor-vfx-handoff` branch;
the measured-stream follow-up uses `fix/editor-audio-stream-bounds`. Keep the
team no-merge hold and isolated branches in effect.

## September 17 isolation and verification follow-up

Team instruction: do not merge. The renderer/intake baseline is draft
[PR #4](https://github.com/Zwc-11/TakeOne/pull/4); the proposal backend is draft
[PR #5](https://github.com/Zwc-11/TakeOne/pull/5), published at `4967dc0`.
Neither has auto-merge enabled. The upstream-verification follow-up used
`fix/editor-upstream-verification`, based on that exact published proposal head.
The older local proposal history is retained, not reset after its guarded
sync correctly refused a divergent history. Main is unchanged by this work.

The pipeline repaired atomic proposal startup, sanitized source-file errors,
and restored the shared production-design schema import. Focused proposal and
production-design checks pass; live model calls remain unverified. No cloud
generation or hardware test was performed in this follow-up.

Latest main `da1268e` intentionally updates light calibration and the Windows
movement-reference inputs. The previous Mac reference therefore fails its
input-hash guard. An independent capture from clean exact upstream `da1268e`
matches all 84 feature-output hashes (28 frames, 28 joint samples, 28 cart
schedules). The new versioned Mac fixture is
`tests/fixtures/legacy-movement-hashes-macos-arm64-da1268e.json`, SHA-256
`bbbfe14924b7dd514123c5b37f469680df08c8c0731a45b7e89979522e78e095`.
The previous Mac fixture, current Windows fixture and calibration are unchanged.
Input, Python and dependency guards remain exact. This is numeric regression
evidence, not cross-platform bit identity or physical qualification.
Local provenance and comparisons: `/tmp/takeone-da1268e-evidence.FpVVZX/`.

The follow-up also restores legacy-scene inventory coverage omitted by rebase
and mechanically formats two inherited Python files. The failing Mac-reference
check now passes alongside all seven inventory tests; full Python lint and
format pass. Independent read-only review passes, including mutations that
break each actual frame/sample/cart regression assertion. Fresh full
verification at `e943dd7` passes 1068 product tests, 29 simulation tests,
303 browser tests, syntax, integrity and full lint/format. Reports are local
at `/tmp/takeone-editor-e943dd7-verification`. The editor frontend additionally
passes nine tests and its production build. This follow-up remains local.
The handoff test added above is a later scoped check; it is not included in
those 1068 product tests. Earlier counts apply only to their named revisions.

## September 17 source-bound VFX proposal backend

At this September 17 checkpoint, the separate proposal backend was implemented
and independently reviewed without a browser UI. A proposal did not submit
generation, approve preservation, place media or change the timeline. The
existing auto-edit path was unchanged. The current thin UI and reviewed import
handoff are documented in
[September 18 browser effects workflow](#september-18-browser-effects-workflow).
This checkpoint depended on the separately published PR #4 renderer/intake
baseline described below.

- `POST /api/editor/projects/{id}/vfx/plan` accepts a UUID `request_id`, current
  integer `expected_version`, `script` and 1-12 registered `sources`.
- Each source supplies `media_id`, exact `source_sha256`, `source_start_s`,
  `source_end_s` and attributed `observations`, for example
  `[{"source": "operator notes", "text": "The actor waves in front of the couch."}]`.
  These are supplied observations, not automatic footage analysis. Source range
  and effect times are seconds relative to the original media; augmentation
  times must also lie on the project frame grid.
- Poll `GET /api/editor/projects/{id}/vfx/plans/{request_id}`. A successful
  `proposal` contains one `augment` or explicit `none` decision per source,
  protected-content requirements and provenance. It always reports
  `generated: false` and `placed: false`.

Use the existing configured Responses provider and planning budget in
`configs/director-planning.json`. Live calls require a locally configured
`OPENAI_API_KEY`; never put a key in this repository or a request body. The
default missing-key result is `unavailable`, not simulated AI. Tests inject
clearly labeled `simulated_provider` evidence. Model input contains only the
script, attributed observations, source identities/ranges and frame rate, not
media/audio, local paths, the project snapshot or filming instructions.

Identical request retries reuse durable state. Changed input with the same ID
is a conflict. Stale project/source results are unusable; uncertain requests
are not retried automatically. Run one live editor OS process per project
database. Budget accounting retains the full conservative reservation for all
durable requests, including failures and uncertainty; it is not a claim about
the provider's final charge and there is no refund/reset endpoint in this slice.
The durable request and reservation commit before queue submission; no SQLite
transaction remains open across the provider call.

Source validation now sanitizes missing-file failures and rechecks the full
project snapshot after hashing and again during the atomic queued-to-running
transition. Edits after validation, including undo that restores a version
number with different contents, therefore make the request stale before the
provider call. The proposal/layering tests cover these races; the earlier
scoped independent re-review was clean.
Fresh whole-repository verification at `3ed70cd` passes 1043 product tests,
29 simulation tests, 295 rehearsal browser tests, source integrity and full
Python lint/format. The separate editor frontend passes its nine tests.
Reports are local at `/tmp/takeone-vfx-3ed70cd-verification`; reproduce with
`PYTHONPATH="$PWD/packages" .venv/bin/python scripts/verify.py --output-dir /tmp/takeone-verification`.
Those counts precede adoption of the separately published high-frame-rate fix.
After merging published baseline `1f832527`, all 202 editor tests pass with
ResourceWarnings treated as errors; full Python lint/format also passes.
At this checkpoint, live schema acceptance, prompt quality, billing, generation
receipts and the generation/review/placement workflow were unverified or
unfinished. See the current browser workflow above for the later manual
generation handoff and reviewed Media-only import. This proposal stage did not
modify either original.

## September 17 latest: reviewed assembly baseline, shipping checks pending

The baseline is published separately in [PR #4](https://github.com/Zwc-11/TakeOne/pull/4),
head `1f832527`. Its publishing review additionally fixed loss of native
120-fps landmarks before slow-motion retiming (`f994fb46`). Ten real-render
qualification cases pass. GitHub reports no configured checks, not green CI;
the exact baseline head passed 1018 product, 29 simulation and 295 browser
tests, integrity and full lint/format before main advanced. High-resolution optical-flow
interpolation remains a documented performance concern because spatial scaling
currently follows timing. No high-resolution throughput or Windows qualification
is claimed. The source-bound proposal backend is not included in PR #4.

Final review reproduced cumulative audio timing loss during genuinely varying
speed ramps and a valid authored ramp rejected by an internal control-point
reconstruction limit. Both are fixed in `bd8ffa3`, with independent scoped
review passing. Real API regressions measure internal sound events, following
cuts and exact final-frame counts. Audio errors are 0-21 ms in the synthetic
linear/ramp cases, within the unchanged one-frame gate. All 175 editor tests
pass; a separate parent rerun passes all nine export qualification tests.
This is not exhaustive speech, extreme-speed or Windows qualification.

Commit `fea7a19` fixes two other final-review cases: preview audio now comes
from original media instead of silent video proxies, and nine audible clips
render without exceeding graph input limits. Fresh verification on that commit
passes 1007 product tests, 29 simulation tests, 292 rehearsal browser tests,
JavaScript syntax, source-preservation checks and full Python lint/format.
These whole-repository counts precede the final retiming repair and latest
upstream merge. Fresh integrated shipping checks are still required.

Delivery uses `feat/editor-rendering-baseline` for the reviewed existing-path
fixes and `feat/editor-vfx-proposals` for unfinished proposal work. Latest main
`b615d77` is integrated in `8e5dc1b`, preserving Caesar's production-designer
updates and legacy scene acceptance. Focused design/schema tests, 295 rehearsal
browser tests, syntax and full Python lint/format pass after integration. Review
also reproduced fixed-object role collisions for long/unsafe IDs; the narrow
follow-up preserves actual object IDs and uses a reserved digest namespace
only for derived role names that cannot retain the ordinary spelling. Private
footage remains local. No new cloud generation or physical tests were run.

Basil approved keeping ChatCut for generated effects and qualifying TAKE ONE's
existing renderer for assembly/export. This supersedes the rendering-ownership
decision still described as open in the historical checkpoint below. Native
ChatCut export remains unqualified; the timing/color thresholds are unchanged.

Real editor operations, render jobs and exports now pass portable synthetic
qualification. Four unequal spans (1.5/2.5/2/3 seconds) render to 270 frames at
30 fps, with hard cuts exactly at frames 45/120/180. BT.601/709 source-reference
RGB errors are 1/0/1/0 out of 255, below the unchanged <3 gate. Master output is
explicitly BT.709. Cache/repeat, preview/master distinction, undo/replay/reload
and unchanged original hashes are covered.

The tests reproduced dropped audio and an audio-insensitive render cache. The
existing graph/compiler now retains source sound and timed/faded audio assets.
Independent review then caught lag after a dissolve. A failing timestamped
picture/tone regression drove matching audio overlaps, not an acceptance-gate
relaxation. The music bed is below 0.000001 outside its window, about 0.063
inside, with monotonic fade-in/out; sampled picture error from an audio-only
change is 0.0. Re-review passes. Commits: `23c0375`, `3c5ee69`.

Verification: 2 real-FFmpeg qualification tests pass with ResourceWarnings as
errors; all 168 editor tests pass (48.137 seconds, exit 0), scoped Ruff/format
and diff checks pass. Reproduce with
`.venv/bin/python -m unittest tests.editor.test_render_qualification -v`.
Synthetic evidence stays local under
`~/Movies/takeone-renderer-qualification-20260917-transition-sync/`.

Limits: VFR input is assembled into CFR output, not timestamp-identical VFR.
The audio bed fixture is an AV file because the existing importer requires a
video stream. Standalone-audio import, multi-video-track audio and ducking are
not qualified. Mac tests do not establish Windows or hardware readiness.
At this baseline checkpoint, the separate VFX planner and
generation/review/placement integration remained unfinished. No existing
generated personal clip was automatically approved. See the current browser
workflow above for the later integration boundary.

Delivery is split into reviewed commits. The earlier director PR #3 is draft
because incoming main `c5146d5` exposed a strict-schema regression after rebase.
The editor worktree now includes that main, the director repairs, mechanical
lint cleanup `69e26e8` and the reviewed schema repair `917c7ed`. The latter
passes 52 focused tests and preserves legacy scene acceptance. Full integrated
verification passes at the historical checkpoint above. Final retiming and
upstream integration still need combined shipping checks; no CI-green claim from an empty
GitHub check list. Private footage and generation outputs
stay outside Git. No further paid job was submitted during this code work.

## September 17 earlier: model/settings tests and export recheck

Basil approved proceeding with the bounded completion plan. Three new Omni
720p source edits completed, all using the original silent room clip rather
than chaining generated outputs. Each cost 2.65 credits: **7.95 total, 83.68
remaining**, confirmed in Credits history / Detail. The fourth allowed job was
not spent. No new account, subscription, private audio upload or public sharing.

| Case | Job | Observed result |
| --- | --- | --- |
| Repeat approved people prompt | `d66486cae1` | Two seated guests and correct image-right wave in reviewed samples; foreground details still rerendered. |
| Replace rear wall with city window | `166f92e952` | Background changes while couch/chair and broad performance remain recognizable in samples. |
| Timed background butterfly | `8c39aaee7a` | Localized effect and correct wave; butterfly remains visible at 5 s despite a requested complete fade-out by 5 s. Timing is not qualified. |

All three outputs fully decode at 1280x720, 24 fps, 144 frames, 6 seconds.
The source video is 5.950544 seconds, so these still exceed the existing
one-output-frame duration tolerance. They contain generated audio; separate
silent viewing copies remove audio without reencoding the video. Preserve the
original recording/audio for any later assembly. No derivative was approved
or inserted into TAKE ONE by this experiment.

Evidence, exact prompts/receipts and local-only media:
`~/Movies/takeone-vfx-selection.N40lMf/`. `REVIEW-four-way.mp4` compares the
source and three results. This is an FFmpeg review assembly, not a native
ChatCut export or the automatic editor. Source review timing is resampled to
24 fps and its end held about 49 ms to align panels; generated outputs are not
retimed. First/middle/end, wave moments and 12-sample sheets were reviewed,
not every frame certified as preserved.

**Model recommendation, not final selection:** retain Omni as the accessible
source-edit candidate, at 720p with the original video as `continueFrom`, a
targeted prompt, explicit protected performance and separate output review.
Do not interpret three varied examples on one source as a broad benchmark.
Seedance's tested real-person route remains refused. Runway Aleph 2 is a
research-only challenger: its official API pricing lists 28 Runway credits/s
at $0.01/credit (about $1.68 for a six-second base generation, before tax and
other operations). No account/access was purchased or tested. These are not
ChatCut credits. Sources: [Runway pricing](https://docs.dev.runwayml.com/guides/pricing/),
[Aleph editing guide](https://help.runwayml.com/hc/en-us/articles/52150503729171-Aleph-2-0-Prompting-Guide).

**Fresh native export blocker:** Desktop remains 0.3.16, bridge 0.1.6. The
existing read-only probe confirms the synthetic nine-second timeline still
matches its saved baseline. A fresh native export, task
`8c7e0590-b6d3-4545-87bb-7a447938570e`, fully decodes to 270 frames at 30 fps,
but hard cuts requested at 120 and 180 appear at 121 and 181. Interior source
RGB mean errors are 7.30, 7.61, 5.47 and 9.23 out of 255, above the unchanged
<3 threshold. First boundary has a dissolve and is not a hard-cut check.
Evidence: `native-before.json`, `native-recheck.json`, `native-cut-review.jpg`,
and `~/Movies/ChatCut/selection-N40lMf-native-recheck.mp4`.

No timeline adjustment, vendor patch or relaxed gate was made. The public
[release page](https://chatcut.io/docs/releases) lists an older version and
does not establish a remedy; do not downgrade on that basis. Completion now
requires a decision: obtain a supported native-export fix, or approve retaining
ChatCut for generation while qualifying the repo's existing renderer for final
assembly. The latter changes rendering ownership and has NOT been selected.
Automatic adapter, semantic VFX planner and full Windows acceptance remain open.

Fresh unchanged-code checks: 166 editor Python tests, 9 frontend tests,
TypeScript/Vite build, Ruff check and format across 63 editor/test files pass.
Fresh fetch leaves origin/main at `dffc505`; no new editor changes are present
in its five commits ahead of this worktree. No merge, push or team message.
Whole-repository inherited fixture failures are not claimed fixed by these checks.

## September 17 earlier: personal-footage background-people test

Basil provided a phone clip and approved autonomous completion of the proposed
test, including scoped cloud editing, not public sharing. Source is about
5.95 seconds, 848x478, with a visible hand wave. A silent video-stream-copy
reference preserved all decoded source pixels while excluding private audio
from upload. Originals and private media remain outside Git.

Two Gemini Omni jobs in project `4e2c743b-1d15-44db-b36e-e9382d8a4805`:

- `a61a4cac4b`: two seated background guests added, but the real subject's wave
  changed to the opposite arm. Rejected for action preservation.
- `011867f62c`: original source reused with an explicit image-right wave
  constraint. Two guests and correct wave side visible in reviewed samples.
  Selected as the better demo, not automatic preservation approval.

Checked first/middle/end, twelve output samples, 0.25-second wave comparisons,
full-size frames, file decode and source hashes. Broad action/framing is
recognizable, but face/hand details are rerendered. Both outputs are 6 s / 144
frames / 24 fps; source video is 5.950544 s, so the difference exceeds the current
one-output-frame duration tolerance. Do not weaken that check. Generated audio
is low-level but nonzero; standalone silent viewing copy removes it without
re-encoding video, verified by decoded-picture hashes. Original audio is not
part of this qualification.

Start with `~/Movies/takeone-people-test.3L6z0J/SHARE-before-after.mp4` (12 s)
or `COMPARE-side-by-side.mp4` (6 s). Raw outputs, original silent reference,
requests, receipts and detailed `REVIEW.md` are beside them. Review assemblies
are local FFmpeg, not native ChatCut exports. They resample the VFR source to
24 fps and hold its last frame about 0.05 s for aligned six-second panels;
that presentation padding does not prove original-duration preservation.
Labels identify generated additions. No clips were sent to the team.

Exact ledger: **2.65 credits each, 5.30 total, 91.63 remaining**. Two jobs done,
no further retries queued. No code/native timeline, subscription, architecture,
production derivative approval, push or merge changed. Other code test failures
and native-renderer defects remain open and were not retested by this experiment.

This now provides an actual background-people example, not just the portal.
Before reliable automation: evaluate another varied input, settle explicit
fractional-duration normalization and foreground review, and resolve authorized
Seedance access. Model selection is still open; one corrected demo is not
general preservation evidence. Personal test data needs separate approval for
any public publication.

## September 17 earlier: Gemini Omni background demo, preservation still open

Basil explicitly requested Gemini Omni research and a conservative background
edit, clarifying that filmed people must remain the basis of the project.
One approved Omni source edit through existing ChatCut access completed:
job `5d463df262`, output asset `b9432d72-036d-46d2-bdd4-59318cefdb53`, project
`47cc3373-4929-4d6d-8807-4ab56bc34f7f`. Service reports
`gemini-omni-1.1-flash-preview`; identity is not independently authenticated.

The licensed four-second *Tears of Steel* shot now has a visible cyan doorway
portal overlooking a futuristic city. This is a usable effect demonstration,
not preservation approval. Nine source-time samples, first/middle/end through
asset inspection, full-resolution middle frames and full decode were checked.
The actors' broad movements remain recognizable in samples, but the output
reframes 1920x800 (2.4:1) to 1280x720 (16:9), losing side content. At 2 s the
source woman is visible at left but mostly cropped out of the generated view.
Faces/small details are rerendered. Nonzero AAC audio was also added to the
silent source (mean -51.6 dBFS, peak -28.3 dBFS). Video timing matches 4 seconds,
24 fps, 96 frames; container duration is 4.01 seconds from audio.

Start here: `~/Movies/takeone-cinema-test.47zzRx/TEAM-DEMO-before-after.mp4`.
This eight-second, 192-frame silent review shows the entire original followed
by the full generated frame, with labels and attribution. The standalone
silent viewing copy uses video stream copy, with decoded-video hashes matching
the untouched raw output. No masking rescue, hidden reframing or AI upscale.
This comparison is a one-off local FFmpeg assembly, not a native ChatCut export.
Share `ATTRIBUTION.md` with it. Original and reference hashes are unchanged.
Raw output, request, receipt, contact sheet, source and review are beside it.

Credits history confirms **1.77 credits spent, 96.93 remaining**. Two cinematic
jobs total, including the earlier refused Seedance job; no third job or ongoing
generation. No code/native timeline, provider purchase, production architecture,
derivative approval, push, merge or external message changed. Existing native
export/color issues and whole-branch failures remain unresolved, not retested
by this media/docs experiment.

### Research and next acceptance gate

- [Google Omni](https://ai.google.dev/gemini-api/docs/omni) documents uploaded
  video editing and background swaps, with regional/input restrictions and
  upscaled 1080p/4K outputs. ChatCut's interface is narrower than upstream.
- [Higgsfield's real-footage course](https://higgsfield.ai/academy/courses/ai-vfx-real-footage)
  covers preserving filmed performance while changing worlds/adding creatures.
  This validates the workflow category, not our account access or output quality.
- [BytePlus's advanced creation page](https://www.byteplus.com/en/activity/seedance2-0-security)
  is indexed with real-person verification/API integration for Seedance 2.0.
  Full page retrieval was unavailable. Do not assume that entitlement exists
  in ChatCut's 2.5 route; no filter evasion or repeat refused request was used.
- [Kling VIDEO 3.0 Omni](https://kling.ai/feature/video-background-remover) and
  [Runway Aleph 2.0](https://help.runwayml.com/hc/en-us/articles/52150503729171-Aleph-2-0-Prompting-Guide)
  document targeted edits of uploaded footage. Research alternatives only,
  not purchased/tested. Kling Omni and Gemini Omni are different models.

**Adding background people remains untested.** Proposed next bounded test:
a consented native-16:9 single-person clip with one or two fictional extras
behind them, no foreground crossing initially. Assess face/action/camera and
extra-person anatomy, timing, lighting and occlusion. Native 16:9 is not a
verified fix for this observed crop. A portal demo cannot qualify this gate.
Do not weaken the reviewed-derivative intake or claim the AI editor is finished.

## September 17 earlier: cinematic Seedance human-footage test blocked

Basil reviewed the cooking overlay, found it unsuitable for judging cinematic
quality and authorized research plus a couple of conservative autonomous tests.
The operational limit was two short sequential jobs with a 20-credit target
ceiling and billing reconciliation between attempts, not an unlimited run.

Research from [Higgsfield's footage VFX guide](https://higgsfield.ai/blog/vfx_4k)
informed a better source-video test: preserve performance and camera explicitly,
add one timed background effect, match lighting/depth, and use an actual source
frame as an identity reference. Its [AI/VFX breakdown](https://higgsfield.ai/blog/ai-vs-vfx)
mixes source-video work with fully generated scenes; do not conflate them.
The supplied Instagram reel remains inaccessible, so only Basil's description
and caption are known. Higher resolution is not a preservation guarantee.

Prepared a four-second excerpt [174,178) of *Tears of Steel*: two real actors
in a warm interior, with a camera pan and clear faces. Source is from Blender's
official download, CC BY 3.0 per its [license statement](https://mango.blender.org/sharing/).
Audio is omitted because a separate soundtrack NoDerivs notice exists.
Source film already has grading/VFX; those are not this experiment's work.
Reference is 1920x800, 24 fps, 96 frames, exactly 4 s; full decode and 0.5-second
sample inspection pass. Imported video and source-frame image into isolated
Desktop project `47cc3373-4929-4d6d-8807-4ab56bc34f7f`.

Submitted one 720p Seedance source edit requesting a cyan energy ring behind
the actors in the doorway. Job `3f2e121836` reached terminal failure:
`InputVideoSensitiveContentDetected.PrivacyInformation`, mapped to
`input_video_real_person`, HTTP 400, `retryable: false`. The error identifies
the video input. **No edited human-footage result exists.** Do not call this a
failed visual-quality comparison or infer that a new prompt/1080p fixes it.
Do not resubmit the same clip, disguise real people or remove references to
evade the check. The planned second generation was not spent.

Credits history Detail now confirms the earlier cooking job cost **6.3 credits**;
balance was **98.7** before the new test and remains **98.7** after its failure,
with no additional debit visible. This is an observed ledger state, not a
general refund guarantee. Read-only browser DOM controls worked after the
Playwright snapshot connection repeatedly timed out.

Local source, attribution, exact request, failure receipt and research:
`~/Movies/takeone-cinema-test.47zzRx/`. Nothing sent to the team, pushed or merged;
no native timeline or production code changed. Reviewed-derivative intake is
not weakened. This batch is blocked, not complete and not running unattended.

Next choice requires an eligible live-action workflow: ask the provider for
clarification, or approve a bounded test of another documented source-edit model.
[ChatCut's model docs](https://chatcut.io/docs/video-generation-models) list Gemini
Omni, but its compatibility with this input and quality are not verified. No
model/provider switch or new account purchase is selected. [Google's Omni docs](https://ai.google.dev/gemini-api/docs/omni)
also identify 1080p/4K as upscaled, not native detail. Keep this distinction in
any quality comparison. Do not treat a marketing demo as account eligibility.

## September 17 paid generation result and effect proof (earlier checkpoint)

Basil enabled paid access and authorized continuing the bounded test. Exactly
one real source-edit job completed through the official ChatCut Desktop
connector: `36be44fc50` (prefix), result asset
`9d5beeca-5f86-471e-ab07-c9feb6dd6038`. Service-reported model is
`doubao-seedance-2-5-260628`, not independently authenticated identity.
The pre-job UI balance was 105 credits. Later Credits history verification
establishes a 6.3-credit debit and 98.7 remaining; the initial check timed out.

**Raw output rejected:** it removes real green batter/food, adds non-silent
audio to a silent source, and returns 5.708333 seconds instead of 6.0 seconds.
It fully decodes, but successful generation is not preservation acceptance.
Do not approve it for the derivative-intake route or substitute it on a timeline.

A separate one-off local composite isolates generated green scallions in a
small upper-left region over the original video. The original action and
six-second timing remain the base; generated audio is omitted. This is a rough
agent-assisted proof, not a generalized mask/tracker, production integration,
native ChatCut export or a replacement application renderer. Hard matte edges,
possible green-pixel residue and unqualified colorimetry remain limitations.

Local deliverables, provenance, prompt, receipt, attribution and review:
`~/Movies/takeone-vfx-proof.cC8MLC/`.

- `before-after-ai-overlay.mp4`: labeled original/composite, 6 s, 1280x440.
- `cooking-ai-overlay-review.mp4`: standalone 720p composite.
- `cooking-reference-72s-78s.mp4`: original six-second reference.
- `REVIEW-2026-09-17.md`: raw rejection, exact compositing command and limitations.
- Keep `ATTRIBUTION.md` with shared footage. This is licensed third-party
  footage, not filmed by the robot.

Both deliverables fully decode as H.264/yuv420p, 30 fps, 180 frames, exactly
6 seconds, no audio. Source/working/reference hashes are unchanged. Fresh
original/composite comparisons, a full comparison frame at 2 s and composite
samples every 0.5 s were inspected. This is sampled visual QA, not continuous
playback certification. Source is silent, so real sound is still unqualified.

Next checkpoint: Basil/team visual review before a second paid generation.
The raw edit path is **not preservation-qualified**. The composite is not yet
an approved production derivative. Full script-informed VFX planning, provider
recovery, timeline/UI integration, qualified native export, real sound, Windows
and repeated end-to-end acceptance remain open. Prior native timing/color and
root fixture failures below are not resolved by this media test.

No production code or native timeline changed, and nothing was sent, pushed or
merged in this batch. Earlier test counts below are historical, not rerun today.

## September 16 generative augmentation implementation (historical checkpoint)

Basil approved the revised direction after supplying an Instagram reference:
add visible objects/effects to filmed footage, retaining real performance and
camera movement. The reel was unavailable; its caption and Basil's description
are the reference, not verified generation evidence. The earlier basic montage
does **not** demonstrate this capability. Making a person trip rewrites their
action and is outside the first augmentation test.

Keep ChatCut and qualify its exposed Seedance source-edit path before building
the automatic provider adapter. The approved full workflow is: visible effect
proof, separate script-informed VFX planning, existing-app integration, then
repeated end-to-end tests. Caesar's scene scripting remains separate; his
existing Director skills are not silently rewritten as an effects planner.

Current bounded implementation plan:
[Generative VFX intake](../superpowers/plans/2026-09-16-generative-vfx-intake.md).
It adds reviewed-derivative intake to the existing editor API/journal. It does
not replace the renderer, add a new app, call a model, or silently substitute
the generated clip on a timeline. Review fields are operator attestations,
not automated proof that people/action/camera motion were preserved.

### Implemented backend slice

`POST /api/editor/projects/{project_id}/vfx/derivatives` accepts a local output,
registered source identity/range, generation provenance/cost, rights evidence,
explicit output color space and an approved preservation review. See the linked
plan for the exact body and [test_vfx.py](../../tests/editor/test_vfx.py) for
executable offline examples. It verifies hashes, bounded full decode, duration
and aspect ratio, then stores a separate verified media copy and journals its
lineage. Its response says `reviewed_derivative` and `placed: false`.
Source and output inspection restrict demuxers before opening media: renamed
playlists cannot read linked files or enter the library as incomplete videos.
Real tests include an outside-root reference-access sentinel and common
self-contained MP4/MOV, MKV/WebM, AVI and MPEG container fixtures.

Identical retries reuse the import, including after reload; conflicting or
missing provenance, changed sources, corrupt media and unapproved reviews fail.
Output color encoding is declared independently of original capture encoding.
Neither a prompt nor successful decode is automatic preservation/color QA.
The existing UI, heuristic planner and render engine are unchanged. This route
is not an automatic generator, VFX planner or timeline replacement command.

Review also exposed and repaired an existing 10,000-operation read limit in
internal replay, undo, duplicate lookup, SSE sequence detection and native
project export. Internal reads are complete; HTTP pages and SSE remain bounded.
Native export here means project JSON, not a newly qualified rendered movie.

Fresh checks after the fixes: **166 editor tests pass**, including 31 new
real-media/API/recovery regressions; **9 frontend tests pass**, TypeScript/Vite
build passes, and Ruff lint/format pass across all 63 editor/test Python files.
HTTP coverage uses an ephemeral loopback server; generation metadata in these
tests is explicitly simulated. No real generated output is claimed. Single
service ownership is tested; simultaneous independent processes sharing one
database are not. Verification holds the service lock, so other edits wait
during bounded media checks. Final scoped review passes at `a4abc2d`.

Broader offline verification ran through `scripts/verify.py` on macOS; no
hardware was connected. Simulation (29 tests), rehearsal browser tests (221),
JavaScript syntax, vendor integrity, and full Python lint/format passed.
The final stable root rerun executed **797 tests in 295.750 seconds**, with only
the 28 previously reproduced cinematic fixture subtest failures and no errors.
The initial run overlapped the final code fix and had two extra shot-template
failures; those disappear in both the nine-test focused run and stable root
rerun. Plan provenance includes editor source hashes, so concurrent source
edits can invalidate cached plans. Final reports, including
`stable-root-rerun.txt`: `/tmp/takeone-vfx-verification.F7yI4Z/`.
The whole branch is not green or declared merge-ready.
No motion behavior or golden hashes were changed to hide failures.

### Real test input and access

- One six-second reference from working-source seconds [72,78), 1280x720,
  H.264/30 fps/180 frames. Full decode passes; original hashes unchanged.
- Labeled first/middle/last frames inspected. The cook turns takoyaki; proposed
  VFX adds suspended scallions/crumbs, avoiding hands/tools and preserving action.
- Local-only files, attribution and **unsubmitted** request JSON:
  `~/Movies/takeone-vfx-proof.cC8MLC/`. Source is silent; no audio-quality claim.
- Existing Desktop test project `1ce57094-29d3-4691-aa4b-688034f58811`;
  imported source `7524adf3-ba16-4300-8e6e-3daf1da0933c`. Native readback confirms
  six seconds, 720p, ready, local registration, cloud access unavailable.
  Generation's supported reference transfer still needs qualification.
- Signed-in account shows 5 credits and Seedance marked PRO. Smallest monthly
  upgrade shown is $25 for 100 credits. Currency/tax/final terms are checkout
  questions. No purchase, generation, cloud footage upload or message sent.

### Remaining completion gates

The full editor is **not finished**. Still required: paid-access and generation
qualification; actual before/after review; VFX planning from real source evidence
and scene scripts; provider job/recovery integration; observed timeline/UI
progress; qualified insertion/export; real sound; Windows checks; repeated-run
acceptance and resolution of the documented native timing/color limits.
Do not label a prepared request, imported derivative or successful job as a
completed film. No push/merge is part of this checkpoint.

Fresh origin fetch still ends at `dffc505`. Its five commits not yet integrated
into this worktree have no editor code/UI/test changes. Main remains untouched.

## September 16 real-footage demo completed, precision acceptance still open

The approved local-only test now has a real 22-second ChatCut Desktop edit.
Five source selections last 3, 5, 2.5, 4 and 7.5 seconds; one 12-frame dissolve
and a built-in final-shot 1.08x slow push preserve the filmed cooking action.
No replacement video, new shader, paid generation or production adapter was
introduced. This is an agent-directed editing demonstration, not an implemented
scene-script/VFX planning workflow in TAKE ONE.

Dedicated single-timeline project: `1ce57094-29d3-4691-aa4b-688034f58811`;
timeline: `170ebd92-cb77-4ea1-8edc-24757475d1fc`. Existing projects are unchanged.
Native plain/treated MP4s and XML are under `~/Movies/ChatCut/`, named
`takeone-real-PkRmJt-*`. The original/edited handoff, credits, source selections,
tool receipts and viewed frame comparisons are under
`~/Movies/takeone-real-footage.PkRmJt/`. Media stays outside Git.

Both MP4s fully decode, with 660 H.264 frames, 1080p/30 fps and 22-second
video/audio streams. Viewed samples preserve actual hands/tools and food
progression. Interior untreated frames match the plain export exactly; measured
final-shot zoom rises toward the requested 1.08x. No black interval >= 0.05 s
or freeze >= 0.5 s was detected at the tested FFmpeg thresholds.
The original and working-source SHA-256 hashes remain unchanged.

Important qualification limits:

- The downloaded source and working copy both decode to entirely silent audio,
  as do the exports. This cannot qualify original sound or dialogue quality.
- Real-footage rough-cut boundaries at frames 90, 240 and 435 are visibly one
  frame late, consistent with the earlier synthetic finding. No compensation
  or weakened test hides the discrepancy.
- Four interior source/export samples have mean RGB differences 7.41-8.00/255,
  with spatial correlations > 0.998. Color-precision acceptance remains open.
- XML was produced, but cross-editor round-trip/effect fidelity is untested.
- Visual inspection is sampled, not a claim of continuous subjective playback.

Next integration work still needs a bounded design: map an existing editor
project/script into ChatCut, keep scene and VFX instructions separate, and
reconcile native output limitations explicitly. This demo does not complete C0
or authorize changing Caesar's architecture. No push/merge or team message ran.

Earlier in the day, the separate clean main checkout was fast-forwarded to
`dffc505` and smoke-tested (49 focused Python tests and 267 browser tests passed).
This feature worktree still contains its existing local probe commits and has
not incorporated those five new upstream commits. Do not confuse the two states.

## September 16 real-footage input prepared (earlier checkpoint)

Basil authorized sourcing an online video instead of waiting for new filming.
Selected a two-minute cooking excerpt from
[2020年2月大阪グルメ旅](https://www.youtube.com/watch?v=U-PFfhzEyBM), by
エミコ グラヴェル / graveru. The
[Commons source and license record](https://commons.wikimedia.org/wiki/File:Man_bakt_takoyaki%27s_in_het_restaurantje_Takomasa_in_station_Shin-Osaka,_-februari_2020.webm)
states CC BY 3.0 and records a YouTube license check dated December 26, 2020.
Downloaded that available mirror, not an arbitrary downloader-site copy. This
is licensed third-party test footage, never evidence that TAKE ONE filmed it.

Local files are under `~/Movies/takeone-real-footage.PkRmJt/`, outside Git:
unmodified `takoyaki-source.webm`, `takoyaki-working.mp4`, a timestamped
`source-overview.jpg`, and `ATTRIBUTION.md` with source/license URLs and hashes.
The H.264/AAC working copy is 1080p/30 fps and fully decodes (3612 video frames,
120.400 s video, 120.472 s audio). Source hash remains unchanged. Actual sampled
pixels show hand/tool activity, food changing during preparation and camera
movement. Audio presence/decode is verified, not listening quality or speech.

Next bounded test: use separate source ranges with unequal durations, one
supported transition and a restrained effect, then compare source/export
actions and audio. This turn prepares input only; it does not claim a ChatCut
edit, AI-driven cut selection, VFX generation or production integration.
Retain credit and list modifications with any shared result. The existing
synthetic export limitations and inherited repository test failures remain open.

## September 15 current direction: keep ChatCut and qualify incrementally

Basil explicitly retained Caesar's ChatCut architecture and authorized small,
compatible changes plus autonomous test/fix loops. The earlier suggestion to
switch backends is **not adopted**. The synthetic timing/color checks expose
limitations; they do not by themselves establish that ChatCut is unusable for
the team's demo. Full precision acceptance stays open without preventing bounded
read-only integration work. No test threshold or cut request was changed to hide
a failure.

Current execution plan:
[ChatCut qualification](../superpowers/plans/2026-09-15-chatcut-qualification.md).
It adds an opt-in Python diagnostic, not a production adapter or new app surface.
The repeated wrong-target and incomplete-state observations justify this small
reproducible probe; it does not grow into a generic orchestration platform.
It leaves the Director, UI, renderer and robot interfaces unchanged.

Caesar's new main commit `3e336e5` adds cinematic shot language, shot design,
performance beats and review/rehearsal integration. It has been incorporated
locally with the earlier voice/cinematic commits, preserving the existing editor
and uncommitted qualification notes. His new shot-design skills provide useful
upstream context, but no VFX selection skill or editor mapping is inferred to be
implemented merely from their presence.

Additional native export evidence: the dedicated nine-second/270-frame timeline
exported at 480p (actual 852x480) and 1080p (1920x1080), H.264 at 30/1 fps with
nine-second AAC audio. Both pass full decode. The preview width is the provider's
observed output, not an assumed 854-pixel contract. These resolution checks do
not resolve frame-accuracy/color acceptance. Local receipts and probes are in
`~/Movies/takeone-qualification.FWzKht/resolution-checks.json`; the MP4 files are
`~/Movies/ChatCut/qualification-FWzKht-preview-480p.mp4` and
`qualification-FWzKht-final-1080p.mp4`.

### Python read-only probe and live checks

`takeone.editor.chatcut_probe` is an optional local diagnostic. It initializes
the official stdio connector, discovers all tool pages, checks project/timeline
identity, reads the complete timeline plus each item's properties twice, and
fingerprints the observed state. It never edits, exports or retargets a project.
One probe run shares cumulative ceilings of 1,000 pages, 10,000 items and 8 MiB
of received data across tool discovery, timeline reads and item inspection. It
fails closed when any ceiling is exceeded, in addition to its timeout,
per-message, notification and backlog limits.
Keep the intended single-timeline project open before running it:

```sh
.venv/bin/python -m takeone.editor.chatcut_probe \
  --project-id fd7f6c8f-023a-45a1-91cf-f1ce212f9876 \
  --timeline-id 1863a94e-4775-456e-bd22-36eaa6716066 \
  --output /tmp/chatcut-snapshot.json \
  --server '/Users/basilliu/Library/Application Support/ChatCut/chatcut-mcp'
```

To compare, add `--compare /tmp/chatcut-snapshot.json` before `--server`,
and choose a new output path or omit `--output`. Existing files are never
overwritten. Paths and IDs above are this Mac's diagnostic setup, not shared
deployment configuration. Do not copy or print the access-bearing launcher's
contents. Reports contain project metadata and belong outside Git.

Live results on Desktop 0.3.16 / bridge 0.1.6:

| Check | Result |
| --- | --- |
| Read dedicated project and repeat unchanged | Both exit 0; complete 60-tool discovery and matching snapshot. |
| Change only synthetic bed gain from -6 to -5 dB | Compare exits 2 with `the ChatCut timeline state changed`. No clip-placement change needed. |
| Restore gain to -6 dB | Readback/comparison matches original snapshot, exit 0. |
| Original project with two visible timelines | Exits 2 with the single-visible-timeline explanation. Dedicated project restored afterward. |

Evidence is `python-probe-baseline.json`, `python-probe-repeat.json`,
`python-probe-restored.json` and `python-probe-live-evidence.json` under the local
qualification directory. This is read-only qualification, not an atomic snapshot,
concurrent edit lock, conflict-resolution UI or a production ChatCut adapter.

An additional synthetic variable-frame-rate source (15 fps followed by 30 fps)
imported and trimmed from source seconds 1 to 5. Its native export has 120 frames
at 30 fps, four seconds of video/audio, and passes full decode. Viewed samples
show different source-frame choices near the low-frame-rate section; this does
not establish frame-perfect VFR, real-phone or HDR support. Evidence:
`vfr-mcp-evidence.json`, `vfr-comparison.jpg`, and native output
`~/Movies/ChatCut/qualification-FWzKht-vfr.mp4`.

### Integration verification status

The hardened probe revision passes 43 subprocess/CLI tests and the 135-test
editor suite. Independent review led to bounded queue/write/compare-file
handling, strict JSON-RPC envelopes, readable inspection-content checks and
cancellation of a writer with queued work during cleanup. Final review also
added sanitized failures for excessively nested JSON and numeric overflow at
parse/canonicalization/report-output boundaries.
The hardened live probe still matches the original snapshot. Its report is
`python-probe-reviewed.json` in the local qualification directory.
The existing editor frontend passes nine tests and its TypeScript/Vite build.

The full root test run executed 753 tests and reported 28 subtest failures in
`test_all_28_pre_upgrade_settings_keep_exact_frames_samples_and_commands`.
A clean archive of `dd8e1cd`, before the probe, independently reproduces all 28.
For the static template, pre-cinematic commit `1835f70` also produces the same
current frame hash after omitting the newer unsupported `camera_target` setting,
not the stored expected hash. This establishes an inherited fixture mismatch
on this Mac, not its exact generation cause or a safe motion-code remedy.
No expected hashes, physical behavior or acceptance thresholds were changed.
Full verification logs are outside Git at `/tmp/takeone-verification.FWUIT5/`.
The whole repository is not green and this branch is not declared merge-ready.
The other completed root checks pass: 29 simulation tests, 221 rehearsal web
tests, JavaScript syntax, vendor integrity and Ruff lint. The first format pass
ran while the review fix was editing a test file; the fresh post-fix run passes
all 238 files, and repository-wide Ruff lint passes too. No AXI shipping run, push or
remote merge was started for this batch.

Task review and final broad review are closed after their scoped fixes and
re-reviews, with no outstanding finding in this qualification addition. The
completed plan and code are committed locally on `docs/recording-call-handoff`.
Keep that branch unpublished until the separate repository gate is resolved.

## September 15 earlier follow-up: exact export qualification still failing

Basil approved an autonomous reproduce/isolate/retest loop. He subsequently
resolved a macOS login-keychain prompt himself and selected Always Allow.
No password was collected or keychain setting changed by the agent. Connector
calls resumed successfully; this does not prove future prompts are eliminated.

The follow-up isolates failures beyond the first fixture. **Do not start the
whole ChatCut production adapter or declare the AI editor finished.** The
observed export discrepancies are downstream of the submitted/read-back edit
plan. ChatCut's internal renderer implementation is not part of this repository;
there is no evidence-backed application-code fix to apply here. Do not hide the
failure by moving cuts a frame early, weakening tests, patching the installed
third-party app, or silently selecting a different backend.

### Follow-up results

| Check | Observed result |
| --- | --- |
| Varied cuts, 270-frame single-timeline project | Requested frames 45, 120, 180; native picture changes at 46, 121, 181. All three are one frame late. |
| Independent FFmpeg control | Same source spans cut at exactly 45, 120, 180. Source/control mean RGB difference is 1.920/255, passing the existing <3 test. This is a diagnostic control, not a replacement production renderer. |
| Explicit color metadata | Separate SMPTE 170M-tagged and converted/tagged BT.709 fixtures still differ from their own decoded sources in native exports. Interior mean RGB differences range 5.47-9.23/255 across four controls. Missing source tags alone do not explain the discrepancy; exact native color-pipeline cause remains unproven. |
| Editable XML | Export parses as `xmeml` and preserves requested clip boundaries and source spans exactly. Cross-application import and effect fidelity have not been tested. |
| Twelve-frame Cross Dissolve at frame 45 | Endpoint inspection confirms attachment. Export pixels blend monotonically from red at frame 39 to blue at frame 51. Repeating the add updates the same transition ID, not a duplicate. |
| Separate synthetic 660 Hz audio bed | Readback has range [15,165), -6 dB, 0.25 s fade-in and 0.5 s fade-out. Exported frequency measurements confirm presence inside the range, absence in sampled outside windows, fades and retained embedded 440/880 Hz audio. Not music/dialogue listening acceptance. |
| Connector process restart | Project identity and normalized timeline readback match before/after restart; the same transition remains attached. Not app restart or exhaustive ambiguous-commit recovery. |
| Invalid atomic edit batch | An otherwise-valid audio gain change plus an out-of-bounds video source span is rejected; audio properties stay unchanged. |
| Multiple timelines | Tool working target changed to the new 270-frame timeline, but `local_export` produced the previously viewed 180-frame timeline. Frame-count verification caught the mismatch. Separate single-timeline project eliminated it for subsequent diagnostics. No multi-timeline export claim is supported. |

The new offline script has **9/11 checks passing**, with exact native cuts and
native source-pixel preservation still failing. The earlier 7/10 report remains
historical evidence, not silently replaced. Actual comparison images were viewed
after rendering, following the visual-analysis skill; tool success alone was
not treated as visual acceptance. Exports decode successfully, but the absence
of an exposed native export-status tool still needs integration handling.

Transition attachment is available in the outgoing video's `inspect_item`
response even though `preview_timeline` omits it and inspecting the transition
ID itself fails. A future projection must not infer that there is no transition
from the lightweight timeline entries. The imported WAV was presented as a
local OGG derivative after processing; preserve original-file identity separately
from the provider display name. Originals are unchanged.

### Qualification boundary and resume point

C0.1-.6 have useful local evidence, subject to the limitations above. C0.7 is
partial because attachment/revision projection needs work. C0.8 yields accessible
decodable files but fails exact picture acceptance. C0.9 has the earlier real
unknown-outcome reconciliation plus a new connector-restart check, not complete
fault coverage. C0.10 external-edit conflict handling, C0.11 a real-footage hero
treatment, and C0.12 a complete duplicate-free TAKE ONE run remain unqualified.
There is no production adapter, scene-script integration or VFX decision skill
implemented by these experiments. Synthetic colored cards cannot prove preserved
people/actions, meaningful pacing, intelligible speech or editorial quality.

Next external dependency: obtain a supported ChatCut remedy for native timing,
color and target-selection behavior, or obtain explicit approval for a different
backend route. No vendor message, issue, paid job or provider switch was sent or
performed. Current official [release information](https://chatcut.io/docs/releases)
and [Desktop documentation](https://chatcut.io/docs/desktop-app), checked September
15, do not establish a fix for these exact observed exports. Real consented clips
and Caesar's scene-script skill remain later inputs, not prerequisites for
reproducing these technical failures.

Evidence remains local, outside Git:

- `~/Movies/takeone-qualification.FWzKht/isolate.py`,
  `isolation-results.json`, `isolation-mcp-evidence.json`,
  `isolation-control.mp4`, and `isolation-comparison.jpg`.
- `~/Movies/ChatCut/qualification-FWzKht-isolated-cuts.mp4`,
  `qualification-FWzKht-dissolve.mp4`,
  `qualification-FWzKht-dissolve-audio.mp4`, and
  `qualification-FWzKht-edit.xml`.
- `qualification-FWzKht-seam-isolation.mp4` is deliberately retained evidence
  of the wrong-timeline export, **not** the four-shot result.

The isolated Desktop project is `fd7f6c8f-023a-45a1-91cf-f1ce212f9876`, named
`TAKE ONE - export qualification`. The original user project and first test are
preserved. Generated MCP evidence includes the complete 60-tool schema catalog,
requests, returned IDs and readbacks, but not the access-bearing launcher.

Reproduce the current failing measurements with the existing environment:

```bash
.venv/bin/python /Users/basilliu/Movies/takeone-qualification.FWzKht/isolate.py
```

Expected exit code: 1. These files are local diagnostics, not a portable test
fixture already delivered to the team. No product source changed, no push or
merge occurred, and publication's separately documented validation-daemon
blocker was not bypassed.

## September 15 initial synthetic edit/export qualification: partial pass

Basil approved the artificial-clip test. It ran through ChatCut Desktop's
supported local stdio connector, not the browser or a simulated editor.
Two locally generated sources (6 and 9 seconds, 1280x720/30 fps, frame/time
labels and 440/880 Hz test tones) were imported. No real footage, generated
AI assets, paid-generation tools, or robot interfaces were used.

Requested cut: source A `[1,3)` seconds on timeline `[0,60)` frames, then
source B `[2,6)` seconds on `[60,180)`. First media insertion automatically
changed the initially empty 1920x1080 canvas to the source's 1280x720 size;
readback confirmed that change. Three native H.264/AAC exports were produced:
plain baseline, second-shot instant zoom, and repeat zoom export.

Observed results:

- Import and timeline readback succeeded. Both sources' SHA-256 hashes remained
  unchanged. The final project contains two video items and one zoom effect.
- All three exports decode with FFmpeg strict error checking. Baseline and zoom
  have 180 video frames at 30 fps, six-second video/audio streams and 48 kHz audio.
- The expected tones are present, with no silent 10 ms windows in the six-second
  audio interval. Decoded baseline/zoom audio correlation is 1.0. This is signal
  evidence, not speech-intelligibility or subjective listening acceptance.
- The zoom is visibly absent from the red shot and present on the blue shot.
  Measured square-width ratio is approximately 1.408 on blue, consistent with
  the preset's 1.4 magnification. The repeat preserves cut/zoom geometry but is
  not pixel-bit-identical (mean RGB difference approximately 0.000078/255).
- An invalid source span ending at 12 seconds on a nine-second source was
  rejected by `validateOnly`. Subsequent readback showed no timeline change.
- **Frame-accuracy check failed:** visible red-to-blue cut is at frame 61
  (2.033 seconds), not requested frame 60 (2.000 seconds). Frame 60 repeats the
  outgoing red frame with source label 2.966667; frame 61 starts blue at source
  2.033333. Adjacent-frame images and encoded PTS confirm the observation.
  Both baseline and zoom show it, and repeat export preserves the same cut.
  The provider's internal cause is not established; do not compensate by
  silently changing requested edit times or declare frame-accurate acceptance.
- **Source-pixel comparison failed:** mean scaled RGB difference is 7.969/255
  against the requested source spans. There is visible source/export RGB shift
  away from the seam as well. These synthetic sources lack explicit color
  tags, so isolate color-management/fixture assumptions before attributing all
  of this difference to a provider defect.

The local verification script returns failure: **7 of 10 checks pass**. The
three failures are the exact cut boundary, the baseline/source pixel comparison,
and the effect beginning on the exact requested first blue frame. Some failures
share the same underlying observed one-frame delay; they are not three proven
independent renderer defects. Full C0 and provider adoption remain open.

### Actual integration contracts and recovery findings

- `browse_library(id="library:zoom:instant")` suggested `pixel-effect` with
  `builtin:effect-zoom`, but live validation rejected that asset ID. The
  `edit_item` description's target-only `effect` placement also failed with
  missing `trackBoundFrom`. A dry-run then accepted the documented alternate:
  `type:"effect"`, `assetId:"library:zoom:instant"`, the existing track ID,
  `trackBoundFrom:60`, `trackBoundDurationInFrames:120`.
- The committed preset is normalized to `builtin:zoom`. Timeline readback shows
  effect range `[0,120)` while dry-run identifies the second clip as its anchor;
  do not interpret this local range as timeline zero or drop the anchor mapping.
  Both raw effect ID and `effect-track:` ID failed `inspect_item`, despite the
  effect being readable under the track and visible in the native export.
- The effect apply returned `ERR_NETWORK_CHANGED`, then an immediate read
  returned `ERR_NAME_NOT_RESOLVED`. A later read found exactly one committed
  effect. **No mutation retry was sent.** This is a real example of an error
  response with a committed outcome, not a complete fault-injection suite.
- `local_export` returned a local output path and task ID. Its documentation
  refers to `track_export`, which is absent from the discovered 60-tool list.
  Finished files were instead checked by ffprobe plus full decode; durable
  renderer-status integration remains unresolved.

### Local evidence and next test

Artifacts are outside Git in
`/Users/basilliu/Movies/takeone-qualification.FWzKht/`: original synthetic clips,
`verify.py`, `verification.json`, `mcp-evidence.json`, adjacent-frame PNGs and
`cut-comparison.jpg`. The contact-sheet skill helper needed unavailable
ImageMagick, so FFmpeg generated the labeled sheet; its actual pixels were
inspected. No extra image package was installed.

Native outputs are in `/Users/basilliu/Movies/ChatCut/`:
`qualification-FWzKht-baseline.mp4`, `qualification-FWzKht-zoom.mp4`, and
`qualification-FWzKht-zoom-repeat.mp4`. They are synthetic diagnostic examples,
not a promotional film or proof of editorial AI quality.

Recheck the local measurements with this checkout's existing environment:

```bash
.venv/bin/python /Users/basilliu/Movies/takeone-qualification.FWzKht/verify.py
```

Expected current exit code is 1 because the exact acceptance checks above fail.
Do not weaken the boundary test just to mark the provider qualified. Next isolate
the seam at additional positions and with explicit color-tagged fixtures, then
agree acceptable behavior or a provider remedy. Transitions, independently
placed music, VFR, real footage, scene/VFX reasoning, external-edit conflicts,
process restart, complete retry idempotency and Windows parity remain untested.
No production adapter or VFX skill was implemented by this experiment.

## September 15 ChatCut setup and read-only connection verified

Basil created the account and approved Desktop installation/setup. ChatCut
Desktop 0.3.16 (Apple silicon) is installed at `/Applications/ChatCut.app`;
the installer checksum, strict code-signature check and macOS notarization
assessment passed. Desktop displays the signed-in account and 5 Free credits.
The first-run Codex option was selected. No editing prompt was submitted.

The native connection panel exposes a supported stdio executable at
`~/Library/Application Support/ChatCut/chatcut-mcp`. The existing Codex MCP
configuration already has `chatcut_desktop` enabled with that executable, so
no duplicate registration or configuration overwrite was needed. Treat the
launcher as access-bearing local material: do not copy it into Git or logs.

A bounded read-only subprocess probe successfully initialized server
`chatcut_desktop` version `0.1.6`, exhausted tool discovery (60 tools), and
called `get_active_project` and `read_project`. The returned desktop project
matched Basil's supplied URL exactly. Observed state: one active 1920x1080
timeline at 30 fps, zero duration, zero assets, no captions and zero markers.
The probe exited without modifying the timeline, uploading footage, starting
generation, exporting or purchasing anything.

This is initial C0 connectivity/project-read evidence, not complete C0 acceptance
or a TAKE ONE adapter. Media import/identity, trim/audio/effect readback, exports,
recovery/conflict tests, repeat-run behavior and Windows parity remain untested.
The current conversation has no natively exposed ChatCut tools; Desktop's own
connection panel instructs starting a new agent conversation after registration.
The direct stdio read probe establishes a usable diagnostic path in the meantime.

Basil granted macOS Accessibility access for setup. Earlier missing-window
observations do not prove an app crash or closure: he reports the editor stayed
open while he was on another screen/Space. The direct connection requires
Desktop running with the intended project open; foreground GUI control is no
longer needed for the verified read calls.

Next: run a disposable synthetic-media import/edit/export qualification before
testing editorial quality on consented real footage. Do not select paid
generation, overwrite originals or call the overall AI editor finished.

## September 15 specification received

Caesar supplied `TAKE-ONE-AI-Editor-Engineering-Spec.md` (990 lines, v1.0) and
`TAKE-ONE-AI-Editor-Engineering-Spec (1).pdf` (32 pages), plus the following
direct requirements. This supersedes the earlier awaiting-documentation status;
it is a received proposed specification, not provider qualification or permission
to replace the existing implementation wholesale.

- Start evaluation with ordinary consented phone/vlog clips; robot footage is
  not required. Keep originals and the edited result for the team's comparison.
- Exercise different source lengths and deliberately paced output. Choose quick
  cuts and longer holds from visible action and story, not an equal-duration
  template. Different lengths alone do not prove the cuts are appropriate.
- Keep Caesar's forthcoming scene-script skill separate from the visual-effects
  skill. The latter should use the script and actual footage to select what to
  add, its target, start/end and intensity. Two independently versioned skills
  do not require two autonomous agents or separate model providers.
- Enhance filmed reality. Preserve the real people, actions and camera movement;
  overlays or 3D elements may augment it, but a fully regenerated replacement
  shot does not meet this request. Immutable original files alone do not prove
  that an edited result preserved those visible properties.

### Consequences of the supplied specification

Sections 0, 3 and 26 propose external-editor integration first. Preserve the
existing Director/UI and native renderer; stop expanding the native renderer
as the new primary solution. Do not delete, restructure or migrate it without
a separate approved change. The author explicitly had not inspected the full
current repository, so proposed module names, routes and schema sketches must
be reconciled with actual code rather than copied as a second application.

The proposed first candidate is ChatCut Desktop's local MCP workflow. The hosted
Agent Plugin is a different connection. Gate C0 requires demonstrated access
from the intended runtime, complete tool discovery, stable project/media identity,
trim/effect/audio readback, export, disconnect recovery, external-edit conflict
detection and a duplicate-free repeat run. Do not invent native tool names or
infer custom-client support from a desktop-agent integration.

The specification lists Shotstack as a separate alternative, not automatic
failover, and generative derivatives as optional later work. It does not select
Higgsfield or Seedance as an implemented API. Caesar's message further constrains
any derivative: retain the filmed people/action/camera movement and compare
protected content, rather than accepting a preservation prompt as proof.

Desired edits, externally observed edits and rendered pixels remain distinct.
No successful effect-creation response proves that an effect is attached or
visible. Source timestamps differ from script times; preserve source/output
mapping when trimming or retiming, and protect dialogue. Keep original hashes,
source spans, plan versions, artifact lineage and rights evidence.

The E7 30-second / 900-frame example is a synthetic timing fixture, not required
footage for the initial vlog trial. Its base assembly uses hard cuts; transition
timing and optional hero treatments require separate tests. Follow the actual
brief and footage rather than forcing every upload into that exact story.

### Existing code versus the new requirements

| Area | Inspected baseline | New qualification or work needed |
| --- | --- | --- |
| UI, project library, operations, export | Existing React UI and Python/SQLite/FFmpeg editor | Reuse assessed pieces; external integration is not already implemented |
| Planning | `plan/heuristic.py` uses metadata and prompt keywords, not visual scene understanding | Evidence-backed span and VFX decisions against available capabilities |
| Jobs | `jobs.py` uses an in-memory bounded pool | Do not treat it as a durable remote-command journal |
| Provider control | No ChatCut/Shotstack/Runway adapter found in the inspected editor paths | C0 before building a complete adapter |
| Quality | September 14 unit/build/startup checks passed | Real varied-length input, observed timeline, export/audio and preservation review |
| Scene-script skill | Caesar says he will send it separately | Receive its actual interface before authoring the separate effects skill |

The local checkout remains on the documentation branch based on `0ddd15d`.
Remote main was fetched through `bc44fe4` on September 15. New commits `1835f70`
and `bc44fe4` add live voice, recording review and cinematic Director integration;
the editor's navigation also changed. Their live-voice record explicitly leaves
provider access and real microphone/playback acceptance untested. Those are
teammate changes to preserve, not new work assigned to Basil. Reconcile main
before implementation; the older local tests do not validate these updates.

### Provider research and missing inputs

Checked September 15 against [ChatCut Desktop documentation](https://chatcut.io/docs/desktop-app):
macOS Apple silicon, macOS Intel and Windows downloads are now documented.
That makes a Mac qualification trial a candidate, not proof of this account's
access or Windows parity. The native bridge requires the editor and supported
agent on the same machine. [Agent Plugin documentation](https://chatcut.io/docs/agent-plugin)
describes its separate hosted connection. [AI Effects documentation](https://chatcut.io/docs/ai-effects)
distinguishes creating a resource from applying it to a target interval.
At the time of that research, no installer, authentication, provider call, media
upload or paid job was run. The later setup/read-only probe above supersedes
the installation and connection status, not the remaining acceptance gates.

Still needed: consented original clips and a short desired outcome, the selected
qualification route/account and allowed data destination/spend, Caesar's scene
skill, and the companion pack referenced in the PDF. The PDF mentions 42
reference tests and the text refers to `store.sql`; those artifacts were not
supplied as part of these two files and have not been executed here.

The immediate bounded experiment proposed by the spec is two real clips in a
disposable provider project: import, trim, add one treatment and audio, inspect
actual state, export, and compare with originals. A later varied-length vlog
evaluates pacing and content preservation. No new editor skill, provider choice
or feature implementation has been made in this documentation reconciliation.

Source originals remain in Basil's Downloads, unchanged. SHA-256:

- Markdown: `e1978c33218787af1f177c052542d7b651656bcfd5f1f8b2173dcfac3886970b`
- PDF: `9dcf708c22509bc892b3009a3959eebeb11e3820df7b36d61c16ff683bd96ba7`

## September 14 ownership and preparation

Basil reports that Caesar is working on the production workflow and Shot Studio,
and has assigned Basil the video editor: using recordings with AI-assisted
effects, transitions and related editing. Higgsfield and Seedance were mentioned
as references, not selected products, providers or APIs. Caesar will supply the
documentation and plan. Until then, this is environment preparation only:
no new feature design, model choice, integration contract or implementation.
The existing documents below describe the current repository, not approval of
the incoming requirements. Reconcile them when that handoff arrives.

Local preparation on September 14 used main `0ddd15d` plus documentation-only
handoff changes, in `/tmp/takeone-published.mI34kg`:

- Python 3.13.5 in the existing isolated `.venv`; imports resolve to this checkout.
- Node 23.6.0 and npm 10.9.2; `npm ci --no-audit --no-fund` installed the existing
  editor lockfile without changing dependencies or the lockfile.
- FFmpeg and ffprobe 7.1.1 available. Editor `doctor` reports backend ready,
  493 filters and 93 registered effects. Counts are inventory, not quality tests.
- The documented hermetic editor suite passed 92 tests; frontend Vitest passed
  9 tests; `npm run build` passed TypeScript checking and Vite compilation.
- The built page, JavaScript, CSS and healthy API were served over loopback HTTP
  on port 8897. This is a startup check, not visual browser acceptance, a full
  media-edit/export test, full-repository verification or live AI validation.
- Test data stayed under `/tmp/takeone-editor-prep.ufkDD9`. Build output and
  installed dependencies are ignored by Git. The test server was stopped after
  verification; no hardware or private footage was accessed.

No provider accounts, credentials, SDKs, uploads, purchases or AI calls were
configured. Existing architecture and product source are unchanged. Await the
teammate's documents before choosing or implementing the next editor work.

Publication is separately blocked: the existing no-mistakes daemon's system Git
requires an Xcode license agreement. Direct installed Command Line Tools Git
works locally; no license was accepted or system configuration changed here.

For a macOS/Linux startup check, from the checkout root after the editor build:

```bash
.venv/bin/python -m takeone.editor.cli --workspace /tmp/takeone-editor-prep.ufkDD9/data serve --port 8897 --media-root /tmp/takeone-editor-prep.ufkDD9 --static apps/editor/dist
```

Open `http://127.0.0.1:8897/`. Use a separate explicit workspace and media root
for later real work; these temporary paths are only this preparation session.

| Document | What it covers | State |
| --- | --- | --- |
| [architecture.md](architecture.md) | The design of record: layers, data flow, schemas, risks, implementation order, and every place this design departs from the originating specification and why | current |
| [edit-operations.md](edit-operations.md) | The operation log: types, targets, parameters, and the rules the reducer enforces | built |
| [edit-graph.md](edit-graph.md) | Node types, content addressing, validation, and why the graph is derived rather than stored | built |
| [render-engine.md](render-engine.md) | Planner / compiler / executor, the artifact cache, proxies, and the safety rules around FFmpeg | built |
| [effect-system.md](effect-system.md) | The twenty-four primitives, the looks built from them, and transitions as two-input effects | built |
| [adding-an-effect.md](adding-an-effect.md) | How to add a primitive or a look without reading the rest of the repository | built |
| [project-format.md](project-format.md) | The project schema, the `.takeone.json` export, OTIO output, and migration | built |
| [ui-design-system.md](ui-design-system.md) | Tokens, layout, motion rules, and the one-reducer contract the interface follows | built |
| [integrating-with-the-rehearsal-server.md](integrating-with-the-rehearsal-server.md) | The exact addition that mounts the editor on the existing app server | ready to apply |
| template-system.md | Templates as parameterised operation programs | milestone 2 |
| ai-editor.md | Orchestrator, planners, schemas, and the explanation contract | milestone 4 |
| robot-metadata.md | `RobotMetadataAdapter` and the signals it contributes | milestone 5 |

The three documents at the bottom are named here because the architecture commits to them,
not because they exist. Writing them before their subsystems would describe software that
does not run.

## Verifying the editor

```powershell
# Offline: no hardware/cloud. VFX tests create tiny fixtures and require
# ffmpeg/ffprobe on PATH, including the libvpx-vp9 encoder for WebM coverage.
python -m unittest discover -s tests/editor -p "test_*.py"

# Real media, real FFmpeg. Builds its fixtures on first run.
python tests/editor/run_milestone1.py     # import -> build -> grade -> render -> export
python tests/editor/run_milestone2.py     # montage, ramps, transitions, colour matching
python tests/editor/run_api_check.py      # the HTTP surface, including SSE and byte ranges
```

## Running it

```powershell
python -m takeone.editor.cli doctor        # is the render backend usable here?
python -m takeone.editor.cli effects       # what is installed
python -m takeone.editor.cli serve --media-root C:\TakeOne\data\takes
```

Then `npm install && npm run dev` in `apps/editor`, or `npm run build` and point
`--static` at `apps/editor/dist`.

Drop clips on the launch screen. Each film stores originals in
`data/editor/library/{project_id}/media/`. The heuristic editor then analyses, selects,
cuts, grades and finishes the film as a paced stream of operations — watch the AI tab
and the timeline while it works. A second drop in the media bin still places a take
manually.
