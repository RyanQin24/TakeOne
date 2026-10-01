# Cinematic channels and compound routes

Implementation of the eight items in [the cinematic audit](../../cinematic-upgrade-2026-09-14.md), within work package 03. Local simulation only. This record does not mark the broader eleven-package Director programme complete.

## Observable result

The movement library has 38 presets in eight families. Director and Shot Studio share an editor for independent camera/light keys, additive aim, organic texture and cart breath. Product shots have an explicit point target and can use a script with no actors. Consecutive edit beats can use one continuous compiled take with a single setup.

### Try the saved demonstration

[Open Cinematic upgrade · product study and short cuts](http://127.0.0.1:8766/?script=f97c1163-bcec-4c9e-a0b6-07d8328051b1/45028ce5426ed743f340002fc9a0949fd709169a753593f34075f21b98db4590).

This explicitly authored local example has three studio scenes, seven shots, zero actors and a 30-second edit. The first three 0.8-second cuts share one four-second light-study take: setup is 5.48 seconds on the first clip and zero on the next two. Full rehearsal retains the unedited tail. The rehearsal clock is a lower bound of 102.68 seconds, with actual location/reset time unestimated. The example was saved through Director's movement editor and compiled again; independent light keys and capture association survived revision 2. Existing arrival productions were preserved.

For individual moves, open [Spiral](http://127.0.0.1:8766/?template=spiral) or [Highlight walk](http://127.0.0.1:8766/?template=product_highlight). Expand **Independent timing & organic drift**. Director exposes the same controls under **Edit simulator movement**.

## Recovery and source mapping

Before editing, 147 source/configuration/test files were copied and SHA-256 verified under `data/recovery/cinematic-upgrade-20260914/`. Its `manifest.json` and `git-status.txt` describe the dirty pre-upgrade workspace. This preserves the preceding scene-aware Director changes. Calibration originals and the independent LeRobot checkout were not edited.

| Before | After | Unique content preserved |
| --- | --- | --- |
| `previs/program.py` exclusive aim returns | Additive contributions plus `previs/channels.py` evaluation | Original preset formulas and numeric results |
| One shared rise interval | Independently keyed height/aim/targets; legacy interval remains a fallback | Every old height and aim parameter |
| Existing `previs/camera.py` lens keys | Same lens compiler and controls used in Director | Lens semantics, simulated horizon and manual recording distinction |
| 28 fixed routes | Ten additional presets; `previs/compound.py` produces polylines | All 28 IDs, families and defaults |
| Constant pace demand in `previs/path.py` | Optional breath/pace demand through the same forward command follower | Exact legacy commands when the new options are absent |
| Embedded .35 pace ceiling and 11-count filming step | `previs/policy.py` reads `configs/arm-execution.json` | Same limits; commissioning/live evidence gates remain separate |
| Turn-in-place reposition described as an estimate | Explicit lower-bound diagram and clock | Original idealized diagram, labelled non-executable |
| Every edit beat repeats setup | Explicit shared capture windows in `previs/capture.py` | Separate setups remain the default; complete source take is rehearsed |

## Contracts

- `channels` is a bounded mapping of named tracks, each with 2–32 `{at, value, ease}` keys. Endpoints must be 0 and 1; intermediate times strictly increase. Scalars use metres/radians/metres per second. XYZ targets are shot-local metres, independent of route rotation. Nonfinite and unknown fields are rejected.
- Camera/aim/target/light and existing lens keys use normalized filming time, excluding setup and including authored holds. Pace keys use normalized route progress. Backend metadata supplies the UI names, units and bounds.
- Added pan/tilt/roll sum with the movement preset. Texture supplies one repeatable bounded contribution; enabling it on the handheld preset does not double the same contribution. Automatic simulated horizon retains authored roll/texture.
- Explicit target keys override the locked-frame preset's default aim. Without its own target keys, the light stays aimed at the subject even while the camera's target moves into negative space. Compound arc sweeps retain the requested angle above 90 degrees; they are not silently capped.
- `cinematography` carries these settings through the strict provider contract. Old saved movement objects remain accepted. Markdown Director instructions explain timing, composition and product/follow choices; Python validates and compiles data.
- `capture` names a continuous source take and its filming start in seconds. Clips must be consecutive, use identical movement/target/mark and share a space. Their source times must adjoin. Editorial boundaries retain the preceding actual FK preview sample, with at most one preview-sample interval of display quantization. They do not create motor commands. Last-clip rehearsal includes unused source footage; edit playback trims it.
- Product-only shots use `subject_motion: none`, an empty actor ID, an object camera target and planned tracking. Scene actor lists can be empty. The renderer hides the actor and shows a procedural product/plinth. Person-follow hooks remain unimplemented, as requested in the preceding task.
- Light intensity/colour are not simulated automation channels. Vendor documentation shows manual controls and USB power, without a remote protocol. The recorded evidence explicitly distinguishes an absent integration from a claim that modification is impossible.

## Verification

Targeted checks passed before the final repository run:

- All 28 pre-upgrade settings reproduce exact hashes for selected frame motion/optical data, all arm samples and the complete cart schedule. Baseline capture: `tests/fixtures/legacy-movement-frames.json`.
- All 38 default presets pass the movement library's independent wheel integration and full arm FK checks, retain landscape filming starts and stay below 3 degrees of maximum default aim error.
- Independent timing, drawn-route overlays, invalid contracts, configured unchanged limits, quantized command slew/holds, shared setup, zero-actor Director scripts and product targets have dedicated regression coverage.
- Both preserved arrival documents compile through the final local API. [The revised five-scene arrival](http://127.0.0.1:8766/?script=5cf67270-9841-4587-98f4-f2f1b464b40e/a537943c9165524b36521620d494f672a10cbced0e3e43971d0e7183b1a3b809) has five shots, a 30-second edit, no blocked shots and no revision warnings. The original six-shot document retains its existing framing/motion warnings; compatibility does not silently rewrite its settings. Scene targets, follow stubs and location resets remain intact.
- All 207 browser tests and syntax checks pass, including shared-cut continuity, sub-second edit speed, independent key defaults and scene placement of camera/light targets.
- Twelve cinematic regressions cover the original-frame fixture, a 135-degree compound arc, independent targets on a stationary cart, bounded-rate lag diagnostics and refusal to change the motion-plan clock through a policy edit. A quick 0.1 m height change can exceed the existing arm trajectory rate; the same change over nine seconds stays below 0.3 degrees in the tested pose. The compiler reports achieved aim instead of increasing the limit.
- All ten new presets were selected and reached ready state in the running browser. Product/plinth visibility, actor hiding, foreground reveal, fractional Director timecodes, light controls, shared source windows and lower-bound reset labels were inspected. No browser console errors were observed on these workflows.

The final-code HTTP sample contains ten requests, one for each new preset default, with repository verification running concurrently: median **2.28 s**, interpolated 95th percentile **5.95 s**, range **1.24–7.49 s**, and **171–796 frames** per response. This measures the local compile endpoint through response transfer and JSON decoding; it is not an isolated performance benchmark or a browser-render latency measurement. Raw results are in `http-preview-evidence.json` and `http-latency-summary.json` under the evidence directory.

**Final root verification passed.** `scripts/TakeOne.ps1 -Command test` completed with exit code 0: **660 product tests, 29 simulation tests, 207 browser tests**, browser syntax, preservation/integrity, Ruff lint and Ruff formatting. All seven check processes returned 0. The complete 30-second edit played through all seven shots and stopped at its end without browser console errors. All 147 recovery files were rechecked against their saved hashes with no mismatches.

Final logs are preserved in `data/cinematic-upgrade-20260914/root-verification/`, with the runner console in `root-verification-final-console.txt`. The first full run found two obsolete provider fixtures, an obsolete reset-text assertion and one formatting issue; those were corrected. A subsequent run was intentionally interrupted before editing the angle/target issues found in final review. The final run above includes those fixes and their regressions. Generated reports in the repository's default `data/verification/` directory were restored after copying the final evidence, to avoid mixing generated log churn with source changes.

Other evidence in the same directory includes `browser-workflow-evidence.json`, `demonstration-final.json`, `saved-arrival-compatibility.json`, `extended-arc-http.json`, `http-preview-evidence.json`, `http-latency-summary.json` and `recovery-verification.json`.

## Reproduce

From any directory, using the existing environment:

```powershell
& C:\TakeOne\scripts\TakeOne.ps1 -Command simulator
& C:\TakeOne\.venv\Scripts\python.exe C:\TakeOne\scripts\cinematic_upgrade_demo.py --previews
& C:\TakeOne\scripts\TakeOne.ps1 -Command test
```

`--install` additionally creates a new labelled demonstration draft through the local Director API. It preserves existing productions, uses no AI provider and calls no robot execution endpoint. Without `--install`, it writes the example project and optional HTTP evidence only.

## Physical limits

Every result above is software/kinematic evidence. Wheel response, slip, braking, caster dynamics, loaded arm limits, real optical focus and exposure still need physical measurement. Pace stays at 0.35 m/s maximum and filming arm steps stay at 11 counts per 40 ms; configuring those values does not authorize an increase. The forward-only reset route and person-follow controller integrations remain unavailable.
