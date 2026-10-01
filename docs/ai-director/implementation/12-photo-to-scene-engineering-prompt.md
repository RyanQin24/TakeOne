# Engineering prompt: Photo Scout inside TAKE ONE

## Mission and definition of done

Implement **Photo Scout** in the verified `C:\TakeOne` checkout. Convert an actual location photograph into an editable, evidence-linked rehearsal inside the existing Director and Shot Studio. The simulator must help the filmmaker compare and revise a real camera/performer setup, not merely orbit a generated mesh.

Read `12-photo-to-scene-research.md` first. This prompt describes future implementation; do not present its proposed capabilities as already shipped.

```text
real photo → local geometry inference → floor/scale and object correction
          → saved scene revision → existing Director script
          → existing cart/arm solver → achieved phone-camera frames
          → visibility/obstruction/unknown-region findings
          → deliberate edit → changed evidence and invalidated old review
```

The value proposition is **test a filmmaking change, inspect its consequences and preserve the exact plan**. Keep real source evidence, assumptions and unknowns visible. Do not replace recorded footage with generated video.

## 1. Verify workspace and baseline

The checkpoint preceding this design is `6ba3c6459c86d6b18650092ef89ffde41316ba96` on main. Verify current HEAD/status; do not reset to that commit. Preserve later work, including unrelated untracked files.

Read AGENTS.md, CLAUDE.md, README, active scene/camera/performer contracts, asset importer/loader, source watcher, configuration provenance and verification scripts. Capture recoverable originals and before hashes for touched files. Use narrow edits against freshly checked contents in shared files such as director.js, orbit.js and server.py. Reconcile unexpected concurrent edits; never overwrite them.

The latest inspected full report was failing. Run a fresh stable baseline and retain separate logs. Distinguish pre-existing failures, concurrent source changes and your regressions. Do not disable provenance guards or weaken tests for a green result. Do not reuse inherited counts.

No serial ports, torque, firmware, calibration edits, autonomous cart exploration or hardware playback. No paid model requests or photo uploads to external providers without explicit consent. Keep private captures, weights, cookies and environments out of Git. Preserve existing preflight and explicit operator authorization.

## 2. One useful vertical slice before optional systems

First release: JPEG/PNG import; real local photo-geometry inference; textured partial-scene rendering; operator floor/scale/region correction; installed asset binding; immutable scene save; existing script and motion compilation; actual phone-view storyboard frames; a changed-shot comparison; and a targeted request for missing observations.

Browser camera capture may feed the same upload contract when supported. Manual annotation is a correction path, not a substitute for real automatic inference.

Defer complete 360-degree single-photo recovery, new object generation, automatic furniture segmentation, actor retargeting, new native iOS builds, generated-code execution, new robot control, photorealistic relighting and custom foundation-model training. Do not add multiple backends before the first integrated loop works.

## 3. Audited model in an isolated worker

```text
source: microsoft/MoGe
source_revision: 925b8ed835a7a9cdb7578ba15c658a0afc969030
model_class: moge.model.v2.MoGeModel
weights_repo: Ruicheng/moge-2-vitb-normal
weights_revision: 54ad3a693e61907ea4633d13dec6ee682fa09419
weights_file: model.pt
weights_sha256: 16b8110e86d5dc5a849db120ca96ef3a223fd30b0c9146d1d81db504073da5f6
weights_bytes: 419110160
```

Inspect licenses/pins before downloading. Verify hashes, use restricted weight loading and verify required encoder, point, mask, scale and normal heads are supplied. The upstream non-strict load must not conceal randomly initialized required parameters. Reject arbitrary model URLs or executable checkpoints supplied by generated content.

The inspected machine has an RTX 4060 Laptop GPU, 8,188 MiB VRAM and driver 566.07. This does not prove compatibility or speed. Create a separate pinned inference environment after checking PyTorch/CUDA/driver compatibility. Do not change the root simulator environment, LeRobot environment or system driver. Record missing setup explicitly.

Use one bounded subprocess job at a time. No PyTorch imports at simulator startup or test discovery. An explicit setup step downloads the model; simply opening the app must not do so. After setup, ordinary inference uses local files without provider calls.

Smoke-test a real permission-cleared image. Measure model load, inference, peak memory and output validity. Trial settings: about 1,200 tokens and processed long edge at most 1,024 pixels; these are configurable starting settings, not proven thresholds. Preserve prior accepted scenes on timeout/OOM. An explicitly chosen lower-resolution retry is acceptable; undisclosed provider substitution is not. Later DA3/RoomPlan adapters are not mandatory for this slice.

## 4. Architectural ownership

```text
packages/takeone/scouting/
  contracts.py        capture, registration, evidence and jobs
  ingest.py           uploads and canonical images
  repository.py       immutable private artifacts/revisions
  geometry.py         coordinate, mask and mesh utilities
  service.py          bounded jobs, cancellation, promotion
  worker.py           isolated inference entrypoint
  adapters/moge2.py   audited model adaptation
  bridge.py           capture → existing scene/manifest
  review.py           source coverage and unknown regions
  __main__.py         offline import/inspect/verify
apps/rehearsal/dist/photo-scout.js and photo-scout.css
configs/photo-scout.json
requirements-scout.lock.txt
```

These are responsibility boundaries, not mandatory empty scaffolding. Combine small modules where clearer. Reuse asset_library, director/scenes.py, scene_assets.py, studio.py, previs/sequence.py, existing screen/shot/film review and the demand-render loop. One coordinate authority, resource owner and production bridge. No new Redis/Celery service, Next.js app, competing session owner, generated-code interpreter or motion solver.

## 5. Data contracts before UI wiring

**CaptureSource:** stable ID; original and canonical image hashes; actual format; original/canonical sizes; orientation/crop/resample transforms; available capture time and camera metadata; local ownership/usage consent. Private filesystem paths are not browser URLs.

**InferenceArtifact:** source/weight/dependency/adapter hashes; preprocessing and configuration; timings; coordinate frame; units and depth convention; mask and geometry hashes. Inferred intrinsics remain inferred. No fabricated confidence percentages.

**Registration:** named capture-to-scene transform; separate uniform scale correction; floor/gravity/direction; measured anchor and correspondence IDs; residuals and independent validation. Keep scene-to-rig registration separate. The photograph camera is not the robot camera.

**SceneCaptureRevision:** immutable source/inference/registration versions, evidence mesh, source patch ownership, unknown regions and semantic object bindings. Never replace geometry behind an ID already referenced by a script or take.

**Object evidence:** property-level provenance. Visibility in a photo, predicted dimensions, authored future position and present-day availability are different facts. Reuse `availability = unconfirmed | present | proposed | virtual_only`; do not turn it into a measurement confidence field. Confirm current physical availability through the operator, not a downloaded asset or caption.

**Job:** immutable inputs, expected production revision, idempotency key and queued/running/completed/failed/cancelled/discarded states. A completed model result is not automatically a production edit. Promotion checks all expected revisions and input hashes.

Add optional `scene_capture_ref` and evidence bindings to the existing scene schema. Old scripts without these fields retain their content, behavior and digest on read. New strict-generation schemas must include the extension correctly without breaking actor appearance, screen targets, inventory or sample fixtures. Keep bulk photo/depth/mesh bytes outside production JSON.

## 6. Image ingestion and private transport

Support JPEG/PNG first. Reject unsupported HEIC with a useful conversion message unless an audited isolated decoder is added. Normalize rotation/mirroring into a canonical image and preserve the transform. Keep necessary camera metadata privately; strip unnecessary metadata from derived exports. A 35 mm-equivalent focal length is not calibrated pixel intrinsics.

Validate decoded format, encoded bytes and decoded dimensions—not extensions alone. Initial configurable limits: 20 MiB upload, 24 megapixels decoded. Test malformed/truncated images, decompression bombs, unsupported formats, traversal, symlink escape and duplicate IDs. Store atomically under generated IDs rather than user paths.

Add routes under the existing server, such as `/api/scouting/captures`, `/api/scouting/jobs/<id>` and `/api/scouting/captures/<id>/artifacts/<name>`. Match loopback Host/Origin rules and mutation authorization. Bound image uploads separately from JSON. Authorize GET and HEAD; serve only manifest-listed artifact names/types. No directory listing or arbitrary filesystem endpoint.

Use gitignored private `data/scouting/` storage outside public static dist. Keep permission-cleared fixtures separate. Do not put user-owned location scans through the CC0 pack importer or imply their license changed. Local inference sends no photographs to external services. Optional semantic analysis via a configured provider needs explicit image-upload/cost consent and an audited image-capable adapter.

## 7. One consistent camera/geometry implementation

MoGe-2 already applies learned metric scale. Treat output as predicted metric geometry, apply only recorded measurement corrections and convert normalized intrinsics with the pinned library's pixel-center convention.

```text
capture_camera: x right, y down, z forward (OpenCV)
scene:          x/y floor, z up (TAKE ONE)
rig_world:      registered physical world, when available
film_camera:    achieved mounted phone-camera pose
orbit_camera:   navigation only, never evidence authority
```

For canonical pixels and axial depth:

```text
p_capture = depth * inverse(K_pixels) * [u,v,1]
p_scene = R_scene_from_capture * (scale_correction * p_capture) + t_scene_from_capture
```

For Euclidean range, normalize the ray and name the different convention. Prefer consistent upstream point maps; verify round-trip projection rather than reconstructing a second incompatible representation. Record inferred versus measured intrinsics, distortion handling and any adapter assumptions about principal point. Known metadata must not be advertised as fully applied when the model only accepts a horizontal field of view.

Floor registration can use an operator mask and robust plane fit. A normal alone does not establish scale, translation and horizontal direction. Resolve them with recorded anchors/direction or retain the ambiguity. For known markers or surveyed correspondences, use audited PnP/IPPE with reprojection, cheirality and ambiguity checks. A measured line only constrains scale within the estimated scene; a floor homography does not locate tabletop corners or faces.

Account for coordinate conversions already performed by upstream GLB export. Apply conversions once; transform normals consistently and test handedness. Add a `preserve_metric` capture-loading path rather than independently fitting the room to a width/depth/height box. Existing ordinary-prop dimension fitting stays intact.

Discard invalid/infinite points before meshing. Do not bridge depth discontinuities or masked holes with triangles. Preserve source-pixel/patch correspondence. Hidden space stays unknown. Flag reflective/transparent objects, stairs and unsupported floor changes rather than flattening them into convenient geometry.

## 8. Editable objects without destroying observations

Provide observed-layout and proposed-layout views. Original photos remain immutable. The operator can outline important regions, label them, correct dimensions/support, choose installed assets or an explicit proxy, and edit a proposed placement.

Manual polygons/boxes plus optional validated semantic suggestions are sufficient initially. Do not claim the depth model performs semantic segmentation. Reuse catalog retrieval and editable tags; a missing model ID fails at the existing boundary rather than silently becoming a default box.

Bind editable instances to source-image/mesh patches. Moving/removing an object suppresses its old patch only in the proposed view and exposes unknown background. Preserve the original evidence view. Never show a moved chair plus an unexplained baked-in duplicate. Never inpaint unknown background and call it observed.

Exclude photographed people from moving rehearsal or retain them only in the evidence layer. Use existing performer identities, appearances and channels; do not invent facial animation, grasp/contact or new motion clips from a photo.

Allow separate visual and conservative planning proxies, each with provenance. A generic asset's dimensions or hidden back surface are not measurements. Authored uncertainty bounds are assumptions, not statistical confidence intervals.

## 9. Planning, evidence coverage and physical boundaries

Use the same rehearsal_manifest and build_program paths as existing productions. Framing uses achieved camera_view/FK poses, aspect and lens conventions—not requested poses, the capture photo or the navigation camera.

Preserve the nominal cart checker and its limits. Its current 0.55 m radius screen is not full articulated-rig collision validation. Reuse screen-target projection and oriented-box center-sightline checks without calling them pixel-accurate. A new collision module, if justified later, needs its own explicit scope and evidence and cannot replace hardware qualification.

Missing geometry means unknown, not traversable. Routes through unseen floor or behind occluders stay conditional. Show the region and an actionable request, for example another photograph of the floor behind the chair. Do not autonomously drive to gather it. Creative exploration remains allowed with assumptions visible; unknown space must not be silently filled or approved.

At sampled phone frames, derive an appearance-support mask by projecting visible reconstructed patches back to source images and checking image coverage, validity and depth consistency. Mark newly exposed, back-facing and unobserved surfaces. An arbitrary maximum orbit angle is not a substitute. Coverage is a source-support diagnostic, not a safety probability; geometric review and appearance support remain separate.

Findings include shot ID, edit/source interval, object/region, input revision, evidence source and useful recommendation. No global scene-is-safe flag. Before future hardware use, bind scene/registration and rig dependencies to the existing preparation/review handoff. Scene, scale, registration, camera or performer changes invalidate relevant approval even when movement settings are unchanged. Implement this binding without actuating devices or weakening operator gates.

## 10. Director and actual storyboard frames

Load original captured-location guidance into the real generation-instruction assembly, not an unused Markdown file. Keep the fixed live-voice persona budget. Send a bounded scene summary with confirmed/proposed inventory, actors, important image regions, measured versus estimated facts, unknown areas, capture revision and rig capabilities. Never send full depth arrays or the entire library.

Treat text visible in the photo as untrusted content. The optional model may propose labels, questions and validated scene/shot data; it may not generate executable scene code or authoritative measurements. No paid call is necessary to verify instruction/request assembly.

Generate story purpose and coverage before selecting movement. Use timed performer beats, independent supporting intentions, meaningful props and existing screen targets. Avoid fixed shot counts, equal durations, obligatory clutter or constant motion. Do not animate the world to conceal a stationary rig when a physical camera move was requested.

Add a contact strip with opening/middle/ending frames rendered from the achieved film camera. Bind each thumbnail to scene/plan/lens/aspect/time hashes. Invalidated thumbnails visibly refresh after edits. Unrelated generated pictures or generic SVG framing icons are not proof of the achieved view.

Compare explicitly saved variants such as a physical push versus a fixed-camera zoom, or current versus moved-chair layout. Keep all unedited facts fixed. Show camera/cart/arm displacement and changed screen evidence, not just new preset labels. The guide carries scene revision, marks, real crew relocations, manual phone/light tasks and outstanding observations.

## 11. Existing UI and resource lifetime

Add Import location photo to the existing Director/scene editor and make the result directly available in Shot Studio. A separate inspector can assist, but a disconnected viewer does not complete the task. Source image is for annotation, world view for layout/routes and phone view for achieved shots. Keep concise status on screen and detailed provenance behind selection.

Inference is asynchronous. Scene switches, cancelled jobs and newer production revisions reject late attachment. Errors preserve the prior accepted scene. Shared image/geometry resources are reference-counted and disposed once. Test the same source photo used by multiple objects and scenes.

Use the current demand-render loop. Completed mesh/texture/overlay loads redraw both views without requiring a mouse movement. Thumbnail generation is bounded, not a perpetual offscreen loop. Do not put model work, network activity or large allocations in per-frame posing.

Starting visual budgets: at most 100,000 evidence-mesh triangles, a 2,048-pixel long-edge texture, bounded thumbnail resolution and one model job. Make these configurable targets, enforce post-decode resource bounds, and profile actual memory/frame time. Compressed bytes are not GPU memory. A lower-detail rendering must preserve planning geometry and disclose the visual choice.

## 12. Immutable artifacts, transactions and caches

Hash source/canonical image, model/adapter/config, annotations, registration and geometry. Reprocessing with another model creates a new revision, never new contents behind an old ID. Do not hash the entire workspace for every request. Keep scouting artifacts out of unrelated process-source checks while including geometry dependencies in scene/plan review bindings.

Split visual and geometric dependencies where appropriate. A label edit should not rerun inference. Job inputs and expected revisions stay immutable. Promotion validates scene links/assets and saves through the existing session owner, clearing obsolete approval. On conflict preserve both artifacts and return a conflict; never overwrite teammate edits. A cancelled job may finish in the subprocess but cannot be auto-promoted.

Restart recovery marks abandoned jobs explicitly and removes only their verified temporary artifacts, not originals or previous scene revisions. Provide offline inspect/verify commands for hashes and missing dependencies, without opening devices.

## 13. Acceptance tests and evidence

**Geometry:** asymmetric axis fixtures; metres, handedness and normals; normalized/pixel intrinsics; crop/rotation/mirroring; axial depth versus range; floor registration; duplicate conversion. Use exact synthetic fixtures for math and a real photo for actual inference. These are different evidence classes.

Test invalid geometry, masked holes, discontinuity bridging, PnP degeneracy and bad anchors. Keep alignment points separate from held-out measurements. Original-view reprojection does not prove depth; use translated viewpoints or independent dimensions. Correcting global scale must not turn every estimated surface into measured evidence.

**End-to-end:** upload → inference → correction → save → reload → rehearsal_manifest → build_program → actual browser rendering. Cover legacy digest preservation, current strict-generation schemas, unknown assets, private GET/HEAD, stale results, cancellation and corrupted hashes. Construct the provider request locally and prove the guidance/summary is present without sending it.

Test observed/proposed layouts: moving a chair suppresses its old patch without modifying the photo and changes the correct obstruction or view result. Moving only the orbit camera cannot alter the film plan, lens commands or storyboard. A photographed person cannot remain as an unexplained frozen duplicate.

**Filming value:** create a separately named authored demonstration, never overwrite the user's production. Compare several shots in the same location. Prove requested cart/phone-arm motion from achieved poses, not labels. Show time-specific visibility, an unseen-region case and a deliberate edit that changes evidence and invalidates old approval.

Real measurements are not available merely because this prompt requests them. Use permission-cleared images and recorded operator measurements when provided. Label synthetic measurements. An inference run on a public example is not proof of accuracy at the user's venue. Do not invent tape measurements, camera poses or recorded hardware trials.

**Operations:** test asynchronous replacement, shared textures, independent actors, repeated scene changes, thumbnail cancellation, timeout/OOM, missing weights, unsupported inputs, disabled network and renderer-context failure. Capture browser console/request failures and screenshots from the actual local server. Label software-WebGL testing; do not present it as GPU performance.

Run focused tests, then `scripts/TakeOne.ps1 -Command test` against stable sources. Preserve historical reports and save new logs/counts/exit codes separately. Explain unrelated remaining failures accurately. Do not claim a full pass when a required check fails.

## 14. Implementation order and gates

**A — Inference:** verify licenses/pins, isolated runtime, real-image execution and parsed metadata. Measure memory/time and coordinate conventions. Fix this boundary before building a UI that pretends inference succeeded.

**B — Single-photo rehearsal:** integrate upload, evidence mesh, floor/scale correction and immutable capture reference into the existing app. Render achieved phone-camera frames. Test actual inference and legacy scenes.

**C — Useful editing:** bind object/source patches, implement proposed layout, one camera/actor/prop comparison, uncertainty overlays and targeted capture requests. Verify no ghost geometry and stale-approval behavior. This is the minimum value demonstration.

**D — Director/handoff:** connect compact evidence to real instruction assembly, generate actual contact-strip frames, extend the guide and bind scene-dependent preparation/review. Preserve all hardware boundaries.

**E — Evaluation/later acquisition:** compare photo/chat, manual staging and Photo Scout on equal evidence and record manual work, held-out error and cost. Only then consider DA3 fusion, RoomPlan or selected generated props.

Do not stop at architecture or a detached mesh viewer. Do not install every deferred model instead of completing the loop. When an external input/permission is genuinely missing, report its blocked acceptance check while delivering working upstream stages; never fabricate evidence.

## 15. Final delivery

Update README with what is actually live and how to reproduce it. Record exact modified paths, recoverable before/after mapping, dependency/model manifest, sample-image rights, new-production URL, screenshots, actual test results and measured performance. Separate nominal simulation results, source-evidence support and physical qualification.

State remaining limits: unseen surfaces, scale uncertainty, proxy occlusion, missing scene-to-rig registration, unsupported phone focus/light controls, and unrun model/capture/hardware checks. Do not call the scene a perfect digital twin or certify safety. Deliver a working editable filming rehearsal with explicit evidence.

## Research references and task boundary

The companion research document contains sources S1–S14, including pinned Twirl/Vibe Draw implementations, MoGe output and weight contracts, DA3 per-checkpoint licensing, OpenCV pose conventions, RoomPlan acquisition and SHARP model terms. Implement original TAKE ONE integration; do not vendor incompatible or unlicensed source.

This prompt was prepared after the existing project checkpoint was pushed. Photo Scout itself was not implemented, installed or benchmarked during the research/prompt task.
