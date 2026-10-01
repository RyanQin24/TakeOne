# Engineering prompt: extensible assets and purposeful scene direction

## Mission
Improve the existing C:\TakeOne production, not a parallel prototype. Connect a free,
data-driven 3D asset library to Director authoring, saved scripts and Shot Studio.
Preserve the September 15 shot-language upgrade and existing hardware boundaries.

## Working rules
1. Read AGENTS.md, current contracts, renderer ownership and verification commands.
2. Preserve all pre-existing edits and capture recoverable originals before editing.
3. Keep product logic in packages/takeone; keep the existing authored browser UI.
4. Never open serial ports, actuate hardware, modify calibration or run paid models.
5. Do not replace the motion solver or claim hardware safety from a visual preview.
6. Keep code direct: explicit contracts, small modules, no catch-all silent fallback.

## Asset pipeline
Use reviewed CC0 sources with source/license records and local content hashes.
Import GLB/glTF plus dependencies; reject unsafe paths and incomplete packages.
Make new models available through catalog data, not per-model Python/JS branches.
Keep the 21 procedural objects as supported legacy assets, not silent substitutes.
Use one generic GLTFLoader with shared resources and independent skeleton clones.
Specify meters, coordinate conversion, bounding-center pivot and instance dimensions.
Load only needed assets; bound cached resources and release obsolete scene instances.
Surface a missing or invalid model clearly; do not hide it behind success indicators.

## End-to-end integration
Director must discover installed assets, save their identifiers, edit scene instances,
and pass them unchanged into the same scene renderer used by the shot rehearsal.
Imported meshes are visual references; existing geometric planning bounds stay
explicit and conservative. Physical presence is not inferred from asset existence.
Existing saved productions must still validate without rewriting their digests.
The library must be accessible from the current app, not only a separate viewer.

## Richer scripts
Load original scene-dressing guidance into actual Director generation instructions.
Favor story-motivated props, foreground/midground/background and clear relationships.
Use independent supporting-performer directions, varied shot duration and coverage.
Avoid quotas that force every shot to be cluttered or every camera to move.
Separate actual location inventory, proposed dressing and visualization-only assets.
Never promise facial acting, object contact or animation clips the renderer cannot do.
Create a separate authored demonstration; do not modify the user's saved production.

## Acceptance and evidence
- Install real free models and verify their referenced files and recorded hashes.
- Verify catalog search, unknown IDs, safe imports and legacy script compatibility.
- Test asset IDs through validation, saving, studio compilation and browser rendering.
- Test transform axes/scale, asynchronous scene replacement and resource lifetime.
- Exercise the real local server and capture browser errors and visible evidence.
- Confirm model/schema instructions are present without making a paid API call.
- Run scripts/TakeOne.ps1 -Command test; record actual results, not inherited counts.
- Record exact modified paths, before/after mapping, demonstration URL and limitations.

## Delivery
Implement the integrated feature now, repair regressions, update README and provide
reproducible verification. Report incomplete work honestly. Do not substitute an
architecture-only document, mock download or disconnected prototype for integration.
