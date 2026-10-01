# Extensible visual assets and ensemble direction

Implementation prepared 2026-09-15 against inspected checkout
`3e336e55bc623a38247e3ceffd0d5576e5e48824`.

## Source ownership

| Existing component | Integration change |
| --- | --- |
| `director/scenes.py` | Catalog merges existing procedural choices with installed models. Asset IDs are bounded strings, checked against the registry. |
| `director/scene_assets.py` | Model selection, asset-reference validation and bounded brief-specific prop shortlist. |
| `director/provider.py` | Uses that shortlist and generation-only scene-dressing instructions. Records the digest of actual transmitted instructions. |
| `scene-library.js` | Keeps its existing procedural and actor paths; imported models use a separate layer. |
| `asset-library/asset-loader.js` | Generic local glTF loading, independent skeleton clones, shared resources and explicit authored dimensions. |
| `asset-library/imported-set.js` | Coordinates asynchronous scene replacement and visible loading/failure status. |
| `director.js` | Adds a model-browser link; its existing scene editor consumes the expanded catalog. |
| `server.py` | Watches asset-library Python changes through the existing idle restart gate. |
| `pyproject.toml` | Packages the new Markdown instruction file. |
| `apps/rehearsal/package.json` | Syntax-checks the new browser modules; existing test discovery includes new math/cache tests. |

New objects are imported catalog data, not new renderer conditionals. The 21 existing
procedural objects remain deliberate options and old productions keep their IDs.
The single-call Director does lexical asset retrieval before generation; it is not
a new autonomous web-browsing agent, an embedding search service or a model trainer.

## Coordinates, ownership and evidence

glTF Y-up data is converted with `(x,y,z) -> (x,-z,y)`. Its visual bounds are centered,
then scaled along TAKE ONE's Z-up axes to the authored `size_m`, then rotated by the
instance yaw and translated by `position_m`. Source geometry is not modified. Flat
or malformed bounds cannot be silently stretched into a valid three-dimensional box.
This is visual fitting, not real-world measurement or physical collision qualification.
The existing scene checks still use authored geometric envelopes, not full mesh contact.

Imported assets are outside the procedural disposal traversal. The cache shares source
geometry/materials, clones skeletons and releases instance leases. Its default 64 MiB
limit concerns encoded source dependencies, not measured GPU allocation; max entries
is 64. Obsolete scene loads cannot commit to a newer scene. Decode cancellation is
not a WebGL performance guarantee. Loading failure stays visible rather than drawing
a generic box and claiming success. Occlusion and detailed contact remain unverified.

## Script behavior

Scene-dressing guidance uses the existing `design.beats` contract. It asks for distinct
performer intentions, motivated props, varied shot purposes and continuity. It does
not require clutter or constant camera movement. Imported character previews are not
a rig-retargeting implementation. Supporting performers keep the existing proxy
animation limits; facial acting, sitting and object contact remain on-set directions.

The instruction file is appended only for new creative plans, not to the fixed-size
live voice persona and not to line-only assistance. A digital model never proves a
physical prop or performer is available. Location notes must distinguish confirmed
inventory, proposed dressing and visualization-only references.

## Sources and reuse

The selected starter manifests refer to Kenney Furniture, Food, Nature and Blocky
Characters pages and their stated CC0 licenses. Imported snapshots retain origin,
license information, local content hashes and dependency records. No live downloads
were completed in the authoring session. The importer refuses unknown archive paths,
missing dependencies and unsupported external model URLs.

Primary reference documentation:
- https://threejs.org/docs/pages/GLTFLoader.html
- https://threejs.org/docs/pages/module-SkeletonUtils.html
- https://kenney.nl/assets/furniture-kit
- https://kenney.nl/assets/food-kit
- https://kenney.nl/assets/nature-kit
- https://kenney.nl/assets/blocky-characters

## Installation and verification boundary

The guarded installer ships with the integration package. It captures original bytes,
checks every changed anchor before writing and records hashes. Unexpected local edits
stop installation. It does not change calibration, device drivers, torque, firmware or
saved productions. The separate `scene_assets_demo.py --install` command creates a new
explicitly authored rehearsal, never a replacement for the user's current production.

Only isolated tests were executed while preparing the package. The current Windows
application was not patched: terminal execution and a code-write request were blocked.
After applying the package, run the supplied full verification command, inspect actual
WebGL output and the new rehearsal diagnostics. Successful tests cannot establish
physical readiness, cinematic quality, or live tracking performance.
