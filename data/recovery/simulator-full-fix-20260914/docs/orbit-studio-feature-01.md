# Orbit studio — feature 01

Implemented 13 September 2026. The user requested one reviewable feature at a time. This slice completes adjustable orbit rehearsal and stops before the multi-shot editor and AI Director integration.

## Review it

Start `scripts/TakeOne.ps1 -Command simulator` from the repository root, or invoke that script by absolute path from another working directory. Open `http://127.0.0.1:8766/`. If PowerShell refuses the unsigned launcher, run `C:/TakeOne/.venv/Scripts/python.exe C:/TakeOne/apps/rehearsal/server.py --port 8766`; do not change machine execution policy.

1. Play the default 360° orbit at a 2.5 m radius over 20 s.
2. Change the radius to 4 m. The cart path expands and its calculated speed changes.
3. Change the duration to 40 s, then try 90° and 180° sweeps and reverse travel.
4. Scrub the timestamp bar. The cart, both arms, camera and light move on one clock.
5. Compare lens presets and the top/rig views. Save and reopen the orbit, or export its timestamped FK poses.

Radius is measured from the static actor to the powered axle. The phone's distance to the face is displayed separately. The axle traces an analytical circle with tangent steering; its offset from the cart origin comes from the current rig configuration. Travel is `radius × abs(sweep)` and average speed is `travel / duration`. Smooth timing uses `3u² − 2u³`, giving a peak speed 1.5 times the average. Direction switches between forward and reverse in this ideal cart model without changing the configured hardware runtime.

The circular static-subject problem has rotational symmetry: solve both five-joint arms once, then carry that posture around the actor. This avoids accumulating wrist turns or introducing unnecessary frame-to-frame IK noise. The bounded solve prioritizes pointing and horizon, with camera height as a preference. The camera monitor uses the achieved optical site from the existing MuJoCo model. A height the arm cannot achieve produces a framing note and the achieved height; preview remains available. All ten joints retain their current configured ranges and phone wrist-roll ID 6 / light wrist-roll ID 5.

Lens presets use the iPhone 17 Pro Max's 13, 24 and 100 mm-equivalent physical cameras and 48/200 mm crop views. Intermediate values are simulated zoom framing. The 16:9 pinhole preview is an approximation of field of view, without phone-specific distortion or stabilization cropping. Source: [Apple specifications](https://support.apple.com/en-hk/125091). Camera-movement vocabulary reference: [The Pixel Farm guide supplied by the user](https://www.pftrack.com/post/types-of-camera-movement-explained).

## Scope and recovery

| Before | After |
|---|---|
| `apps/rehearsal/dist/index.html` showed the direct motor test | `/` shows the orbit studio; the exact former homepage is retained as `motor-test.html` |
| Existing `app.js`, styles and motor endpoints | Still consumed by the motor diagnostic; no diagnostic behavior is deleted |
| No interactive shot-first orbit endpoint | `GET /api/previs/orbit` describes defaults, lenses and ranges; `POST` compiles the orbit |
| Director marks orbit unsupported | Unchanged in this review slice; correcting the Director is the next independent feature |

Pre-change sources and their SHA-256 hashes are in `data/recovery/shot-studio-20260913/before.json`. New product code is in `packages/takeone/previs`; the app is its client. This feature does not modify calibration originals, derived mappings, LeRobot, firmware, torque, provider configuration or live execution. The preview export is labelled `takeone_orbit_previs` and contains settings, timestamps, joint poses, world poses, source hashes and the ideal-motion assumptions. It is not a motor command artifact.

Verification is provided by `tests/test_orbit_previs.py`, `apps/rehearsal/tests/orbit.test.mjs`, HTTP checks and browser interaction. Project-wide verification uses the existing `scripts/verify.py` runner. Results are recorded after verification in the feature evidence file.

Verification result: **11 focused Python tests and 4 orbit playback/lens tests pass**, and the complete web suite passes **104 tests**. Browser playback, radius/duration changes, partial/reverse orbit import, real file save/reopen, and 361-frame export were verified. Integrity, JavaScript syntax and Ruff lint pass. The repository-wide run remains red: core tests report four failures and three errors; legacy simulation tests report five failures and one error; six existing files require formatting. These results are recorded in `data/verification/orbit-feature-01.json` and `orbit-feature-full-tests.log`. The failures are in existing planning/simulation tests and fixture imports, outside this orbit review slice. The signed-script policy rejected the launcher, so the same verification runner was invoked directly.
