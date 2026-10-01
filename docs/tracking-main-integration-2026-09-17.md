# Tracking integration onto GitHub main, 17 September 2026

The local branch `integration/tracking-on-main-20260917` was refreshed and
rebased onto GitHub `main` commit
`b615d773298fddd9143a80c4c9461a015394b1a3`, including its AI production
designer and generative-world workspace. It adds the tracking feature and
active light-arm calibration from the local commits `12b4860` (calibration)
and `f6d0be6` (tracking), without importing their session-database changes or
historical run output.

The original checkout at `C:/Users/nonst/Documents/Python/TakeOne_Astra/TakeOne`
remains on its original local `main` at `f6d0be6`. Its files, local commits,
runtime environments, session database and saved runs are preserved. The new
checkout is `C:/Users/nonst/Documents/Python/TakeOne_Astra/TakeOne-main-tracking`.
After the refreshed source and tracking integration passed their software
checks, this single integration commit was fast-forwarded to GitHub `main` at
the operator's request.

## Conflict resolutions

| Area | Integrated result |
|---|---|
| README | Retained current main's production/voice/setup documentation; added tracking and current calibration sections |
| Shot Studio HTML | Retained the cinematic UI, experience layer, channel editor and shot-direction assets; added the tracking panel and its assets |
| HTTP server | Retained current main's model caching, perception, Live Director, Gemini voice tools, source reload and listener behavior; added tracking routes, status, shutdown and exclusion with robot playback |
| Frontend checks | Retained every main check and MediaPipe dependency; appended tracking JavaScript checks |
| Python packaging | Retained all new Director skill package-data entries; excluded the byte-preserved tracking source from formatting |
| Reposition and sequence descriptions | Retained main's non-executable/lower-bound travel explanation; described configured starting goals instead of always claiming midpoints |
| Shared starting pose | Kept main's motion-policy-based aiming duration; added optional explicit encoder goals with midpoint fallback |

The tracking scripts and UART helper retain their original SHA-256 hashes.
Both original calibration files and the phone mapping retain their previous
hashes. The active light-arm ranges and goals match the operator's latest
values; no calibration registers or hardware settings were changed.

The active `data/robot-commissioning-ready.json` plan was stale against the
replacement light-arm calibration and required 150 clamped light-arm samples.
It was regenerated offline from `configs/robot-commissioning-shot.json` with
current provenance. All 226 refreshed samples convert without clamping, and
the matching checked-plan receipt is retained. Its commissioning preflight
still reports existing numerical, support, endpoint-derivative and unverified
alignment blockers, so this refresh does not claim that live execution is safe.

## Validation

Using the existing simulation Python environment with `PYTHONPATH` and
`TAKEONE_ROOT` explicitly pointed to this new checkout:

- A 73-test focused Python suite passed: tracking, calibration revisions,
  calibration-dependent cinematic snapshots, current-plan conversion,
  production design and Live Director HTTP boundaries. Devices, cameras and
  providers are fake fixtures.
- All 303 JavaScript tests passed: tracking client/panel, robot client,
  production design, the current experience UI, browser-local perception and
  live voice contracts. A Windows test-harness expression now accepts both LF
  and CRLF when removing imports from the authored voice module.
- Every JavaScript syntax command declared in `apps/rehearsal/package.json`
  passed. Ruff passed on every Python file changed by this integration. The
  full Ruff command still reports 31 pre-existing violations in files identical
  to fetched `origin/main`; those unrelated upstream files were not reformatted.
- Source-integrity and original-calibration hashes matched. The staged source
  diff passed whitespace checking excluding the unedited supplied scripts.
- Calibration-dependent cinematic snapshots, explicit start-pose assertions
  and the refreshed commissioning plan conversion were checked against the new
  light-arm mapping; the refreshed plan has zero clamped joint samples.

The full simulation suite and physical playback were not run, following the
operator's instruction. No application server, camera or robot was launched.
The existing main versions of `apps/rehearsal/server.py` and
`packages/takeone/previs/compiler.py` already fail Ruff's formatting-only
check; unrelated reformatting of those files was left outside this integration.

## Using the separate checkout

The new worktree does not share editable Python installation state or frontend
node_modules with the old checkout. Run its normal `scripts/Setup.ps1` before
launching it, and `scripts/setup_robot_runtime.py` if ordinary robot playback
is needed there. Neither setup nor the simulator has been launched here.

Tracking continues to use the existing environment selected by
`configs/tracking.json`, whose relative path resolves correctly from either
checkout. Both model files were copied into the new worktree's ignored
`.runtime/tracking/models` cache. `scripts/Check-Tracking.ps1` performs the
non-actuating dependency/source check.

Historical Git LFS archives, editor videos and upstream test artifacts were
left as pointers in this source-integration checkout. They are unchanged by
the feature and are not required by these checks; hydrate them with the normal
Git LFS workflow when those historical assets are needed.
