# Commit plan for prompt 16

I could not run `git` from the environment that reached this checkout:
`git-lfs` is not installed there and this repository stores
`archive/recovery/**/workspace.zip` through LFS, so a commit from that side
risked writing broken pointers; `git status` also reports every file as fully
rewritten (CRLF/LF) and takes minutes against `data/previs-cache`. Run these on
the Windows host, where the LFS filter and the line-ending config are correct.

Check `git status` first. A live-tracking feature was landing in this tree at the
same time (`packages/takeone/motion/tracking*.py`, `scripts/tracking/*`,
`scripts/Check-Tracking.ps1`, `configs/tracking.json`, `configs/robot-commissioning-shot.json`,
`tests/test_tracking.py`, `tests/test_calibration_revision.py`, `tests/test_motor_panel.py`,
`tests/test_orbit_previs.py`, `tests/test_shot_playback.py`, `packages/takeone/calibration.py`,
`packages/takeone/previs/{compiler,reposition,sequence,start_pose}.py`,
`docs/live-tracking.md`, `docs/tracking-main-integration-2026-09-17.md`,
`docs/light-arm-calibration-2026-09-17.md`, `docs/calibration-inventory.md`,
`data/verification/preservation.json`). None of those are part of this work —
commit them separately, or first.

Deleted files that need `git rm`: `apps/rehearsal/dist/takeone.css`,
`takeone-experience.css`, `takeone-refine.css`, `style.css`, `layout.css`,
`shot-direction.css`, `channel-editor.css`, `recording.html`, `recording.css`,
`recording.js`, `recording-client.js`, `fonts/instrument-serif-400.woff2`,
`fonts/OFL-Instrument-Serif.txt`, `apps/editor/public/fonts/instrument-serif-400.woff2`,
`apps/editor/public/fonts/OFL-Instrument-Serif.txt`,
`apps/editor/scripts/sync-takeone-tokens.mjs`, `apps/editor/src/styles/tokens.css`.
`git add -A` on the paths below covers the deletes.

## A — one design system

    git add apps/rehearsal/dist/takeone-tokens.css apps/rehearsal/dist/takeone-base.css \
            apps/rehearsal/dist/takeone-components.css apps/rehearsal/dist/takeone-icons.svg \
            apps/rehearsal/dist/orbit.css apps/rehearsal/dist/director.css \
            apps/rehearsal/dist/production-design/world.css apps/rehearsal/dist/voice.css \
            apps/rehearsal/dist/motor-test.css apps/rehearsal/dist/tracking.css \
            apps/rehearsal/dist/asset-library/browser.css \
            apps/rehearsal/dist/takeone.css apps/rehearsal/dist/takeone-experience.css \
            apps/rehearsal/dist/takeone-refine.css apps/rehearsal/dist/style.css \
            apps/rehearsal/dist/layout.css apps/rehearsal/dist/shot-direction.css \
            apps/rehearsal/dist/channel-editor.css apps/rehearsal/dist/fonts \
            apps/rehearsal/dist/render-profile.js apps/rehearsal/dist/asset-library/imported-set.js \
            apps/rehearsal/dist/local-perception.js apps/rehearsal/dist/takeone-experience.js \
            apps/rehearsal/tests/fixtures/css-scan.mjs \
            apps/rehearsal/tests/design-tokens.test.mjs apps/rehearsal/tests/type-scale.test.mjs \
            apps/rehearsal/tests/token-parity.test.mjs apps/rehearsal/tests/experience-ui.test.mjs \
            apps/rehearsal/tests/tracking-ui-preview.mjs apps/rehearsal/package.json \
            apps/editor/package.json apps/editor/scripts apps/editor/public/fonts \
            apps/editor/src/main.tsx apps/editor/src/styles scripts/sync-takeone-tokens.mjs

Message body should state: 15 stylesheets to 4; 205,477 B to 136,734 B; 550
colour literals to 0; 64 font sizes to 5; 176 `!important` to 0; Instrument
Serif removed. **And say explicitly** that three existing tests were rewritten
rather than deleted, because the contracts they encoded — "the experience layer
wins over page CSS" and "the palette lives at `#f4f1ea` and `#ff8a67`" — are the
exact contracts this work replaces: `experience-ui.test.mjs` now asserts the
four-file load order and the neutral ramp, and `production-design-ui.test.mjs`
asserts the phase order in one definition instead of a link in one page's
header. Also note the one token added beyond §3.2: `--t1-pulse: 1200ms`,
because §3.9 mandates a 1.2 s rolling pulse and no other file may define a
duration. The §9 CSS budget of 60 KB was **not** met; see RESULTS.md.

## D — remove the offline recording test

    git add apps/rehearsal/dist/record.html apps/rehearsal/dist/record.css \
            apps/rehearsal/dist/record.js apps/rehearsal/dist/record-client.js \
            apps/rehearsal/dist/record-copy.js apps/rehearsal/dist/recording.html \
            apps/rehearsal/dist/recording.css apps/rehearsal/dist/recording.js \
            apps/rehearsal/dist/recording-client.js apps/rehearsal/tests/recording.test.mjs \
            README.md docs/ai-director/implementation/06-recording.md \
            docs/ui-unification-2026-09-14.md

All 31 blocks of `recording.test.mjs` still pass; only the import path and one
assertion message changed. No redirect stub was left at `/recording.html`
because every referrer is updated in the same change.

## B — Record page

    git add apps/rehearsal/dist/camera-source.js apps/rehearsal/dist/voice-live.js \
            apps/rehearsal/dist/takeone-phases.js apps/rehearsal/dist/takeone-shell.js \
            apps/rehearsal/tests/camera-source.test.mjs apps/rehearsal/tests/record-ui.test.mjs \
            apps/rehearsal/tests/voice-live.test.mjs

## C — iPhone capture and auto-roll

    git add packages/takeone/embodied/behavior.py packages/takeone/embodied/recorder.py \
            packages/takeone/phone/http.py packages/takeone/phone/capture.py \
            packages/takeone/recording/phone.py packages/takeone/recording/service.py \
            packages/takeone/recording/repository.py packages/takeone/recording/api.py \
            packages/takeone/recording/contracts.py apps/rehearsal/server.py \
            tests/test_embodied_observe.py tests/test_phone_routes.py \
            tests/test_recording_phone_source.py tests/test_recording_phone_adapter.py \
            tests/test_recording_plan_link.py

Message body must record the deviation in §5.5: `PhoneRecorder.request_start`
performs the device call and blocks on the camera's own `wait_recording(True)`
readback **before** returning, so the acknowledgement time it reports is
measured rather than predicted and `_poll()` needs no change. The prompt asked
for a pending attempt resolved by a later readback; this meets the reason given
(a device's acknowledgement cannot be predicted at call time) without opening
the state machine. It must also record that `tests/test_recording_plan_link.py`
now asserts `user_version == 3`, which is a genuine contract change from the
`MIGRATION_2_TO_3` §5.6 asked for.

## E — cross-phase consistency

    git add apps/rehearsal/dist/index.html apps/rehearsal/dist/director.html \
            apps/rehearsal/dist/world.html apps/rehearsal/dist/voice.html \
            apps/rehearsal/dist/motor-test.html apps/rehearsal/dist/drive-proof.html \
            apps/rehearsal/dist/drive-proof.css apps/rehearsal/dist/asset-library/browser.html \
            apps/rehearsal/dist/dev apps/rehearsal/dist/director.js \
            apps/rehearsal/dist/orbit.js apps/rehearsal/dist/orbit-robot.js \
            apps/rehearsal/dist/sequence-player.js apps/rehearsal/dist/voice.js \
            apps/rehearsal/tests/scene-edit.test.mjs apps/rehearsal/tests/production-design-ui.test.mjs \
            apps/editor/src/state/phases.ts apps/editor/src/components \
            docs/cart-movement-proof.md

## F — voice model as configuration

    git add packages/takeone/voice/provider_gemini.py packages/takeone/review/vlm.py \
            tests/test_voice_tools.py docs/voice-live-feature-09.md \
            docs/ai-director/implementation/05-rehearsal-voice.md CLAUDE.md

`CLAUDE.md` changed: the token-mint body is no longer described as unverified,
because it was exercised against the live service with a real key on
2026-09-17. Confirm that wording before committing — it is a hard-rules file.

## Evidence

    git add data/verification/record-design-20260917

## Before pushing

    scripts\TakeOne.ps1 -Command test

That is the only place `ruff`, `mujoco`, `scipy` and the editor's `vitest` can
actually run. Expect the two `.venv/bin/python` node failures to disappear on
Windows and the 66 missing-dependency Python errors to disappear with the real
environment.
