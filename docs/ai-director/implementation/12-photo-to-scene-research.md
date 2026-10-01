# TAKE ONE Photo Scout: research and build decision

Research date: September 15, 2026 (Toronto). Proposed feature, not an implementation or model benchmark. The existing project checkpoint was pushed to main as `6ba3c6459c86d6b18650092ef89ffde41316ba96` before this document was written.

## Decision

Build **Photo Scout: photograph a location, turn the visible space into an editable 3D rehearsal, and test how a real camera move changes the shot**. Start with a single-photo geometry draft, not a claim of complete room reconstruction. Add measurements and further views where the requested shot needs them.

The simulator should answer: given this version of the location, these performers, this lens and our actual rig, what will the phone see throughout the move, what assumptions does that prediction depend on, and what must change before shooting?

This is a product hypothesis to validate. The defensible contribution is scene evidence, editable blocking, achieved camera motion, revision-bound review and eventual recorded-take comparison. A rotatable mesh alone is not that product.

## What the supplied repositories actually do

**Twirl**, inspected at `fe1c6d0f3cede00b951e886319e45f624febb23e`: its `backend/llm/core.py` sends description/image input to a language model and extracts parameters and OpenSCAD. Its browser worker compiles OpenSCAD through WebAssembly into STL. This is editable parametric CAD, not evidence of measured room dimensions. Borrow the structured proposal → editable parameters → deterministic artifact pattern. Do not execute arbitrary generated code. Inspected metadata did not identify a repository license; treat it as inspiration rather than permission to vendor source. [S1]

**Vibe Draw**, inspected at `c75689df6d59ee1931d81e776863757299710a64`: one conversion path sends a selected drawing image to a hosted TRELLIS task through PiAPI and receives glTF; another requests generated Three.js code. The interface composes models into an editable world and exports glTF. Its repository is AGPL-licensed. Borrow region selection, iterative correction, persistent object identity and scene composition—not its entire application stack or generated-code execution. Source availability does not make hosted inference free. [S2]

## Why not just photo chat?

ChatGPT can interpret photographs and suggest useful compositions. OpenAI also documents precise-spatial-localization and original-metadata/resizing limitations. Do not claim that an AI assistant cannot understand an image. For a static talking-head video in an open room, chat advice may be enough. [S3]

Photo Scout earns its cost when a filmmaker can change a decision and inspect the consequences: move the camera instead of zooming; keep two people visible through a move; relocate a chair; ask for an unseen angle; preserve the same setup for take two; later compare a recorded take with its rehearsal.

The distinction is operational, not a claim of superior language understanding. An assistant connected to this same scene model, solver and recording system could operate it too. The contribution is the filming system beneath that interface. CineMPC illustrates the broader approach of translating cinematographic objectives into camera/control variables, but its drone controller is not a replacement for our cart solver. [S4]

## Three representations, not one authoritative beauty mesh

**Photo evidence:** preserve the original image and camera view. Estimated visible-surface geometry plus texture provides recognizable parallax. Holes, hidden surfaces and newly exposed areas remain unknown. This is initially a partial reconstruction, not a closed scanned room.

**Editable scene:** use persistent object IDs, actors, dimensions, transforms and source-region bindings. Installed library objects can replace visual proxies, not measured reality. Reuse `availability = unconfirmed | present | proposed | virtual_only` and keep measurement/provenance separate.

**Planning evidence:** explicit obstacle proxies, inspected floor, unknown regions and registration. A texture or inferred back surface cannot establish collision-free motion. Permit creative exploration under assumptions while retaining physical qualification boundaries.

**Ghost-furniture trap:** when a chair moves, its original painted patch must not remain behind the moved proxy. Suppress the old patch only in the proposed layout and mark the exposed background unknown. Preserve the immutable observation view. Likewise, mask photographed people out of the moving rehearsal or show them only as static evidence; never leave duplicate frozen performers.

## Model and capture choices

### Default: MoGe-2 Base Normal

Recommend `Ruicheng/moge-2-vitb-normal`: 104M parameters, metric-scale geometry and normal prediction; the model card declares MIT. This is a practical first candidate, not a tested performance promise. [S5–S7]

| Item | Audited pin |
| --- | --- |
| Source | `microsoft/MoGe` |
| Source revision | `925b8ed835a7a9cdb7578ba15c658a0afc969030` |
| Source package version | `2.0.0` |
| Class | `moge.model.v2.MoGeModel` |
| Weights | `Ruicheng/moge-2-vitb-normal` |
| Weight revision | `54ad3a693e61907ea4633d13dec6ee682fa09419` |
| Published SHA-256 | `16b8110e86d5dc5a849db120ca96ef3a223fd30b0c9146d1d81db504073da5f6` |
| Published bytes | `419110160` |

The inspected Windows machine has an RTX 4060 Laptop GPU, 8,188 MiB VRAM and driver 566.07. First benchmark bounded inference in an isolated worker. Parameter count and weight-file size do not establish VRAM use. No weights were downloaded or run for this research. The source pin avoids blindly adopting later dependency restructuring; lock compatible worker dependencies rather than installing latest main into the robot environment. [S6–S7]

MoGe-2 already applies learned metric scale, returns normalized intrinsics and can mask invalid geometry with infinities. Its upstream loader is non-strict. Verify required checkpoint heads, convert intrinsics using the pinned pixel convention, remove invalid vertices and avoid multiplying by scale twice. A validity mask is not a calibrated probability of accurate geometry. [S8]

### Later options, not mandatory dependencies

| Candidate | Decision |
| --- | --- |
| DA3-Base | First multi-view candidate later. Its Apache-2.0 weights and pose/depth outputs are relevant, but several larger/nested DA3 checkpoints have non-commercial licenses. DA3Metric-Large is monocular and not the same pose-estimating model. Fuse aligned views, not independently scaled single-photo meshes. [S9] |
| RoomPlan | Useful optional measured scan input with camera/LiDAR, furnishings, surfaces, dimensions and USD/USDZ output. It requires scanning on supported hardware; it is not one-photo conversion. [S10] |
| SAM 3D Objects | Selected-object reconstruction later. Upstream default setup requires Linux and at least 32 GB VRAM, not the current 8 GB laptop configuration. Optimized deployments and their licensing need separate evaluation. [S11] |
| TRELLIS | New object generation rather than measurement of an entire venue. Documented setup requires at least 16 GB GPU memory. Reuse existing props before adding this backend. [S12] |
| Apple SHARP | Interesting Gaussian appearance for nearby viewpoints. Its released model license limits use to research and expressly excludes product development; not the product default without suitable permission. [S13] |

Generative completion may later improve visualization, but must never overwrite source evidence or silently become the collision model.

## Scale, registration and units

A single photograph does not uniquely specify hidden geometry. Under a pinhole camera, uniformly scaling the visible scene about the camera preserves image coordinates. Learned metric estimation adds priors, not a measurement. A measured length can correct global scale, not local distortion or unseen floor.

Preserve crop/orientation and use measured camera intrinsics when available. Let the operator select a floor and scale anchor. Better registration uses a known marker or surveyed 3D-to-image correspondences with intrinsics/distortion. OpenCV PnP supplies the relevant pose contract; one measured segment alone does not solve every pose degree of freedom. A floor homography applies to floor points, not elevated furniture or faces. [S14]

Keep capture-camera, scene-floor, rig-world, mounted-phone and navigation-camera frames distinct. The photo's camera is not automatically registered to the cart. For axial depth, `p_camera = depth * inverse(K) * [u,v,1]`; apply a recorded scale correction and named capture-to-scene rotation/translation exactly once. An upstream GLB may already have converted axes. Never put the whole room through per-object dimension fitting: it could become a one-metre cube or acquire non-uniform distortion.

Draft rehearsal is allowed before registration, with assumptions visible. Physical handoff remains conditional on relevant geometry, scene-to-rig registration and the unchanged hardware qualification process. A reconstructed floor does not qualify wheel slip, payload dynamics, stopping distance or arm clearance.

## Embed it in the actual project

The current scene contract already has optional legacy-compatible inventory availability. `director/studio.py:rehearsal_manifest` and `previs/sequence.py:build_program` are the integration path. Reuse `scene_assets.py`, shot/screen review, scene-library rendering and the existing on-demand render loop. Keep inference in a small new `packages/takeone/scouting/` boundary with a separate worker environment—not another app or robot controller.

The current cart obstruction check uses a nominal 0.55 m radius and does not qualify every arm sweep. The screen review uses center sightlines against oriented proxy boxes, not pixel-accurate visibility. Add source-coverage/unknown-region diagnostics without changing those claims into hardware safety assurances.

## Demonstration that proves usefulness

Use a real room and a repeatable tabletop interaction. This is a proposed experiment, not executed evidence.

1. Import a photo, display the textured scene from the source viewpoint, then translate the camera slightly to show parallax and uncovered regions.
2. Confirm floor and a measured anchor. Stage two actors and identify a real chair that may affect the route.
3. Compile a held two-shot, a physical push and a reveal. Show opening/middle/ending frames rendered from achieved phone-camera poses, with the route and assumptions.
4. Move the chair or actor as a proposed edit. Show changed framing/obstruction evidence and invalidate the old review. Do not secretly rewrite the camera to manufacture a pass.
5. Request a view around an unseen corner. Mark the unknown floor/surfaces and ask for the specific additional photograph or measurement. If fusion is not implemented, label that integration pending.
6. Export the shooting guide. Later, a supervised recorded take can test whether the predicted screen behavior matches reality.

The demonstration is valuable because a filmmaking decision is changed and checked before shooting—not merely because a model rotates.

## Fair evaluation

Compare photo/chat advice, a manually authored simulator scene and Photo Scout. Give all the same brief, photographs, rig capabilities and measurements. Record setup time, manual corrections, cost, held-out geometry error and screen-region predictions against independent viewpoints. Do not disadvantage the baseline by withholding information.

Alignment anchors are not held-out validation points. Original-view reprojection is not proof of correct depth. Test translated viewpoints, independent dimensions, missing-view cases, glass/mirrors, repeated furniture and moving people. Report actual failures and sample sizes; do not invent percentage improvements or an uncalibrated cinematic-quality score.

The product benefit is a hypothesis until measured. Ship the first slice when a real image passes through inference, correction, immutable scene binding, actual Shot Studio camera preview and one actionable changed-shot comparison. More models and photorealistic world completion are not substitutes.

## Primary sources

- **S1:** [Twirl core](https://github.com/martin226/twirl/blob/fe1c6d0f3cede00b951e886319e45f624febb23e/backend/llm/core.py), [OpenSCAD worker](https://github.com/martin226/twirl/blob/fe1c6d0f3cede00b951e886319e45f624febb23e/frontend/public/worker.js), [metadata](https://api.github.com/repos/martin226/twirl).
- **S2:** [Vibe Draw conversion](https://github.com/martin226/vibe-draw/blob/c75689df6d59ee1931d81e776863757299710a64/frontend/app/lib/vibe3DCode.tsx), [README/license](https://github.com/martin226/vibe-draw/blob/c75689df6d59ee1931d81e776863757299710a64/README.md).
- **S3:** [OpenAI Image Inputs FAQ](https://help.openai.com/en/articles/8400551-chatgpt-image-inputs-faq).
- **S4:** [CineMPC 2024](https://arxiv.org/abs/2401.05272).
- **S5:** [MoGe-2 paper](https://arxiv.org/abs/2507.02546), [pinned model table](https://github.com/microsoft/MoGe/blob/925b8ed835a7a9cdb7578ba15c658a0afc969030/README.md).
- **S6:** [Pinned MoGe worker dependencies](https://github.com/microsoft/MoGe/blob/925b8ed835a7a9cdb7578ba15c658a0afc969030/pyproject.toml).
- **S7:** [Selected model/license](https://huggingface.co/Ruicheng/moge-2-vitb-normal), [published checkpoint revision/hash](https://huggingface.co/Ruicheng/moge-2-vitb-normal/commit/54ad3a693e61907ea4633d13dec6ee682fa09419).
- **S8:** [Pinned MoGe-2 inference](https://github.com/microsoft/MoGe/blob/925b8ed835a7a9cdb7578ba15c658a0afc969030/moge/model/v2.py).
- **S9:** [Depth Anything 3 capability/license table](https://github.com/ByteDance-Seed/Depth-Anything-3#-model-cards).
- **S10:** [Apple RoomPlan](https://developer.apple.com/augmented-reality/roomplan/).
- **S11:** [SAM 3D Objects setup](https://github.com/facebookresearch/sam-3d-objects/blob/main/doc/setup.md).
- **S12:** [TRELLIS installation](https://github.com/microsoft/TRELLIS#-installation).
- **S13:** [SHARP](https://github.com/apple/ml-sharp), [model terms](https://github.com/apple/ml-sharp/blob/main/LICENSE_MODEL).
- **S14:** [OpenCV PnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html).

The companion engineering prompt defines contracts, implementation order and acceptance gates. No Photo Scout implementation, model download, paid generation, GPU benchmark or hardware trial was performed during this research task.
