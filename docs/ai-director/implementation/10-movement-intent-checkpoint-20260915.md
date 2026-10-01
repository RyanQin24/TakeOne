# Movement intent review — slice 1 checkpoint

Production edits authorized by the user's explicit “Start implementing” request.
Checkout verified at `C:\TakeOne`, HEAD `3e336e55bc623a38247e3ceffd0d5576e5e48824`.
`E:\TakeOne` was absent. This checkpoint does not complete slices 2–4.

## Demonstrable change

Open `data/directing-intent-slice1-20260915/checkpoint.html` for before/after phone-view evidence.
The original shot 2 is still `boom_up`, with requested height 1.55 → 1.55 m and
achieved height 1.5486772509496904 → 1.5486772509496904 m. The earlier review said
`reviewable`; the integrated review now says `needs_revision` and reports
`boom_authored_no_motion`. The phone monitor, timeline assessment and shooting
 guide expose the contradiction without modifying the original exercise.

## Owned application and test changes

- `packages/takeone/previs/motion_review.py` — new sampled boom diagnostic.
- `packages/takeone/previs/shot_review.py` — call it through existing review; retain framing checks.
- `apps/rehearsal/dist/shot-direction.js` — evidence formatting and shooting-guide output.
- `apps/rehearsal/dist/orbit.js` — visible notice beneath the phone monitor and detail review.
- `tests/test_motion_review.py` — 20 targeted semantic/integration tests.
- `apps/rehearsal/tests/motion-review.test.mjs` — five evidence-formatting tests.

The standalone historical audit checker is not an application dependency or a second compiler.
No schema, movement templates, camera route, lens, calibration, provider settings or saved
production was rewritten for this slice. No dependency or engine was added.

## Timing and evidence contract

Checks use raw achieved `camera.pos`, not horizon-corrected `camera_view`.
The edit-local clock excludes setup. Shared captures retain full-take source offsets;
height keys remain normalized to the full take. The checker uses the compiler's
existing ramp/channel evaluators and the capture path's preceding-FK-sample boundary
convention. Unused source tails cannot supply missing edited motion.

Explicit camera-height keys override the named preset on their intervals, including
intentional holds or opposite-direction moves. The original template name is retained
and the override is labelled in the UI. A normal static shot is not treated as a boom.
Missing/non-finite/undersampled evidence is `unverified`, not a synthetic zero-motion pass.
The 0.001 m tolerance only identifies numerical no-ops. No smoothness, exact trajectory
tracking, measured camera accuracy or physical qualification is established.

## Verification and limitations

57 targeted tests passed, including the existing shot-design, cinematic-channel and
sequence tests. A subsequent final run passed all 20 new Python motion tests and all
five new JavaScript tests; owned Python lint/format checks passed.
The normal full verifier was invoked with a separate output directory. It was not
certified green: the product group reported a recording-finalization failure and later
stalled at the nested-repository preservation test. After approximately 20 minutes,
its owned worker was terminated to preserve output and permit later groups to proceed.
See `data/directing-intent-slice1-20260915/verification-status.json` for final group results.

A headful Edge browser used the user's Intel Arc / Direct3D11 graphics device. The
phone-view result was visually inspected. This is not a headless software-rendering
substitute. CPU render-submission and preview-frame samples are saved; GPU elapsed
time was not measured, and no performance improvement is claimed.

## Preservation and current checkout

The original `final-script.json`, `final-program.json` and pre-existing
`08-asset-scene-engineering-prompt.md` retained their recorded SHA-256 hashes.
Unrelated actor/asset/phone changes appeared during execution, including edits to
`sequence.py` and `orbit.js`. They were read and preserved, not reverted or claimed.
The isolated slice patch and `owned-after/` snapshot exclude those concurrent additions;
the reconstructed owned `orbit.js` matches this slice's last pre-concurrency write hash.
The live checkout is therefore intentionally not presented as a clean single-author diff.

The exact unsent planning request was built locally. All three current Director skill
texts were found byte-for-byte in its instructions, with request/instruction/skill hashes
saved in `unsent-instruction-check.json`. No provider call was transmitted. This proves
request construction, not model behavior or a successful paid generation.

The first slice ends here. Actor identity/attention, composition/visibility checks,
continuity review and The First Turn candidate were not implemented or qualified by
this checkpoint. No robot motion, serial access, firmware/calibration changes, phone
recording, dataset creation, paid generation or training run was performed.

### Final full-check disposition

The standard verifier was stopped after preserving available output; there is no
successful standard-runner summary. The simulation group completed 29 tests: 28 passed
and one errored because the stale-source guard detected changed planner inputs.
The full browser unit group passed 249 tests. The npm syntax wrapper stalled and was
stopped; the exact 34 declared `node --check` files were then executed directly and
all passed. That supplemental result is labelled separately.

The repository-preservation command also stalled and was stopped, so preservation
is not marked passed by the full suite. Explicit hashes still confirm the protected
original exercise files and pre-existing engineering prompt were not changed by this slice.
Direct full-tree lint found three import-order errors; full-tree formatting identified
14 files requiring formatting in other in-progress actor/screen/phone/asset work.
Those files were not reformatted here. Owned-file lint/format and the final focused
motion tests passed. All outcomes and logs are linked by `verification-status.json`.

No verification continues in the background. Re-run the full suite against a stable
checkout before calling this a release-verified build.
