# Asset scene integration: live checkout status

Updated 2026-09-15. This supersedes the earlier uninstalled-kit status.

## Implemented in C:\TakeOne

687 real Kenney CC0 models are installed: furniture 140, food 200, nature 329,
characters 18. All 706 referenced files passed local hash verification. All 687
models decoded with the actual browser GLTFLoader; the model viewer and existing
Shot Studio both rendered imported meshes. This is not a mocked download.

Director's existing scene editor exposes 708 asset choices including the 21
legacy procedural objects. Imported IDs are validated against the installed
catalog, survive save/reload and reach the existing rehearsal scene renderer.
Generation uses a bounded lexical asset shortlist and scene-dressing/SKILL.md.
A local request construction test included 23 imported choices in 116,905 bytes;
no paid request was made. The existing live-voice persona budget is unchanged.

The generic loader owns imported resources separately from procedural cleanup.
Browser checks cover authored size/centre within 1 micrometre, shared geometry
and materials, stale-load rejection, visible unknown-asset errors and a redraw
notification after asynchronous load. The cache budget counts encoded source
bytes, not measured GPU memory. No device motion or calibration was changed.

## Use it

Director > Script > Edit scene & objects > Add from object library. Imported
choices appear alongside procedural assets. Set dimensions and placement explicitly.
Viewer: http://127.0.0.1:8766/asset-library/browser.html
Rehearsal: http://127.0.0.1:8766/?script=4e348393-3be2-4e74-9f0c-8aaa57d7aab8/4251a52fbf4631c176854da1106434b7233479d2522c1d03637b7ad449f71830

## Evidence and boundaries

`data/asset-scenes-live-evidence/` contains backend acceptance, preservation
checks, browser reports, screenshots, request construction and full-run logs.
`data/recovery/asset-scenes-20260915T200328Z-151ccd7d/manifest.json` records the
successful core application patch and recoverable original files. Follow-on
before/after records are under the live evidence directory's `before-*` folders.
The initial application patch failed twice on Windows replacement locks and
rolled back. The successful patch omitted optional server-watcher and navigation
changes; it did not change permissions or overwrite those files. Source edits
inside asset_library may therefore require restarting the existing simulator.

Six existing saved documents validated, and every pre-existing saved creative
digest remained unchanged in the preservation check. The ensemble exercise is
a new authored production, not an AI response or an edit of the user's films.

The saved example has six shots, three performers and imported dressing in its
room scenes. Four shots are reviewable. Shots 2 and 6 are explicitly flagged:
the inherited boom preset has no authored vertical travel. A tested moving-boom
candidate instead cropped required regions and was not saved. A later attempted
held-camera correction was blocked before applying. The warnings are not waived.
The saved URL above is the inspected revision; the draft demo builder is not
claimed to reproduce a fully accepted camera plan.

Character clips can be viewed, but this feature does not retarget downloaded
characters onto existing performer figures, provide facial acting, establish
hand/object contact or qualify physical collisions. Actual, proposed and virtual
inventory is conveyed in authoring guidance and location notes, not inferred from
model availability. No custom perception or trained motion model was added.

Run `scripts/TakeOne.ps1 -Command test` for the complete repository suite.
The actual run and its result are recorded separately; older counts from previous
reports are not evidence for this installation.

## Executed verification: 2026-09-15, 20:44 UTC full-run report

| Check | Actual result |
| --- | --- |
| Real imported files | 706 referenced files verified; 687 indexed models |
| Real browser decoding | 687 decoded, zero model failures |
| Asset-focused Python tests | 41 run: 40 passed, one skipped |
| Full JavaScript unit suite | 257 passed |
| JavaScript syntax and repository integrity | Passed |
| Live Director editor | 687 imported choices; saved imported selections present |
| Live Shot Studio | Imported models rendered; no page errors or failed requests in the passing run |
| Existing saved scripts | Six validated; prior creative digests unchanged |
| Full product suite | 752 run; four failures, 51 errors, one skipped |
| Full simulation suite | 29 run; five errors |
| Full-checkout Ruff | Did not pass; feature-local Ruff passed |

The skipped test needs Windows directory-symlink creation privilege; ZIP symlink
rejection and portable path-boundary tests still ran. Live mesh-bound assertions
use a 1 micrometre tolerance for Float32 geometry, not exact decimal equality.

The required `scripts/TakeOne.ps1 -Command test` command returned exit code 1.
Its immutable copied reports are in `data/asset-scenes-live-evidence/full-suite/`.
Failures include missing required performer appearance fields, stale-planner
checks and resulting absent framing-review data. Motion/performer sources were
being edited during the run; timestamps and logs do not establish a clean,
stationary full-checkout regression result. Full acceptance is therefore not met.
The test failures and two demo camera warnings remain open rather than hidden.

## Final live checks

The same application was restarted on port 8766 with --no-prewarm --no-reload
after source-watcher restarts repeatedly interrupted checks. The final health
check reported local rehearsal, robot playback idle, hardwareConnected false.
This verification instance does not auto-reload edits: restart it after code
changes. Existing compiler stale-input checks were not disabled.

The final Shot Studio browser check passed again against that instance.
A character-viewer check found a first-frame RAF timestamp that could precede
the selection event clock. browser.js now bounds viewer elapsed time at zero;
the underlying model time validator remains strict. The corrected live test
passed with no page errors, actual named clips and independent animation state:
playing walk on one instance changed it without changing a second instance.
This verifies the asset viewer, not automatic performer retargeting in Shot Studio.

The final snapshot of 30 feature/shared file paths and current hashes is
`data/asset-scenes-live-evidence/final-feature-files.json`. Original file snapshots
remain in the recovery manifest and the before-* evidence folders.
