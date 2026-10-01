# Extensible assets in the existing Director and Shot Studio

Implemented in C:\TakeOne on 2026-09-15. See 08-asset-scene-status.md for the
inspected demonstration revision, actual verification and remaining warnings.
This is an application integration, not an alternative simulator.

## Runtime path

Reviewed source ZIP -> checked local import -> content-pinned catalog ->
Director scene choices and generation shortlist -> validated saved asset_id ->
existing rehearsal manifest -> scene-library.js -> generic imported model layer.

The initial installation contains 687 real Kenney models. Publisher page file
counts include other files; installation counts refer to indexed model entries.
The existing 21 procedural assets remain explicit, valid choices. An invalid
imported ID produces a validation or visible load error, never a substitute box.

## Module ownership and before/after mapping

| Path | Responsibility |
| --- | --- |
| packages/takeone/asset_library/storage.py | Local path validation, atomic JSON writes, import lock, hashes |
| packages/takeone/asset_library/inspect.py | GLB/glTF boundaries, local dependencies, animation and extension metadata |
| packages/takeone/asset_library/importer.py | Checked ZIP extraction, immutable imported revisions, catalog publication |
| packages/takeone/asset_library/providers.py | Bounded download from reviewed Kenney source pages |
| packages/takeone/asset_library/catalog.py | Catalog lookup, lexical search, defensive copies |
| packages/takeone/asset_library/__main__.py | Import, download, search and verify commands |
| packages/takeone/director/scene_assets.py | Installed choices, ID validation, bounded provider shortlist, loaded skill |
| packages/takeone/director/scenes.py | Uses catalog choices instead of a closed imported-model enumeration |
| packages/takeone/director/provider.py | Applies the shortlist and actual scene-dressing generation instructions |
| apps/rehearsal/dist/scene-library.js | Keeps procedural and imported ownership separate; legacy actor behavior remains |
| apps/rehearsal/dist/asset-library/asset-loader.js | Generic GLTFLoader, independent clones, instances and cache leases |
| apps/rehearsal/dist/asset-library/imported-set.js | Scene epochs, lazy status panel, visible failures, completion callback |
| apps/rehearsal/dist/asset-library/transform.mjs | Axis conversion and authored bounding-box fitting |
| apps/rehearsal/dist/orbit.js | Passes the existing redraw callback after asynchronous model loading |
| configs/asset-library/packs.json | Reviewed source/license records; new assets are data |
| packages/takeone/director/scene-dressing/SKILL.md | Purposeful props, spatial layers, independent beats and continuity |
| scripts/scene_assets_demo.py | Separate authored example builder, with camera review still required |
| tests/test_asset_import_boundary.py | Safe imports, dependencies, immutable revisions and hashes |
| tests/test_scene_asset_catalog.py | Legacy compatibility, choices, validation and generation context bounds |
| apps/rehearsal/tests/scene-asset-*.test.mjs | Resource lifetime and transform regression checks |

pyproject.toml packages the new Markdown skill. The app's package.json includes
new syntax checks. README documents the actual editor route and library commands.
The optional server-watcher and Director navigation-link edits were not applied.
Existing Director asset selection works without either optional edit.

## Coordinate and evidence contract

glTF Y-up becomes scene-local Z-up using (x,y,z) -> (x,-z,y). Imported geometry
is centred by its converted bounding box, then fitted to authored size_m before
applying scene position and yaw. This matches the existing centre-based object
contract. Source geometry stays unchanged so differently sized instances can
share the same resources. Source dimensions are not measured venue dimensions.
Existing planning bounds are not replaced with detailed visual triangles.

The model viewer can play actual named animation clips. Performer retargeting,
facial expressions, object contact, focus, measured collisions and hardware
qualification remain outside this visual-asset integration.

## Reproduce

Run from the checkout root:

```powershell
.\scripts\TakeOne.ps1 -Command simulator
.\.venv\Scripts\python.exe -m takeone.asset_library --root C:\TakeOne verify
.\.venv\Scripts\python.exe -m takeone.asset_library --root C:\TakeOne search "table"
.\scripts\TakeOne.ps1 -Command test
```

Use `python -m takeone.asset_library --help` for reviewed ZIP imports and provider
downloads. Do not assume an arbitrary download is CC0 because it is free.

Actual evidence and known failures are under data/asset-scenes-live-evidence/.
Browser screenshots used Chromium's software WebGL renderer because the default
headless GPU context was lost on this machine. This proves rendering, not a
hardware GPU frame-rate benchmark. Full-suite failures are preserved, not relabelled.
