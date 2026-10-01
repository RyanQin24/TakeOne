# 08 · Extensible scene assets — integration handoff

Date: 15 September 2026. Status: additive toolkit, NOT an integrated local release.

## What was inspected

The connected `Zwc-11/TakeOne` main snapshot was read through GitHub. Relevant
files: root AGENTS.md and README.md; packages/takeone/director/scenes.py;
apps/rehearsal/dist/scene-library.js and the import map in index.html. The indexed
search snapshot referenced bc44fe4b7f856c46c81a92886db07b78d619ecfd.

That snapshot has an OBJECTS dictionary and asset_id enum in scenes.py, and
per-type mesh branches in scene-library.js. The user's pasted local report lists
21 objects and seven atmospheres, more than the inspected files. The current
Windows working tree was not accessible. Do not replace it with these older files.
No GitHub commit, Windows write, paid generation, or hardware action was performed.

## Implemented in this kit

A standard-library Python package imports selected CC0 packs into immutable local
snapshots, reads glTF/GLB metadata, preserves dependent buffers/textures, records
source/license evidence, hashes model and dependency bytes, and supports catalog
search, retrieval, and integrity verification. Asset identity includes path and
content revision. Different revisions coexist; re-imports are idempotent. There
are no per-asset Python classes or renderer branches.

The Kenney provider reads the selected official landing page and resolves its
actual ZIP link. It does not guess a download URL. Downloads require HTTPS on an
approved host, have size/time limits, and preserve provenance. The provider's live
network path has NOT run here; its pipeline was exercised with a mocked network.
A changed website or multiple links produces an actionable import-zip error.

A separate Three.js loader clones skeletal hierarchies, keeps shared source
resources alive while instances use them, converts Y-up to Z-up, distinguishes
center and feet anchors, and supports independent animation mixers. It has a
bounded source-byte cache and rejects undeclared required extensions. AssetLayer
prevents stale async loads from entering a different scene. Imported model errors
are visible errors, not silent generic cubes.

An independent library browser uses the existing /vendor/ import map from the
inspected index.html. After local install/import it is intended to be available at
/asset-library/browser.html through the existing simulator server. It loads only
a selected model, displays provenance and nominal dimensions, previews actual
clips, and copies a pinned reference. The browser and loader received syntax
checks, NOT a live WebGL integration test. Directory serving and vendor paths must
be checked against the current local build.

A scene-dressing skill and a scene recipe are included. Neither is automatically
loaded into the Director. The recipe is planning data, not a valid executable
rehearsal script in the current application schema.

## Required integration into the current local app

1. Read the current AGENTS.md, README, newest shot-language record, schemas,
   scene conversion, runtime routes, source watcher, and browser lifecycle first.
   Snapshot or commit local work. Do not restore the older GitHub main files.

2. Expose two read-only Director tools backed by AssetCatalog:
   search_scene_assets(query, kind, limit=12) and get_scene_asset(asset_id, sha256).
   Return only a small candidate set, with dimensions_status and provenance.
   This toolkit does not register these tools into the existing LLM automatically.

3. Retain all current procedural IDs and their behavior. Change only the external
   asset selection branch of the schema: accept the namespaced lib: identifier
   as a string with a reasonable length bound, and validate it against the local
   registry at runtime. Do not put thousands of IDs into a fixed enum or prompt.
   Older productions must still parse. A missing ID or hash mismatch must fail
   with a specific repair request. Add an explicit schema version for any new
   fields rather than silently dropping them through strict conversions.

4. Persist asset_id, sha256, instance/object ID, transforms, anchor convention,
   nominal dimension evidence, physical-presence state, and collision evidence.
   Preserve the same IDs across shots. The imported registry is not a measured
   venue inventory. Label proposed props and virtual extras in the shooting guide.

5. Add an AssetLayer as a sibling of the existing procedural scene root. Filter
   imported objects out of the old renderer's mesh branches, but keep its labels,
   existing procedural objects, atmospheric settings, cast/cue behavior and
   current framing logic. Never let the old clear() traversal dispose geometry
   or materials owned by the shared imported-asset cache. Clear the AssetLayer
   through its own API. Await required loads before starting rehearsal time.

6. Compile one authoritative scene transform set for rendering and nominal
   obstacle checks. Source glTF is Y-up. The loader rotates +pi/2 about X:
   (x,y,z) becomes (x,-z,y), a proper rotation, not a reflection. Existing scene
   positions are center-based in Z-up metres. Feet anchoring is explicit for
   actors. Uniform scale is the default; do not stretch a person or force a mesh
   to match arbitrary size_m silently. Return achieved visual dimensions and
   resolve mismatches before committing a plan. Visual bind-pose bounds do not
   cover arbitrary skeletal animation or establish safe robot clearance.

7. For cast, preserve the current actor IDs and cue timelines. A character model
   supplies appearance and actual animation clips, not all existing face/head
   tracking controls. Use distinct skeleton clones/mixers for each person. Drive
   playback from filming time, not setup time or elapsed browser frames. Retarget
   only with verified bone mappings, rest poses, root-motion policy and contact
   tests. Keep current mannequin mode as an explicit representation choice.

8. Load the new Markdown skill through the existing instruction-loading path.
   The Director proposes story, cast objectives, set relationships and coverage;
   deterministic code resolves IDs, transforms, resource limits, and actual rig
   feasibility. Do not add an autonomous online downloader to the recording loop.
   Asset acquisition is a separate authoring/import step.

9. Run the project's real verification:
   scripts/TakeOne.ps1 -Command test
   Then inspect browser scenes and saved production reloads. Do not overwrite
   prior evidence reports. Preserve physical follow hooks as pending unless the
   user separately requests and qualifies their implementation.

## Suggested component flow

User brief + venue inventory + available performers
  -> story and interaction beats
  -> asset search (small candidate set)
  -> installed IDs and revision binding
  -> relationship/placement proposal
  -> compiled scene + nominal collision/visibility checks
  -> existing camera/cart/light solver
  -> rehearsal renderer + timed actor cues
  -> shooting guide + measured on-set validation

Library data comes from an import pipeline:
  selected free pack -> ZIP boundary checks -> glTF/dependency checks
  -> immutable local files -> searchable catalog -> generic loader.

## Blender's role

Use Blender offline for bespoke models, repairs, material baking, optimization,
and exporting glTF 2.0 / GLB. It need not be the application's second runtime.
Do not execute downloaded .blend scripts. The importer intentionally ignores
.blend, FBX and OBJ until an artist exports glTF with its buffers and textures.
Blender's glTF exporter handles the format's Y-up convention; do not manually
pre-rotate and then convert twice in the runtime. Inspect one asymmetric model
and a known-size calibration object before accepting a new source pipeline.

glTF Transform is a useful optional build-time tool for packing, inspecting,
pruning, deduplicating, simplifying and resizing. Pin any installed version.
Draco/Meshopt/KTX2 models require matching tested loader/decoder configuration.
This kit does not install these decoders, Blender, Node packages, or a GPU stack.

## Performance policy

Choose lightweight low-poly assets for the entire room and selectively replace a
few hero props with higher-detail models. Do not stream a complete photoreal asset
library at startup or push binary models into localStorage. Reuse source meshes
and materials; for many identical static copies, a tested InstancedMesh path can
reduce draw calls. That instancing path is a next integration step, not included.

The provided cache's 64 MiB default is the SUM OF ENCODED SOURCE FILE SIZES, not an
accurate GPU-memory cap. Decoded textures, buffers, skins and render targets can
cost much more. Measure renderer.info, draw calls, texture dimensions, frame-time
percentiles, decoded-memory estimates and scene-switch memory growth on the
actual laptop. Set LOD/texture budgets from those measurements. Do not call browser
slowness 'full cache' without profiling. No FPS, GPU-memory or speedup claim was
measured here. Exporting pretty models is not evidence of a faster simulator.

## Free-source roadmap

Kenney starter sources are in configs/asset-library/packs.json. Add another
reviewed Kenney landing page as data, not another renderer branch. Other CC0 packs
can use the same importer by adding metadata and importing a local ZIP.

Poly Haven provides realistic models, materials and HDRIs. Its live API is a good
future provider; use the documented API instead of scraping its website. Its
18 July 2026 notice makes standard API access free, including commercial use,
with visible Poly Haven attribution for live integrations and a unique User-Agent.
The assets themselves are CC0. Asset rights and API usage rules are distinct.
Preserve /files metadata and download all selected dependencies; do not mistake
a glTF JSON file for the entire asset. This provider is NOT implemented in this kit.

Quaternius Universal Base Characters has a free CC0 Standard download; its Source
package is paid. Rigged bases still need suitable wardrobe, animation mapping and
contact checks. Do not promise its paid source files or arbitrary retargeting for
free. A BlenderKit/Sketchfab/TurboSquid 'free' filter is not a universal redistribution
license. Verify each chosen asset before bundling it in the application.

## Local acceptance tests still required

- Import at least one real Kenney pack and record actual model/texture counts.
- Load an asymmetric object, a static prop, a textured model and two independent
  skinned instances; verify axes, scale, materials, bones and animation clips.
- Switch repeatedly between populated scenes; stale loads never reappear, shared
  resources stay valid, and memory does not grow unbounded.
- Existing 21-object/seven-atmosphere local features, object shots, supporting gaze,
  intentional reveals, silent beats and shooting-guide access remain intact.
- Add a new asset through data/import only; no changes to the renderer or enum.
- Missing IDs, altered textures, unsupported compression, invalid transforms,
  unavailable physical props and unqualified footprints are surfaced explicitly.
- Frame checks use achieved rig pose, not desired camera pose. Rehearsal animation
  does not claim facial acting, focus correctness, full occlusion coverage or
  measured physical safety unless those checks really run.

## Sources reviewed

Kenney Furniture: https://kenney.nl/assets/furniture-kit
Kenney Food: https://kenney.nl/assets/food-kit
Kenney Nature: https://kenney.nl/assets/nature-kit
Kenney Characters: https://kenney.nl/assets/blocky-characters
Poly Haven license: https://polyhaven.com/license
Poly Haven API: https://polyhaven.com/our-api
Quaternius: https://quaternius.itch.io/universal-base-characters
Three.js loading: https://threejs.org/manual/en/loading-3d-models.html
GLTFLoader: https://threejs.org/docs/pages/GLTFLoader.html
SkeletonUtils: https://threejs.org/docs/pages/module-SkeletonUtils.html
glTF Transform: https://gltf-transform.dev/cli
