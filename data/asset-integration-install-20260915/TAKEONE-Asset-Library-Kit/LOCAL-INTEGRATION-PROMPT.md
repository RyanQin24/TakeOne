# Task for the coding agent with access to C:\TakeOne

Work in the existing C:\TakeOne working tree. Read AGENTS.md, README.md, the newest
shot-language implementation/audit, and docs/ai-director/implementation/08-asset-library-integration.md.
The asset kit is additive. Do not replace current files with an older remote
snapshot. Inspect git status and preserve uncommitted work. Do not reset the repo,
delete dist, change calibration or robot drivers, activate follow hooks, run live
hardware, or make paid model calls.

Goal: make real imported GLB/glTF scene assets discoverable to the current AI
Director and renderable in the existing rehearsal, while improving multi-person
scene design. More hardcoded object types or an unconnected asset demo is not the
final goal. A new downloaded/imported asset must become usable through data and
the registry, without adding another Python enum value or JavaScript branch.

The installed kit supplies takeone.asset_library, a same-origin asset browser and
loader, and a new scene-dressing Markdown skill. It does NOT yet integrate those
into the current Director/Studio. Verify the kit against actual third-party assets
first. Run its imports/search/verify commands and inspect representative static,
textured, asymmetric and skinned assets in the browser. Record actual file counts,
licenses, source URLs, dimensions/axis findings and unavailable formats. Never
report a model downloaded until its bytes exist and its dependencies verify.

Then implement a small coherent integration:

- Register read-only search_scene_assets and get_scene_asset tools using the
  existing tool architecture; retrieve a limited candidate set, not the full
  library. Preserve legacy procedural catalog entries.
- Accept namespaced external asset IDs in the appropriate schema branch and
  validate them against installed records. Pin content revisions in saved
  productions, propagate fields through all deterministic converters, and test
  backwards compatibility. Unknown IDs must be explicit errors.
- Use a generic imported-asset rendering branch with AssetLayer isolated from
  the legacy root's disposal traversal. Preload required assets before advancing
  rehearsal time. Verify cached source ownership and stale async load handling.
- Preserve current Z-up SI coordinates, center-based scene placements, existing
  marks, achieved-camera framing evidence and rig solver. Normalize imported
  glTF axes exactly once and review nominal visual bounds separately from measured
  collision footprints. Do not silently stretch models to fit a desired frame.
- Reuse the existing current cast/cue contracts rather than inventing a parallel
  acting system. Give imported skinned instances separate skeletons and mixers.
  Do not claim facial acting, handoffs, sitting contact, root-motion mapping, or
  head-follow works just because a character model loads. Add only tested mappings.
- Load scene-dressing/SKILL.md through the existing skill loader. Make the Director
  consider available performers and physical inventory, story-relevant hero props,
  foreground/action-plane/background relationships, independent supporting actions,
  and continuity. The final design may remain sparse when that serves the story.
- Keep physical, proposed and virtual-only elements distinct. Update the shooting
  guide with props/performers the user actually needs and any setup uncertainties.

Do not mechanically copy an example recipe into the current strict production
schema. Resolve its asset queries, translate its intent into real supported
contracts, and retain all current local features: richer shot language, timed
performance beats, supporting gaze, object-only shots, silent dialogue, planned
reveals, framing validation and guide access.

Test regressions before and after. Add tests showing a newly imported asset works
without a code change; old scripts still work; missing hashes fail; two characters
animate independently; repeated scene changes do not leak/stale-load assets; and
physical-presence/clearance states are truthful. Run scripts/TakeOne.ps1 -Command test
and save new evidence without overwriting historical reports. Inspect the populated
scene in the real browser. Profile performance rather than attributing lag to
'full cache' by assumption. No hardware readiness claim from a simulated test.

Return the actual changed-file list, downloaded/usable asset inventory, confirmed
integration paths, commands and results, browser evidence, performance measurements
when available, and any remaining limitations. Distinguish fixture tests from live
provider/browser tests. Do not claim success based only on a schema field or a new
file existing on disk.
