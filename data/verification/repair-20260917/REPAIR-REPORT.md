# TakeOne local recovery — September 18, 2026

The supplied saved film is `ef3e5b02-6017-4e94-8cc9-1354b69e43bd/afefd2864c22309ab0ef667b81c70cb40b6dbddc0e0d8f86c26f406c600b0dc3`.

## Recovery and preservation

Before repair, `before-repair.zip` captured the existing dirty/untracked shareable work and patch, and `director-backup.sqlite3` captured the Director database through SQLite's backup API. No reset, clean, source-tree deletion, commit, push, hardware command, firmware change, or calibration modification was performed.

`repair-file-comparison.json` identifies 34 changed and 53 unchanged files from the original dirty-work archive. `final-source-fingerprint.json` fingerprints 3,789 files across product code, browser assets, editor source, configuration, tests, and scripts. Clean-at-start files remain recoverable from Git; new repair files remain uncommitted alongside the original changes.

`production-preservation.json` compares every Director table with that backup. All 17 creative briefs, 40 creative revisions, 18 sessions, events, operations, jobs, and planning requests remain identical. Only the runtime record changed as the local server restarted.

## What actually broke and what changed

- The new shell removed controls that Shot Studio and Motor Lab access during module initialization. Restored the controls, repaired obsolete header lookups, and added startup-contract regression tests.
- CSS pruning removed layout rules for dynamically created shot controls, movement cards, stage columns, the camera monitor, and disclosure drawers. Restored those rules with the shared design tokens. Fixed hidden elements overriding `[hidden]` and the phone setup sheet remaining translated offscreen.
- Record had an initialization ordering error, a placeholder planned frame, mismatched subject/review request fields, wrong clock arithmetic, and automatic camera permission requests. Fixed startup and request contracts; permission is now an explicit button action. Elapsed time uses monotonic timestamps.
- Record's planned frame now uses the existing Shot Studio camera renderer. The saved script revision or current compiled shot settings transfer from Studio; the plan timeline scrubs the actual simulated camera and lens.
- Record uses a phone recording source only after pairing and passes phone-specific arguments rather than simulated zoom/scenario inputs. Observe prepares the selected subject and goal through the owning voice session before invoking the observe route.
- Behavior-triggered capture now goes through the same recording/voice bridge as manual capture, retaining ownership and the quiet latch. A server watchdog handles stale camera input and maximum take duration even if the page stops delivering frames.
- Uncertain phone stops remain uncertain. Recovery checks the device's idle report, shutdown attempts to close owned captures, and acknowledgment events retain device-reported timing. Phone media remains on the phone and is never presented as a verified local file.
- Static files request revalidation so reloads receive the repaired code. Existing lint/format problems in the supplied work were corrected as part of the required checks.

## Interactive checks

- Supplied film: three shots, 32 seconds; world and camera rendered; rehearsal advanced through shot transitions and changing focal lengths; pause worked.
- Record: original film rendered in the planned frame; scrubbing to 24 seconds changed the camera view and focal length to 41 mm.
- Modified shot handoff: changed a Static preset's filming duration to 12 seconds; Record rendered that compiled plan with its 16.88-second total including arm setup.
- Phone setup: opens as a visible sheet; no camera, microphone, phone, or Bluetooth permission was granted during verification.
- Director: saved Cinematic story opens and preserves the exact rehearsal revision link; movement cards render and link to templates.
- World: local draft generated five objects and four relations and rendered the furnished scene. No saved production was overwritten.
- Motor Lab: actual cart and dual-arm scene rendered; simulated prediction played and raw joint readouts advanced. No motor connection was opened.
- Voice rehearsal: offline page loaded. No paid provider session was started.
- Editor: build and nine front-end tests passed; local built UI started on port 5178. All eight existing projects reopened after repairing schema-1 initial-intent replay. The Mysterious luxury introduction edit recovered its three media items, operations, and timeline; its 11.266667-second preview loaded with `readyState=4`, no video error, and visibly advanced through playback. `editor-reopen-audit.json` verifies saved project rows were unchanged by reopening. Previewing can create/reuse a derived artifact; no edit operation was submitted.
- Record initially contained an unresolved take marked "Stop unconfirmed". A direct read established that its source was `simulated` and its error was `runtime_restarted`. After creating `recording-before-recovery.sqlite3`, the app's Resolve action retained it as failed, appended a `recovery_retired` event, and unblocked the controls. `simulated-take-recovery.json` records the outcome. No take or media was deleted; no phone stop was asserted. Recovery guidance now distinguishes this simulated case from a real phone that must report idle.

## Test baseline correction

The historical movement fixture's 28 frame hashes did not reproduce even with clean committed source at `da1268e0ab83d9978dcf422e7794b44502bb08dc`. `head-source`, `compare_motion.py`, `head-motion.json`, and `repaired-motion.json` preserve the comparison. All 28 frame, motor-sample, and cart hashes from the repaired source exactly match that clean committed source. Historical motor-sample and cart hashes also remain unchanged.

The legacy fixture was retained. `tests/fixtures/committed-movement-frames.json` records the independently reproduced committed frame reference, and the regression test now checks that reference for frames while retaining the original motor/cart checks. This is a documented reference correction, not a tolerance increase or a claim of unchanged historical frame hashes.

## Verification results

The first complete repaired run passed 989 product tests (one skip), 29 simulation tests, 331 JavaScript tests, JavaScript checks, integrity, and lint. Its final formatting check caught the newly added Editor regression test while it was being written; that formatting was corrected. `before-editor-checks` preserves the exact results, without rewriting them as a clean run.

The additional Editor fix passed all 96 editor-engine tests. Its new regressions reproduce the original reopen failure before the fix and verify initial-brief preservation through reopen and undo while retaining snapshot-corruption detection. No database repair or rewrite was necessary: schema-1 creation metadata is used only when the complete operation history contains no SET_INTENT operation.

The final complete launcher rerun, `scripts/TakeOne.ps1 -Command test`, exited **0** at 2026-09-18 00:56 Toronto time. `final-after-editor.log`, `summary.json`, and `check-0.txt` through `check-6.txt` preserve the actual output:

| Check | Result |
| --- | --- |
| Python product suite | 993 run, no failures, one skip |
| Simulation suite | 29 passed |
| Rehearsal JavaScript suite | 331 passed, no failures or skips |
| JavaScript syntax and token synchronization | Passed |
| Repository integrity | Passed |
| Python lint | Passed |
| Python formatting | Passed, 314 files already formatted |
| Editor build / TypeScript | Passed |
| Editor front-end tests | 9 passed |

The single skipped product test requires directory-symlink creation, which this Windows account does not permit. The 96 Editor engine tests are included in the product suite as well as their focused run. `source-check-result.json` confirms that none of the 3,789 fingerprinted files changed between the fingerprint capture and final verification completion.

## Local entry points and restart

- Rehearsal: `http://127.0.0.1:8766/`; the supplied script link opens the preserved three-shot film.
- Record: `http://127.0.0.1:8766/record.html`; opening Record from Shot Studio transfers the last successfully compiled plan.
- Editor: `http://127.0.0.1:5178/`; the existing built UI is served by the editor API in one local process.

After stopping the relevant existing service, these PowerShell commands restart it without depending on the terminal's working directory:

```powershell
& 'C:\TakeOne\scripts\TakeOne.ps1' -Command simulator
& 'C:\TakeOne\.venv\Scripts\python.exe' -m takeone.editor.cli serve --port 5178 --static 'C:\TakeOne\apps\editor\dist' --media-root 'C:\TakeOne\data\takes'
```

Run these in separate terminals. Starting the simulator opens no motor connection; physical actions remain explicit operator controls.

## Limits

These are local software and simulator results. A paired iPhone, real camera media, Bluetooth acknowledgments, paid voice/planning providers, live tracking, and physical motion were not exercised. Phone route integration tests use a fake device and do not qualify a real handset. The project still refuses the unverified embodied arming path.

The original redesign's 60 KB CSS target is not claimed as met. Responsive CSS was repaired, but the browser viewport override did not produce a reliable 1024-pixel viewport; do not read these checks as verified device-size coverage. Record's planned camera is a simulation, not evidence of synchronized physical execution.
