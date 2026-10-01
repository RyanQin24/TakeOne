# Visible attention and bounded Director requests — continuation checkpoint

Date: 2026-09-15. Checkout: `C:\TakeOne`, starting HEAD `3e336e55bc623a38247e3ceffd0d5576e5e48824`. Production software edits authorized; no hardware or paid model actions. This continues the existing movement-intent checkpoint and actor work rather than introducing another compiler or animation framework.

## Actual changes in this continuation

- `previs/performers.py`: interpolate the reported scene target before computing head angles; measure angular clamp error between vectors; mark a coincident head/target as unavailable instead of inventing a direction.
- `director/performers.py`: shared source takes must preserve performer tracks even when one clip has an empty track list.
- `walking-actor.js`: use ZYX head Euler order so simultaneous head yaw/pitch matches the sampled target. Tests inspect the real Three.js head world quaternion.
- `performer-samples.js`: show unavailable attention explicitly in the phone inspector.
- `director/scene_assets.py`: factor identical movement-template defaults only in the provider's copied payload. Canonical JSON equality preserves types; every resolved default, parameter bound and template remains intact.
- `director/skills.py`: newly selected authored examples explicitly carry the current appearance, empty performer and empty screen-target fields. Existing explicit values remain intact; saved user documents are not rewritten.
- New regression files: `tests/test_attention_geometry.py`, `tests/test_provider_catalog_compaction.py`, `apps/rehearsal/tests/attention-geometry.test.mjs`.
- `scripts/first_turn_demo.py`: final formatter-only correction, with identical parsed Python AST. Its benchmark behavior was not authored by this continuation.

Coordinates remain scene-local XYZ metres, Z up. Object/point targets are translated by the shot mark before sampling; sequence placement transforms the samples for rendering. Actor targets use the independently staged actor pose. Body direction, head yaw and head pitch stay separate; eyes are fixed to the head, not independently animated. Full-take timing is not renormalized at edit cuts. No prop transfer or grasp is implied by a proxy reach.

## Visible evidence

Evidence root: `data/directing-intent-continue-20260915T203355Z/`.
Open `comparison.html` there. It includes actual original/candidate phone images and `candidate-two-shot.webm`, recorded from edit 9.050 to 14.834 s. The candidate shows mutual attention and separate rust/dark clothing, then both figures look down toward the bench.

The original `cae2b2f293d9b633615fd6b0ce9fcd02ea71fbbbb64075b2875dc72c31ccbcd8` exercise remains unchanged. The separate inspected candidate reference is `91ee7242-c97b-4c4b-8eac-1b3f363372bd/99be3218d65587fb3c5efb77407ec6a814aae6d70e9e693ed526d97cc520572f`.

Original shot 2 now visibly reports authored/achieved rise of 0 mm as needing revision. The separately authored candidate requests 50 mm and achieves approximately 51.2 mm in simulation. No movement is silently renamed.

## Requests and verification

All four standard planning requests initially failed the existing 120,000-byte cap locally. The factored requests are 100,729–100,813 bytes, preserve the current skill text, and retain all existing model/token/spending settings. `unsent-requests-final/` contains exact request bytes, request-time skill/instruction hashes and a manifest. Zero requests were transmitted; no creative ablation or training result is claimed.

The final complete verifier execution (`scripts/verify.py --output-dir .../full-verification-final`) ran 833 product tests: 832 passed and one was skipped because the Windows account cannot create directory symlinks. All 29 simulation and 263 JavaScript tests passed. Browser syntax, preservation and lint passed. The command exited 1 on formatting only in `scripts/first_turn_demo.py`. That whitespace-only correction has an identical Python AST; subsequent whole-project lint and formatting checks passed (268 formatted files). Runtime suites were not rerun after the formatter-only correction. The original full-run logs were not edited to manufacture an exit-zero result.

Focused verification: 96 Python and 16 JavaScript tests passed. This continuation added 15 Python and five JavaScript tests. All 178 application Python file hashes were unchanged during the final functional verification. `changed-files.json`, `continuation-changes.patch`, before snapshots, protected-file hashes and both initial/final full-run logs preserve the evidence; concurrent asset, phone and other directing work was retained.

## Performance and remaining scope

The inspected preview ran in a real headful Edge instance on the connected Windows computer, using Intel Arc through ANGLE/D3D11 (not the available RTX 4060). One two-second sample during VP9 recording measured 23.86 preview frames/s and 1.65 ms CPU submission/frame. This is not a GPU timer, an unrecorded steady-state benchmark or evidence of a speedup. No cache/renderer rewrite was made.

The separately installed First Turn candidate was rendered and its complete 0–30 s simulated edit recorded as `first-turn-edited.webm`. It remains a fixed-tool-contact adaptation, not a transfer or screw-turn demonstration. The exact saved revision inspected still has a partial performer at the final frame edge and an inconsistent courtyard audio cue. `first-turn-review.md` records those failures; a newer generator script is not substituted for the saved revision's evidence.

Screen-space and cut-review modules added in the wider working tree are covered by the functional checks, but their visibility evidence uses sampled proxy geometry. Full rendered-mesh occlusion, text readability, meaningful prop identity, independent pupil/facial acting, actual phone optics/exposure and hardware repeatability remain unestablished. The original production and the pre-existing asset-engineering prompt were byte-preserved. No hardware readiness, completed training or creative-quality guarantee is claimed.
