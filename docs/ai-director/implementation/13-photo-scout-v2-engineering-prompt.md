# Engineering prompt: implement shot-conditioned Photo Scout in TAKE ONE

## Mission

Work in the actual `C:\TakeOne` checkout. Implement a real-photo-to-editable-rehearsal feature inside the existing Director and Shot Studio. Read `13-photo-scout-v2-research.md` and its primary sources first. The previous `12-photo-to-scene-*` documents are background; this prompt supersedes their model choice and outdated description of current clearance review.

**The product outcome is not a generated room that rotates.** A filmmaker must import a real location photo, correct its geometry, compare what the actual camera rig would film under deliberate changes, see unsupported regions, and retain an exact scene/plan/evidence revision for the shoot.

This document is an implementation assignment, not a statement that Photo Scout is already shipped.

## 1. Verify and preserve the existing product

The project changes were checkpointed to main at `1544a60facc7b53e69f41a621310b3fecb75f45f`. Verify current HEAD, branch, absolute checkout and dirty state. Do not reset to that commit or overwrite later work. Inspect `AGENTS.md`, `CLAUDE.md`, README, scoped instructions and current tests. Capture recoverable before bytes/hashes for every edited existing file. Make narrow edits against fresh contents; stop and reconcile an unexpected hash change in a shared file.

Read the current implementations before assigning responsibilities:

- `director/scenes.py`, `creative.py`, `scene_assets.py`, `studio.py`, `motion_contract.py`, `provider.py`, inventory/performer/screen contracts and loaded Markdown skills.
- `previs/sequence.py`, `scene_checks.py`, `screen_review.py`, `shot_review.py`, `travel_review.py`, `optical_candidates.py`, camera/placement/channel contracts and canonical compiler entrypoints.
- `apps/rehearsal/server.py`, authored `dist/scene-library.js`, `asset-library/*`, `orbit.js`, `render-loop.js`, `optical-path-editor.js`, `choreography-review.js`, `preview-capture.js` and `capture_preview.mjs`.
- Existing session transactions, source watching, request authorization, explicit robot preparation/approval, manifest hashes and verification launcher.

Do not create another app, HTTP framework, session owner, motion solver, robot controller or generated-code interpreter. Product logic belongs in `packages/takeone`. Keep current serial watchdogs, calibration bytes, solver fidelity, lens cues and operator approval intact. No serial ports, firmware, torque, autonomous exploration, hardware playback, paid requests or external photo transmission in automatic tests.

Run a fresh baseline against stable sources. Record the baseline HEAD and changed-source hashes. Historical reports are not evidence that this checkout passes now. Do not weaken provenance guards, skip failing product tests, or alter unrelated work to manufacture a green result.

## 2. Ship one complete vertical slice

Minimum release:

```text
real JPEG/PNG
  -> validated private capture
  -> genuine local model inference
  -> textured partial geometry with a source-pixel map
  -> operator floor, scale, orientation and object corrections
  -> immutable scene capture revision
  -> existing Director script and motion requirements
  -> existing cart/arm compiler
  -> achieved phone-camera storyboard and evidence overlays
  -> deliberate what-if edit and changed findings
```

The same photo must remain useful after its original view. One source-view reprojection does not pass acceptance. Include translated camera views, a missing-view example, a proposed object relocation and a genuine changed planning result. Manual correction is required; manual geometry alone must not be labelled automatic photo inference.

Defer automatic complete-room recovery, compulsory object generation, giant model installs, new native iOS apps, custom foundation-model training, full photorealistic relighting, and general autonomous route search. Missing future fusion may block resolution of a capture request, but must not be hidden behind a completed status.

## 3. Select and isolate inference

First benchmark candidate:

```yaml
source_repository: microsoft/MoGe
source_revision: 925b8ed835a7a9cdb7578ba15c658a0afc969030
model_class: moge.model.v2.MoGeModel
weights_repository: Ruicheng/moge-2-vits-normal
weights_revision: 26b477f41595707c5db6770294c0d1721e8ed4ed
weights_file: model.pt
published_weight_bytes: 140550416
published_weight_sha256: 79a16621928c2bf0ed04659218c55c01075e950507f40bb3332fb4c873d3e1dc
```

Explicit comparison candidate: `Ruicheng/moge-2-vitb-normal`, revision `ca5f0e07ff01d3e5a364c1d954ed12ee1814b368`, `model.pt`, 419110160 bytes, SHA-256 `16b8110e86d5dc5a849db120ca96ef3a223fd30b0c9146d1d81db504073da5f6`.

Both are declared MIT in the inspected model cards. Recheck the exact source, weights and dependency terms before vendoring. Publisher hashes are not proof a local file was verified. Download only through explicit setup from the allowlisted origin/revision; verify bytes and hash before loading. Never load arbitrary user/model-provided checkpoint paths, pickle code or arbitrary remote repositories.

Use an isolated worker environment; do not install PyTorch or model dependencies into the root simulator or LeRobot runtime. The inspected device is an RTX 4060 Laptop GPU, 8,188 MiB VRAM, driver 566.07. Recheck actual compatibility, create a resolved lock and record it. Do not upgrade system drivers as an incidental setup step. Inspect the pinned utilities and minimal runtime dependencies instead of installing upstream demos/training extras unnecessarily.

MoGe-3 is available, but newer main has a different dependency stack. Do not blindly install latest main. Compare it only after the bounded v2 pipeline works and only if measured task quality warrants the added footprint. DA3 multi-view and RoomPlan are later adapters, not prerequisites.

One inference job at a time, immutable job inputs, deadlines, bounded memory/output, cancellation and crash recovery. No torch imports at app startup/test discovery. Keep model work out of render/request-critical threads. Opening the app must not download weights. After setup, ordinary inference uses local files.

Measure load/inference/postprocess time separately, peak CUDA allocation and process memory, output validity and task-specific error on permission-cleared images. Try Small and Base at bounded resolution/token settings; choose based on results, not parameter count. A lower-resolution retry is an explicit choice recorded in provenance, never a silent provider substitution. Preserve the prior accepted scene on failure.

## 4. Preserve three independent representations

**Source evidence:** immutable original/canonical image, preprocessing, point/depth/normal outputs, validity mask, source camera and source-patch ownership. Inferred geometry remains inferred.

**Editable scene:** stable actor/object IDs, source bindings, support relationships, installed asset IDs, existing availability values, proposed placement and dimensions. Do not infer current physical availability from a photograph or a downloaded asset.

**Planning representation:** reviewed floor regions, bounded obstacle/actor proxies, scene-to-rig registration and explicit unknown regions. A visually complete proxy or generated backside cannot become observed free space.

Each property carries evidence type and source revision: measured, sensor-derived, model-estimated, operator-assumed or proposed. Availability is not a geometry-confidence field. Do not compress these distinctions into a global “scene confidence” or “safe” badge.

Changing a desired shot may change sampling priorities but must not mutate the evidence geometry. Never stretch the room, move an observed obstacle, change a measured anchor, or silently move a performer just to make a camera plan pass.

## 5. Contracts and revision graph

Define small typed contracts at boundaries; trust validated internal values rather than stacking repeated validation wrappers:

| Contract | Required responsibility |
| --- | --- |
| `CaptureSource` | Original/canonical hashes, decoded format and sizes, crop/rotation/mirror map, relevant private camera metadata, input-rights record |
| `InferenceArtifact` | Model/code/weight/worker-lock hashes, configuration, coordinate/depth convention, output hashes and actual timings |
| `Registration` | Uniform scale correction, named transforms, floor, origin/direction, anchor IDs, residuals and independent-check status |
| `SceneCaptureRevision` | Immutable evidence/artifact/annotation references, source camera, patch ownership, unknowns and derived proxy bindings |
| `ShotEvidence` | Scene/plan/camera/actor/registration versions, exact source/edit timebase, achieved optical pose, tested regions, findings and scope |
| `CaptureRequest` | Affected shot/time/region, unresolved question, suggested human observation, priority rationale, and resolution state |
| `ScoutingJob` | Bounded immutable inputs, owner/session/revision, idempotency token, status and explicit failure/cancellation/discard outcome |

Keep image/depth/mesh arrays outside script JSON. Add an optional capture reference and source bindings to the existing scene contract. Old scripts must preserve contents, validity and digest on read. New strict generation must still handle current required actor appearance, screen targets, inventory, motion requirements and curated fixtures. Never fix schema tests by deleting information.

Use existing session transactions for explicit scene promotion. A completed job is not automatically a production edit. Promotion checks expected scene/session revisions; stale work is retained as an artifact but cannot overwrite new decisions. Undo/redo creates or restores exact versions, not regenerated approximations.

Define cache dependencies narrowly:

```text
source + model/config -> inference
inference + anchors/annotations -> evidence scene
scene + authored proposed edits -> proposed scene
scene geometry + actors + lens + motion -> compiled review
visual scene + achieved camera/time -> thumbnails
```

A label, camera scrub or proposed chair move must not trigger fresh model inference. A change in relevant geometry, scale, registration, lens, actor blocking or plan must invalidate the corresponding review/approval. Do not claim an old prepared run is still valid just because its movement parameters did not change.

## 6. Private image ingress and transport

Support JPEG/PNG first. Inspect actual bytes and decoded dimensions; do not trust filename/MIME alone. Declare encoded/decoded resource limits and show a useful reduce/export message for unsupported sizes or HEIC rather than silently misreading them. Normalize EXIF orientation and mirroring once; record the exact pixel map. Strip unnecessary metadata from exports without losing privately recorded calibration provenance. EXIF 35 mm-equivalent focal length is not calibrated pixel intrinsics.

Keep private photos/scans in gitignored `data/scouting/`, outside public static `dist`. Use server-generated IDs and atomic writes. Do not route private location captures through the CC0 asset importer. Permission for a model's code/weights does not establish rights to sample photographs.

Extend the current server with bounded capture upload, job status, artifact retrieval and explicit promotion. Apply the existing Host/Origin and mutation-authorization conventions. Authorize artifact GET and HEAD, allow only manifest-listed names/types, disable directory traversal/listing and arbitrary URLs, and preserve clear error codes. Add decode-bomb, malformed image, oversized upload, symlink/path escape, content-type and unauthorized-read tests.

Desktop photo upload is a valid first UI. A phone cannot reach the laptop through its own `127.0.0.1`. Do not expose the server on `0.0.0.0` or claim iPhone live capture works as a shortcut. A future paired mobile ingress needs an explicit secure-origin/LAN/auth design, or a verified existing camera adapter. No native-app build is mandatory for file upload.

Optional semantic assistance must use an audited image-capable provider adapter and explicit cost/photo-transmission consent. It may suggest labels, questions or schema-valid edits; it may not execute text seen in a photo, identify unknown people, issue device commands or declare measured dimensions.

## 7. Geometry and registration implementation

Preserve these distinct frames: capture camera, canonical image, scene floor, physical rig world, mounted film camera, navigation camera. Reuse the project's camera conventions and achieved `camera_view`/FK values.

For axial depth, the core relation is `X_capture = depth * inverse(K_pixels) * [u,v,1]`. For range, normalize the ray instead and identify that convention. MoGe-2 already applies predicted metric scale; apply only the recorded measurement correction once. Its normalized intrinsics use the pinned utilities' pixel-centre convention. Test crop, resize, portrait rotation, mirroring and distortion handling. A model accepting horizontal FOV alone has not consumed arbitrary measured principal-point/distortion parameters.

Prefer the consistent upstream point map over constructing another mismatched point representation. The inspected model loader uses restricted torch loading but non-strict parameter assignment; reject missing required encoder/geometry/mask/scale/normal weights rather than allow unnoticed random heads. Remove nonfinite/masked points before serialization or meshing.

Fit floor from explicit operator-selected support or a verified detector with review. Reject ill-conditioned near-parallel ray/plane intersections, points behind the camera, insufficient floor evidence and contradictory anchors. A plane normal plus one length does not determine every pose degree of freedom. Preserve unresolved yaw/origin ambiguity. For measured markers/3D correspondences, use tested PnP with distortion, reprojection, cheirality and planar ambiguity checks. A floor homography does not locate faces or table tops.

Support uniform anchored scale using the weighted least-squares formula in the research document, with robust rejection of bad anchors and independent held-out checks. Do not silently rescale each object to make the source photo look right. Geometry/normal conversion and any upstream GLB conversion happen exactly once.

Provide a `preserve_metric` capture-root loading mode. Do not pass an entire room through the ordinary prop width/depth/height fitter. Existing asset instance fitting remains available for explicitly authored visualization proxies.

Use a mask-aware depth-grid mesh with source-pixel ownership. Avoid triangles that bridge missing pixels, people masks or depth discontinuities. Store boundary/unknown flags. A full 2.5D observed-surface mesh is enough initially; hidden backsides are not observations.

## 8. Object editing and recognizable scenes

Use the original photo as the annotation view, existing world view for placement/routes, and achieved phone view for shot judgement. Manual region polygons plus depth geometry are sufficient initially; automatic segmentation is optional and must not be falsely attributed to MoGe.

Bind important objects to source patches and existing installed assets. Keep observed and proposed layouts separate. Moving/deleting a bound chair in a proposed layout suppresses its original owned patch, leaves exposed background unknown, and retains the immutable evidence view. Test no duplicate “ghost” furniture and no unexplained frozen people behind avatars.

Use existing anonymous-to-named performer assignment, appearance and motion channels. A photo does not supply facial animation, joint retargeting, grasp/contact, or consent/availability of another actor. Source mesh detail and asset completion must not increase planning authority.

Keep lighting assumptions explicit: baked shadows in a photo are not relightable BRDF evidence. Preserve the light arm's current simulation/recording boundaries and manual tasks.

## 9. Add shot-specific evidence to the existing compiler

Flow through `rehearsal_manifest` and `build_program`. Use the actual achieved phone pose, lens/crop and aspect at each tested time. Reuse screen/shot/travel review and the sampled full-rig/actor/object checker now present in `scene_checks.py`. Its midpoint FK and bounding-sphere conservatism are not continuous collision certification, cable validation or measured stopping dynamics.

Maintain distinct findings for image support, cropping, proxy occlusion, nominal clearance, unknown space, registration and hardware qualification. No all-purpose pass score. A textured surface must not certify unseen floor as traversable.

For source support, project a visible novel-view surface sample back into source views; check image bounds, valid mask, depth agreement, surface/patch ownership, facing and excluded dynamic regions. Record magnification/angle limits as policy or heuristics, not calibrated confidence. Merely landing inside a source image is insufficient: the sample may be behind the originally visible surface. No geometry in a requested view means unsupported, not automatically clear or source-supported.

Use both full-frame and story-critical-region denominators. Do not inflate coverage with empty background or hide a face failure inside a high average. Attach shot ID, affected edit/source time range, region/object, tested sample count, input digests and an actionable recommendation. Contact-sheet frames must be rendered from the achieved film camera and labelled by time/revision.

## 10. Task-conditioned sampling and counterfactuals

First implement explicit A/B comparisons: same scene and actor performance, changed camera route versus lens; same camera/performance, changed proposed chair position. Only the requested variables may change. Preserve the earlier variant and show differences in achieved motion, screen regions, source support and geometric findings.

Use the existing numerical `motion_requirements` and bounded `optical_candidates` where their contracts match. Do not expand its one-to-five permitted offsets into an undocumented global route optimizer. Retain nonholonomic cart motion, five-motor camera-arm limitations, configured joints and actual controller capabilities. A required moving shot cannot be “fixed” by making the robot stationary while the actor moves or the lens zooms.

Prioritize samples near the union of modeled rig/actor sweeps and important sightlines. Retain a broad-phase whole-scene check. Use depth-to-screen sensitivity `f*abs(b)/Z^2` only as a local estimate, and explicit hypothesis testing near discontinuities or ambiguous occlusions. Task priority allocates observation/computation; it must not pull inferred geometry toward a convenient answer.

If adding a conditional temporal lower-bound diagnostic, implement and test the research formula `min_sample_distance - geometric_error_bound - relative_speed_bound*sample_gap/2`. Its premises require complete bounded geometry, endpoint coverage, valid relative motion bounds and finite uncertainty. Include angular/articulated motion. Missing bounds return unknown. Keep it labelled conditional and separate from hardware approval; do not mislabel the current midpoint sampler as continuous proof.

Cheap local edits update affected scene/query dependencies, not the neural scene estimate. No per-frame model calls, unbounded optimizer loops or dense all-to-all recomputation.

## 11. Targeted next-observation guidance

Create a `CaptureRequest` when unknown geometry can change a route, framing or occlusion decision. Highlight the region and explain the question, e.g. “The floor behind this chair is not observed; this reveal passes that boundary.” Suggest a human photograph/measurement that could resolve it.

Use a transparent bounded heuristic over unseen task-region coverage, predicted visibility, viewpoint diversity and capture effort. Evaluate more than one plausible geometry hypothesis where useful. Do not present the score as calibrated entropy reduction or a probability of safety. Avoid pure-rotation-only advice for resolving ambiguous depth.

Suggested capture positions must lie on already reviewed accessible floor; do not plan autonomous robot exploration. If multi-view alignment is not implemented, the UI must say so and leave the request unresolved. Later DA3 or RoomPlan ingestion must produce a registered new evidence revision with explicit scale/pose/overlap checks, not a loose overlay of separately scaled meshes.

## 12. Director, UI and resource ownership

Load original captured-location/shot-conditioned guidance into the existing generation assembly, not only a Markdown file. Preserve live-voice budgets. Send bounded scene facts, inventory, measurements, source/scene revisions, unknowns, relevant installed asset choices and the current rig capability contract; not raw depth arrays or the whole library.

Generate purpose, attention and coverage before choosing movement. Use independent performer beats, meaningful props, varying durations and continuity. Do not require every shot to be cluttered or moving. Keep one deliberate demonstration where the actor and cart move simultaneously and the phone arm contributes measurably, checked from achieved states against numerical requirements declared before evaluation.

Add Import location photo and scene review to the existing surfaces. A helper inspector alone does not complete the task. Existing productions, shot editing, rehearsal, recording guide and export must continue to work. The film camera, not navigation zoom, owns storyboard and lens evidence.

Inference progress, stale/cancelled results, unsupported inputs and load errors must remain visible without destroying the last accepted scene. Reference-count shared geometry/textures, release obsolete instances exactly once, reject late loads after scene switches, and invalidate both views through `render-loop.js` when geometry/overlays finish loading. No unconditional render loops or allocations in hot posing paths.

Starting configurable budgets: one neural job, a processed image long edge around 1,024 pixels, a roughly 100,000-triangle visual mesh, at most a 2,048-pixel texture long edge, and bounded low-resolution thumbnail jobs. These are development targets, not measured performance or safety thresholds. Account for decoded textures, mipmaps, copies, vertices and framebuffer allocations; compressed source bytes are not GPU memory. Visual LOD must not silently simplify planning geometry.

## 13. Suggested module ownership

```text
packages/takeone/scouting/
  contracts.py           capture/evidence/registration/query contracts
  ingest.py              private images and canonical pixels
  repository.py          immutable artifacts and job records
  geometry.py            projection, masks, planes and anchored scale
  worker.py              isolated inference entrypoint
  adapters/moge2.py       pinned model-output boundary
  bridge.py              current scene/session integration
  review.py              view support and task-region queries
  service.py             bounded jobs, cancellation and promotion
apps/rehearsal/dist/photo-scout.js
apps/rehearsal/dist/photo-scout.css
configs/photo-scout.json
requirements-scout.lock.txt
```

Treat these as responsibility boundaries, not a demand for empty scaffolding or dozens of defensive wrappers. Combine small modules where clearer. Reuse existing asset, rendering, scene and solver functions instead of duplicating them.

## 14. Acceptance tests: separate mathematical and empirical evidence

**Math/geometry:** use the supplied `photo_scout_geometry_proof.py` as a research reference, then add production tests through real interfaces. Test axis asymmetry, handedness, known scale, normalized intrinsics, crop/rotation/mirror maps, axial depth versus range, floor degeneracy, bad anchors, double scale/conversion, mask holes, missing surfaces and depth-discontinuity bridges. Source-view roundtrip alone is insufficient. Scale-distorted scenes must demonstrate identical source views but different translated views.

**Actual inference:** execute a pinned model on a real permission-cleared photo; record source rights, model/config hashes, validity, memory and time. Do not substitute a mock download or handcrafted mesh. A synthetic fixture tests geometry, not a real model. If no appropriate photo is available, request that input rather than inventing a venue measurement.

**Application loop:** upload -> local inference -> correction -> immutable save -> reload -> Director scene -> canonical compilation -> actual browser world/phone rendering -> A/B difference -> invalidated old review. Include source-ownership masking after prop moves, unchanged originals, repeatability, legacy digests, unknown IDs, stale jobs and transaction conflicts.

**Evidence:** source support cannot be claimed for a point behind an observed surface or an unseen floor. An unknown bound stays unknown. Changing only the navigation camera must not change film plans, thumbnails' camera parameters or physical lens cues. Required motion cannot be satisfied by edit cuts, setup time, navigation motion or digital zoom. Original-view fit and fitting anchors are not held-out evaluation.

**Runtime/security:** unauthorized GET/HEAD and mutations, private-path escape, image bomb, missing/corrupt weights, offline setup state, timeout/OOM, interruption, repeated scene changes, demand rendering and release of shared resources. Preserve previous accepted state on failure. No automatic paid calls or device use.

**Product value:** create a separate authored real-location study, preserving the user's productions. Compare photo/chat advice, manual floor sketch, manual 3D staging and Photo Scout using the same brief, images, measurements, rig constraints and budget. Measure setup time, intervention count, held-out scene/screen error, incorrect confident predictions and per-session cost. Report sample sizes and failure cases. No invented success rate, style score or percentage improvement.

## 15. Implementation order and stop gates

A. Verify checkout and stable baseline; audit the isolated inference boundary and run one genuine image. Do not build success-looking UI ahead of a working worker.

B. Integrate image ingress, partial evidence mesh, source view, floor/scale/orientation correction and immutable scene references into the existing app. Obtain achieved phone-view frames, not a separate viewer screenshot.

C. Add bound object patches, observed/proposed layouts, A/B shot comparison and missing-evidence findings. Preserve original reality while allowing explicit creative changes. This is the minimum useful product slice.

D. Bind Director instructions, numerical movement intent, real storyboard capture, guide export and revision-specific preparation/review metadata. Verify no hardware route can consume stale scene assumptions as fresh approval.

E. Add task-weighted adaptive sampling and targeted capture requests; evaluate them against uniform sampling and generic “take more pictures” guidance. Add multi-view fusion or another model only when the measured failures justify it.

After each gate, capture actual evidence and repair regressions before proceeding. Do not stop at a library loader, paper summary, disconnected prototype or mock geometry. An external-input blocker must be named precisely while completed upstream functionality remains usable.

## 16. Final deliverables

Run focused tests, the real local browser workflow and `scripts/TakeOne.ps1 -Command test` on stable sources. Keep historical reports and save this run's command, exact counts, failures and source hashes separately. Distinguish baseline defects, concurrent changes and your regressions. Never claim a full pass from selected tests.

Update README only with shipped behavior. Deliver before/after mapping, exact paths, runtime/model/asset provenance, source-image rights, new demonstration URL, achieved phone-view evidence, resource measurements, cost records, remaining unknowns and reproducible commands. Keep private photos/weights/browser profiles out of Git. Do not change robot approval, calibration or live control.

The successful result is an **editable filming experiment tied to evidence and the real rig**. No part of this assignment authorizes calling a single-photo estimate a perfect digital twin or a physically certified plan.
