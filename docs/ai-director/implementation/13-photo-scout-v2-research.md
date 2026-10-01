# Photo Scout v2: reconstruct only what the shot needs

**Status:** researched design and synthetic mathematical checks, not an installed photo-reconstruction feature. Prepared after the requested project checkpoint was pushed to `main` as `1544a60facc7b53e69f41a621310b3fecb75f45f`. The repository's earlier `12-photo-to-scene-*` documents remain historical context; this decision supersedes their model-selection and current-integration statements where they differ.

## 1. Product decision

Build an **editable, evidence-linked filming scene**, not an image-to-imaginary-world generator. Start from one photograph, infer the visible geometry, and let the requested shots determine which uncertainties need another photograph, measurement, or operator decision.

The proposed promise is: **“See what your actual robot would film, change the setup, and inspect what that prediction depends on.”** A scene that rotates attractively but never changes a filmmaking decision has not delivered that promise.

The differentiator is a loop:

```text
photograph + recorded measurements
    -> visible-surface estimate + editable object/actor bindings
    -> frozen evidence revision + explicitly proposed layout
    -> Director's story and motion requirements
    -> existing cart/arm compiler
    -> achieved phone-camera views and task-specific findings
    -> compare a deliberate change OR request the missing evidence
```

“Shot-conditioned” means **prioritize observation, meshing and review for the intended shot**. It must never mean distorting reconstructed geometry to make a requested move appear possible. Geometry fitting uses image/measurement evidence, not a reward for collision-free motion.

This is an original TAKE ONE integration proposal built from established geometry and planning ideas, not a claim to have invented a new reconstruction theorem, proven a patentable method, or outperformed another product.

## 2. What the supplied repositories actually contribute

### Twirl

At `fe1c6d0f3cede00b951e886319e45f624febb23e`, the inspected backend sends text and optional image material to an Anthropic model and extracts parameters/OpenSCAD. A browser worker runs OpenSCAD and returns binary STL. The useful pattern is **semantic request -> editable parameters -> deterministic geometry**. It is a CAD-generation workflow, not a measurement of a room. Repository metadata did not identify a license; do not vendor its source without resolving reuse permission. [S1]

### Vibe Draw

At `c75689df6d59ee1931d81e776863757299710a64`, selected drawing content is rasterized. One path requests Three.js code; another requests an image-to-3D TRELLIS task. The backend points to PiAPI. The interface adds results to an editable scene. Its repository metadata identifies AGPL-3.0. Useful ideas are selection-local editing, persistent object identity and iterative scene composition. Do not copy its application, generated-code execution, or assume a hosted service is free because the client source is public. [S2]

### What TAKE ONE should do differently

Generate no novel 3D object by default. Estimate the visible scene once; use installed models for editable visual substitutions and explicit proxies for geometry. Put difficult effort into camera/actor choreography, evidence support, registration, and reproducible changes. A model generation service can remain an optional artistic tool, never a source of measured hidden surfaces.

## 3. The honest answer to “why not send the picture to ChatGPT?”

ChatGPT can interpret images and help with composition. OpenAI's image-input documentation also describes spatial-localization and image-resizing/metadata limitations. That is not a reason to call language models useless at filmmaking. [S3]

The case for simulation is operational: a persistent scene, timed performers, an actual rig model, numerical lens/pose behavior, repeatable alternatives, and evidence about what changes between alternatives. An assistant connected to these same tools could operate them. The product is the system underneath the conversation, not an exclusive ability to understand a photo.

For a static talking-head shot in a clear room, advice and a simple floor sketch may be enough. Keep a quick planning mode. Require the simulator to earn its extra setup through moving shots, reveals, multiple actors, obstruction, or repeat takes.

The research literature includes cinematographic control systems such as CineMPC, which relate composition and camera variables. Its drone-specific controller is inspiration, not a replacement for TAKE ONE's ground-cart/arm compiler. [S4]

## 4. Three representations with different authority

| Representation | What it owns | What it must not claim |
| --- | --- | --- |
| Source evidence | Original image, canonical-pixel transform, inferred point map, masks and source-patch IDs | A complete observed room or a measured surface merely because it looks plausible |
| Editable production scene | Objects, actors, relationships, authored placements and installed asset IDs | That a digital prop exists on location, or that an edited layout already exists physically |
| Planning model | Explicit proxy bounds, reviewed floor, registration, unknown regions and their provenance | That photo texture, inferred backsides, or an uncalibrated confidence score establishes clearance |

Availability (`unconfirmed`, `present`, `proposed`, `virtual_only`) and geometric evidence are independent. An object visible in an old photo can still have unconfirmed current availability. One measured width does not make its height, depth or placement measured.

When a chair is moved in a proposed layout, hide the original chair's owned mesh/texture patch in that layout. Expose the uncovered background as unknown. Keep the source image immutable. The same rule avoids frozen photographed people coexisting with moving avatars. Generative inpainting, if added later, remains a separately marked appearance layer.

Baked photographic lighting is not measured reflectance or a relightable material model. Do not evaluate the light arm's real effect from a texture that already contains shadows. Use existing qualitative lighting previews or separately measured capture evidence.

## 5. Model selection and cost policy

The actual Windows device reports an **RTX 4060 Laptop GPU, 8,188 MiB VRAM, driver 566.07**. This was queried, not inferred from a model's parameter count. No weights were downloaded and no model was run during this task.

### Default experiment: MoGe-2 Small, then Base only when useful

Benchmark `Ruicheng/moge-2-vits-normal` first; retain `Ruicheng/moge-2-vitb-normal` as an explicit quality mode. Upstream lists 35M and 104M parameters respectively, with metric geometry and normals; both model cards declare MIT. These are predicted metric values, not independent physical measurements. Smaller weights are a reason to benchmark, not proof of adequate accuracy or a guaranteed speedup. [S5–S7]

The publisher metadata inspected for `model.pt` gives:

| Candidate | Weight repository revision | Published bytes | Published SHA-256 |
| --- | --- | ---: | --- |
| MoGe-2 Small Normal | `26b477f41595707c5db6770294c0d1721e8ed4ed` | 140,550,416 | `79a16621928c2bf0ed04659218c55c01075e950507f40bb3332fb4c873d3e1dc` |
| MoGe-2 Base Normal | `ca5f0e07ff01d3e5a364c1d954ed12ee1814b368` | 419,110,160 | `16b8110e86d5dc5a849db120ca96ef3a223fd30b0c9146d1d81db504073da5f6` |

These are **publisher records**, not locally verified downloaded files. Start from the inspected MoGe-2 source revision `925b8ed835a7a9cdb7578ba15c658a0afc969030`; audit and lock the separate inference environment before installation. The pinned project declares additional dependencies, including utilities with their own Git pins. Do not treat the two model hashes as a complete environment lock. [S8]

### Important update: MoGe-3 exists

The current official README at source revision `74fbce054ebed49800de42d0ad0e83495065719a` reports MoGe-3 released and lists weights, rather than “coming soon.” Its default installation now brings a different dependency stack, including CUDA-13-oriented uv configuration and FlexGEMM/Triton dependencies. MoGe-3 Large's published checkpoint is about 1.48 GB. Keep it as a later benchmark candidate, not an automatic driver/environment upgrade on this laptop. [S5, S9]

### Deferred alternatives

| Option | Appropriate use / reason not to make it the first dependency |
| --- | --- |
| DA3-Base or DA3-Small | Candidate for two-to-six overlapping views and joint pose/depth estimation. These checkpoints are Apache-2.0; they do not supply metric scale in the same way as the metric variant. Larger/nested checkpoints have different noncommercial terms. Do not independently place monocular meshes and call that fusion. [S10] |
| Apple RoomPlan | Optional scanned-room import using camera/LiDAR and parametric structures. Requires a capture sweep on supported hardware and an import/conversion path, not one-photo inference. [S11] |
| TRELLIS | Optional generated hero prop; upstream documents Linux-oriented setup and at least 16 GB GPU memory. Not the core representation of a real venue. [S12] |
| SAM 3D Objects | Optional object reconstruction later; the official default setup specifies Linux and at least 32 GB VRAM. Do not promise that setup on the current laptop. [S13] |
| Apple SHARP | Appearance-oriented research alternative. Current model terms restrict use to research and expressly exclude product development; do not make it the product default under those terms. [S14] |

The intended steady-state cost is **one local geometry inference per changed source/configuration**, plus optional explicitly budgeted semantic assistance. Object edits, camera scrubbing and repeated views should not call an image-generation service or rerun depth inference. Local electricity, inference time, development, storage and the Director's optional existing API calls still have costs. No claim of measured lower total cost is established yet.

## 6. Mathematics that serves the product

The equations below are design derivations. The supplied standard-library proof checks selected special cases on synthetic numbers. It is not a reconstruction, uncertainty calibration or robot test.

### 6.1 One source image cannot validate metric depth

For camera intrinsics K and positive axial depth Z:

\[
\tilde p=(u,v,1)^T,\qquad X_c=ZK^{-1}\tilde p,
\qquad X_s=R_{s\leftarrow c}(sX_c)+t_{s\leftarrow c}.
\]

Use axial depth, not Euclidean range. MoGe-2's inference already applies its learned metric scale and can output infinities outside its validity mask. Apply only the separately recorded measurement correction s. Its intrinsics are normalized; preserve the pinned pixel-centre convention when converting them. The upstream non-strict state-dictionary load needs required-head coverage checks. [S6, S8]

The projective identity is:

\[
\pi(KX)=\pi(K\lambda X),\quad\lambda>0.
\]

Thus a perfectly matching source view can coexist with wrong room scale. In the authored experiment, scaling a scene by 1.3 preserves the source projection, yet moving the camera 0.30 m produces **34.62 pixels** of error for a point truly 2 m away at f=1,000 pixels. An attractive source-view screenshot is not a geometry acceptance test.

With predicted anchor lengths d_i, measured lengths L_i and positive weights w_i, one simple positive-scale fit is:

\[
 s^*=\frac{\sum_i w_i d_iL_i}{\sum_i w_i d_i^2}.
\]

This solves the stated weighted least-squares problem; robust fitting is needed for mistaken correspondences. Reject empty/degenerate anchors. It corrects one scale parameter, not arbitrary local distortions.

### 6.2 Registration is more than scaling

For a world ray C+td and floor n^T X+b=0:

\[
 t=-\frac{n^TC+b}{n^Td}.
\]

Near-parallel rays are ill-conditioned; negative t points behind the camera. A floor normal does not fix yaw, origin and scale. Use explicit operator anchors/direction, or known 3D-to-image correspondences with intrinsics and distortion via PnP. Planar marker solutions need ambiguity and cheirality checks. A floor homography only maps points on the floor. [S15]

Keep capture-camera, scene, rig-world, mounted film-camera and navigation-camera transforms separate. Changing the navigation view must change no filmmaking evidence. Never anisotropically fit an entire reconstructed room through the ordinary prop-size fitter.

### 6.3 The reason camera movement differs from zoom

For a lateral camera translation b, focal length f in pixels and scene depth Z:

\[
 \Delta u=-fb/Z,
 \qquad |\Delta u_1-\Delta u_2|=f|b|\left|1/Z_1-1/Z_2\right|.
\]

The authored example at depths 2 m and 5 m, b=0.30 m and f=1,000 pixels gives **90 pixels of relative parallax**. A focal-length change cannot create this depth-dependent translation for points on the same original image ray. This illustrates optical translation, not a command for the differential-drive cart to strafe.

Sensitivity to depth error is approximately:

\[
 |\delta u|\approx\frac{f|b|}{Z^2}|\delta Z|.
\]

At 1 m versus 5 m, equal depth error has a **25-fold difference in screen sensitivity** for that setup. Refine or measure a nearby occluding chair edge before spending computation on a distant wall. Near depth discontinuities, first-order approximations can fail: evaluate multiple plausible hypotheses and expose ambiguity.

### 6.4 Task regions, not uniform reconstruction detail

Given a proposed plan, form two distinct regions:

\[
 \Omega_{task}=\Omega_{rig\ sweep}\cup\Omega_{actor\ sweep}\cup\Omega_{sightlines}.
\]

The first two concern occupancy; the last concerns image prediction. Use conservative boxes/capsules, existing rig geometry, a spatial index and sparse time samples. Region priority can combine minimum clearance, image sensitivity and whether uncertainty could change the chosen shot. Preserve a coarse whole-scene representation; do not discard unrelated obstacles from planning just because they are outside the photo crop.

When uncertainty is unbounded, return **unknown**, not zero uncertainty. An inferred confidence mask is not a calibrated probability that a point lies within a centimetre.

### 6.5 A conditional temporal bound, not a safety certificate

If distance between complete represented shapes is L-Lipschitz in time, maximum sample spacing is h with both endpoints covered, and all relevant geometric/registration errors are bounded by e, then:

\[
 d_{true}(t)\ge\min_k d_{sample}(t_k)-e-Lh/2.
\]

L must cover the actual changing articulated geometry, actors and relevant obstacles; cart translation speed alone is insufficient. This provides a testable reason to adapt temporal sampling. Unknown surfaces, unbounded human motion or absent error bounds invalidate this certificate's premises.

The synthetic test uses sampled distance 0.25 m, e=0.07 m and L=1.2 m/s: h=0.20 s gives a 0.06 m conditional lower bound, whereas h=0.50 s gives -0.12 m. No input here is a measured property of TAKE ONE. The current application has sampled checks, not this continuous guarantee.

### 6.6 Freeze reality; optimize only permitted decisions

Let q(t) be the actual base/arm state, a(t) actor blocking, and f(t) the intended lens/crop. Candidate costs can combine normalized screen-region error, occlusion, unknown-region exposure, optical tracking residual, movement smoothness and setup work. Evaluate costs on **achieved** camera poses from the existing compiler.

Retain differential-drive constraints:

\[
 \dot x=v\cos\psi,\qquad\dot y=v\sin\psi,\qquad\dot\psi=\omega.
\]

Begin with explicit comparisons and bounded existing candidates, not a new giant optimizer. Hard constraints and required movement precede soft cost ranking. A low-cost stationary camera cannot replace a required tracking move; changing actor positions or physical furniture needs an explicit proposed edit. The renderer cannot assign the phone arm an arbitrary unsupported six-degree-of-freedom pose.

### 6.7 Ask for the observation that can change the decision

For candidate human capture position v, use a transparent heuristic such as:

\[
 score(v)=\sum_j w_j\,unseen_j\,predictedVisibility(j,v)\,baselineQuality(j,v)
 -\lambda\,captureEffort(v).
\]

Weights emphasize unresolved rig-route/sightline regions and disagreement among plausible scene hypotheses. This is a heuristic priority, not calibrated mutual information. Another view from essentially the same optical centre may provide little depth information. Suggest positions on already reviewed accessible floor and ask the human to capture; never drive autonomously into unknown space.

The first release can issue a truthful annotated capture request before multi-view fusion exists. It must not mark that request resolved until the new evidence has actually been ingested, aligned and checked, or explicitly measured by the operator.

## 7. Integration audit against the current checkout

The requested checkpoint includes `director/motion_contract.py`, `previs/optical_candidates.py`, `previs/travel_review.py`, optical-path editing and preview capture. Use them; do not build a second camera planner.

In particular, the current `scene_checks.py` is more capable than the older research described: it now includes time-matched full modeled-rig bounding-sphere checks with midpoint FK, in addition to the nominal 0.55 m cart-footprint screen. Its own scope still excludes continuous swept guarantees, cables and physical qualification. Extend evidence inputs and unknown handling without silently upgrading that claim.

The existing `optical_candidates.py` accepts one-to-five explicitly allowed base offsets within +/-0.3 m for an already authored optical path. Reuse it only for matching requests; do not advertise it as general autonomous route planning. Preserve existing `motion_requirements`, actor channels, lens cues and explicit application of a candidate.

Use `director/studio.py:rehearsal_manifest`, `previs/sequence.py:build_program`, scene inventory, the installed asset catalog and the same world/film renderer. Add private capture artifacts and revision references, not bulk images in scripts. Keep inference isolated from root/LeRobot imports and the render loop.

## 8. Acceptance: demonstrate a changed filming decision

Create a separate permission-cleared location exercise. Start with a photo and show its partial geometry, known/estimated/unknown overlays and a measured anchor when one is actually supplied. Stage two performers and identify a real nearby obstacle.

Compare a fixed-camera zoom, a physical camera move and a deliberate reveal, preserving unedited facts. Include at least one explicitly designed interval with actor and cart movement and meaningful phone-arm participation, verified through achieved-state evidence. Do not force movement into every shot.

Move a chair in a proposed layout. Show changed screen/route findings, the removed original patch and the newly unknown background. Undo must restore the exact earlier revision. Ask for an unseen angle; expose which assumption prevents reliable preview and request the specific missing observation. Then export the plan, source/scene revisions and remaining conditions.

Compare four equal-information baselines: photo/chat advice; a manual floor sketch with rig constraints; manual 3D staging; Photo Scout plus the simulator. Measure setup effort, correction count, predicted crop/occlusion events against independent frames, scene error on held-out measurements, total cost and failure cases. Do not give the system richer inputs than the baseline. Source-view reprojection and alignment anchors are not held-out accuracy tests.

The simulator's value is a hypothesis until this experiment shows useful decisions or fewer corrections. No percentage improvement, model inference time, GPU budget or photorealism benchmark is claimed here.

## 9. Delivery in this research task

`photo_scout_geometry_proof.py` ran **24 tests with zero failures/errors in each of the research and actual Windows environments**. The Windows results and interpreter record are preserved in `docs/ai-director/research/photo-scout-v2/`. These check projection, scale ambiguity, ray/plane degeneracy, parallax, selected support rules and conditional temporal bounds. They do not test model inference, image reconstruction, current application integration or physical operation.

The companion engineering prompt specifies the production implementation. No Photo Scout provider was installed and no image was sent to a paid service in this task.

## Primary-source index

- **S1:** [Twirl inference](https://github.com/martin226/twirl/blob/fe1c6d0f3cede00b951e886319e45f624febb23e/backend/llm/core.py), [OpenSCAD worker](https://github.com/martin226/twirl/blob/fe1c6d0f3cede00b951e886319e45f624febb23e/frontend/public/worker.js), [repository metadata](https://api.github.com/repos/martin226/twirl).
- **S2:** [Vibe Draw conversion](https://github.com/martin226/vibe-draw/blob/c75689df6d59ee1931d81e776863757299710a64/frontend/app/lib/vibe3DCode.tsx), [backend routes](https://github.com/martin226/vibe-draw/blob/c75689df6d59ee1931d81e776863757299710a64/backend/app/api/routes.py), [repository/license](https://github.com/martin226/vibe-draw).
- **S3:** [OpenAI image-input limitations](https://help.openai.com/en/articles/8400551-chatgpt-image-inputs-faq).
- **S4:** [CineMPC](https://arxiv.org/abs/2401.05272).
- **S5:** [Current MoGe source and model table](https://github.com/microsoft/MoGe/tree/74fbce054ebed49800de42d0ad0e83495065719a).
- **S6:** [MoGe-2 paper](https://arxiv.org/abs/2507.02546), [pinned v2 inference](https://github.com/microsoft/MoGe/blob/925b8ed835a7a9cdb7578ba15c658a0afc969030/moge/model/v2.py).
- **S7:** [Small model](https://huggingface.co/Ruicheng/moge-2-vits-normal/tree/26b477f41595707c5db6770294c0d1721e8ed4ed), [Base model](https://huggingface.co/Ruicheng/moge-2-vitb-normal/tree/ca5f0e07ff01d3e5a364c1d954ed12ee1814b368). Publisher file hashes were also read from the corresponding Hugging Face model APIs with `blobs=true`.
- **S8:** [Pinned MoGe-2 environment declarations](https://github.com/microsoft/MoGe/blob/925b8ed835a7a9cdb7578ba15c658a0afc969030/pyproject.toml).
- **S9:** [MoGe-3 Large weights](https://huggingface.co/Ruicheng/moge-3-vitl/tree/184008f877d7ad1ad4c2cd2182a9bd1f63d0e5be).
- **S10:** [Depth Anything 3 per-checkpoint capability and license table](https://github.com/ByteDance-Seed/Depth-Anything-3#-model-cards).
- **S11:** [Apple RoomPlan](https://developer.apple.com/augmented-reality/roomplan/).
- **S12:** [TRELLIS official installation and scope](https://github.com/microsoft/TRELLIS).
- **S13:** [SAM 3D Objects default setup](https://github.com/facebookresearch/sam-3d-objects/blob/main/doc/setup.md).
- **S14:** [SHARP model terms](https://github.com/apple/ml-sharp/blob/main/LICENSE_MODEL).
- **S15:** [OpenCV PnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html).
