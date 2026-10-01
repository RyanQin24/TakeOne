# Director authoring and simulator handoff verification

Date: 14 September 2026. Workspace: `C:\TakeOne` (root rehearsal on port 8766).

## Verified application behavior

- The served Director displays four labelled editorial samples, including **A
  serious entrance**. The existing user's production was preserved.
- Opened the cinematic example in the browser. Saved an orbit change from 30 to
  45 degrees, confirmed the new value and revision-specific rehearsal link, then
  restored 30 degrees. Switching to Dolly Zoom loaded that preset's own fields.
- Edited and saved stage mark coordinates, dialogue performance directions and
  explicit between-take actor-reset wording through the UI.
- The saved example is session `cdd223e5-18ac-4d8b-95c5-b92cfab0f1ec`, document
  `57828ed84b159a1d752583b6ced76220e35dfa431fb9fbd4fafaf7d5ff9a4fa3`.
- Rehearse in studio navigates in the same tab to this exact saved revision.
  Three shots and two setup moves load on one 49.64-second rehearsal timeline;
  the proposed edit remains 32 seconds. Play, pause, shot selection and scrubbing
  were exercised. Actor and cart were visually separate during the walking shot.
- Rising orbit: compiled camera height 1.254624 to 1.590441 m; upward pitch
  10.10989 to 0.175824 degrees. Fixed a false advisory that compared the ending
  height to the requested starting height. The existing 18.5-degree maximum
  aiming-error advisory remains visible and does not prevent playback.
- Dolly Zoom out: browser monitor showed focal length changing from 35.0 mm to
  44.7 mm near the end of the cart retreat. Starting lens remains labelled 35 mm.
- Script rehearsal uses readable dark shot cards and shows the active shot's
  lens settings. Single-shot lens editing controls are hidden during script
  playback; these settings are edited in the Director's script.
- Final preview browser console inspection returned no warnings or errors.
- Health check: local rehearsal, robot playback idle, hardware disconnected.

## Automated checks

The required `scripts/TakeOne.ps1 -Command test` was run. Its original logs and
summary are preserved in `required-run/`:

- 633 product tests passed.
- 198 frontend tests passed; frontend syntax checks passed.
- Preservation check passed (1,086 LeRobot files checked, no preservation
  failures). Existing recorded source changes remain recorded.
- Repository Python lint and formatting checks passed.
- The simulation phase initially stopped at its stale-source guard while the
  diagnostic source was being corrected. Its fresh-process rerun passed all
  **29 simulation tests** in 803.735 seconds; the result is recorded separately
  in `simulation-final.txt`. Every check from the required runner therefore has
  a passing result, with this corrected rerun recorded separately rather than
  overwriting the original failed run.

Focused checks also passed: 26 creative planning tests, 10 repair tests, 10
translation tests, 3 script bridge tests and 11 diagnostic tests. These counts
overlap the larger suite and are not additional independent totals. The new
diagnostic regression was added after the main suite's discovery and was run in
the focused 11-test check. Source whitespace checks passed for changed source
files. The skill creator's validator reports **Skill is valid!**

## Provider and scope

The running Director reports `gpt-5.6-luna`, reasoning `max`, `missing_key`.
Configuration uses the OpenAI Responses API with strict structured output and
separate API billing. The provider fixture test checks the exact outgoing model
request, saves its result through the normal job-completion path, retrieves the
rehearsal manifest and refuses a stale document digest.

No live provider request was made: `OPENAI_API_KEY` is not configured in the
server process. Live generation, account access and billed usage are unverified.
Samples remain labelled curated examples. No real motors were actuated, and
simulation results do not establish physical robot performance. Reposition
segments are simulated estimates; phone recording and physical zoom remain
manual in the existing integration.
