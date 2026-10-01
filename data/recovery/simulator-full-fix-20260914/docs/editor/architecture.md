# TAKE ONE Editor — system architecture

Status: design of record for the autonomous editing module. Written 13 September 2026 after
inspecting the existing workspace. This document is the contract the implementation follows; where
it departs from the originating specification, the departure is stated with its reason.

---

## 0. What already exists, and why it constrains this design

The inspected workspace is not a greenfield.

| Fact in the repository | Consequence for the editor |
| --- | --- |
| `packages/takeone` is **stdlib-only Python ≥3.12**. `pyproject.toml` declares `dependencies = []`; heavy packages live in opt-in extras (`simulation`, `uart`, `robot`). | The editor core must not require FastAPI, Pydantic, PyAV, librosa or OpenColorIO to import. Anything heavy goes behind an extra and behind a plugin boundary. |
| Validation is **frozen dataclasses + hand-written validators** (`fields`, `text`, `integer`, `identity` in `director/contracts.py`), not Pydantic. | The editor reuses that idiom. Schema validation is explicit, fails closed, and is unit-testable without a third-party validator. |
| The LLM adapter is **stdlib `http.client` against the Responses API with a strict `json_schema`**, no SDK, no tools, budgeted (`director/provider.py`). | The edit planner mirrors this adapter exactly, including the "input JSON is untrusted creative material" instruction and the per-request budget reservation. |
| Persistence is **SQLite with an explicit `SCHEMA` string and `PRAGMA user_version` migrations**, one transaction per state change plus its event and its command receipt (`director/repository.py`). | The editor uses the same pattern in its own database file. Operation, resulting state and receipt commit atomically or not at all. |
| The Director session FSM already contains `Phase.EDITING`, `Phase.COMPLETE` and the command action `prepare_edit`. | The editor is not a bolt-on. It is the implementation of a transition the Director already knows how to request. `ACCEPTED → prepare_edit → EDITING → COMPLETE`. |
| `apps/rehearsal/server.py` is a **stdlib `ThreadingHTTPServer`** dispatching to transport-independent API objects exposing `get(path)` / `post(path, body)`, loopback-only, with bounded request bodies. | The editor exposes `EditorAPI` with the same shape and mounts on the same server. No second web framework, no second port to explain on stage. |
| `AGENTS.md`: "no UI imports in drivers", "no hardware side effects during import/test discovery", "dependencies are lightweight and pinned", "never claim hardware readiness from a simulated test". | These map cleanly onto the editor: no renderer imports in the planner, no FFmpeg process started at import time, and a rendered preview is never reported as a rendered master. |

**The single most important existing-code fact:** the repository already separates *deciding* from
*executing* under review — the Director proposes, a deterministic compiler produces a finite plan,
and only a reviewed finite plan reaches a device. The editor is the same shape with pixels instead
of motors. That is why the spec's architectural rule (§3, "AI decides WHAT, the engine decides HOW")
is not a new idea here; it is the house style, and the design leans on it hard.

---

## 1. Departures from the originating specification

These are deliberate. Each is a place where following the spec literally would produce a worse
system.

### 1.1 Four state representations collapse to one writable structure and two pure derivations

The spec (§4, §5, §11, §40) names `EditOperation`, "Canonical Project State", `Timeline`, `EditGraph`
and `Project` as if they were peers. If `EditGraph` and `Timeline` are both independently mutable,
every operation must update both consistently, and every bug in that dual update surfaces as "the
preview does not match the timeline" — which is precisely the failure the spec is trying to prevent.

Adopted instead:

```
EditOperation[]            append-only log        ← THE ONLY WRITABLE STRUCTURE
        │  fold(state, op) → (state, patch)       pure, total, deterministic
        ▼
ProjectState               immutable snapshot     ← derived
        │  compile(state) → EditGraph             pure, deterministic, content-addressed
        ▼
EditGraph                  derived DAG            ← derived
        │  compile(graph, backend) → RenderPlan   backend-specific
        ▼
RenderPlan                 argv + filter graph
        │  execute(plan)
        ▼
Artifacts                  proxy / preview / master
```

Consequences that fall out for free:

- **Undo** is truncating the log and refolding, or applying a recorded inverse. Not bolted on (§41).
- **Replay** (§6) is folding the log prefix by prefix. The replay *is* the edit, not a re-enactment.
- **Time travel** to any point is `fold(ops[:n])`.
- **Recovery** is refolding a durable log rather than trusting a serialized blob.
- **The graph can never disagree with the timeline**, because it is a function of it.

### 1.2 The UI does not re-implement the reducer

The spec's UI section implies a client-side project store. Two reducers (one Python, one TypeScript)
drift, and drift here means the animation lies about the state — the exact failure §4 forbids.

Adopted: **the server is the only reducer.** For each executed operation the server emits

```
{ operation, project_version, patch }        patch = RFC-6902-subset JSON Patch
```

over Server-Sent Events. The client applies patches to a mirror and animates the transition between
the pre-patch and post-patch values. The client owns *animation*, never *state derivation*. SSE
rather than WebSocket because SSE is ~40 lines on `ThreadingHTTPServer`, reconnects with
`Last-Event-ID` for free, and the traffic is one-directional by nature (commands go over POST).

### 1.3 Content-addressed graph nodes, and therefore free render caching

Every `EditGraph` node id is

```
node_id = sha256(canonical_json(type, version, sorted(input_ids), params, time_range))[:16]
```

This mirrors the repository's existing `plan_id` discipline (a SHA-256 digest identifying an exact
finite plan). It yields, with no additional machinery:

- **Incremental render.** A cached artifact keyed by `node_id` is valid forever; changing a colour
  parameter invalidates only that node and its descendants. Scrubbing after a look change re-renders
  a handful of segments, not the film.
- **Determinism proof.** Two compilations of the same project produce byte-identical node ids. A
  unit test asserts this, and a visual-regression test pins ids to reference frames.
- **Honest progress.** `RenderPlanner` reports "17 of 41 nodes cached" because it knows.

This is the single highest-leverage structural decision in the design, and it is the reason the
demo feels instant.

### 1.4 A transition is an effect with arity 2, not a separate plugin type

The spec lists `TransitionPlugin` and `EffectPlugin` separately (§10). A whip, a flash and a
crossfade are all "consume N inputs over a time range, emit one output" — identical to a two-input
effect. Merging them removes a registry, an interface, a compiler path and a class of "is this a
transition or an effect?" bugs, and makes a *match cut* (which is a transition that needs both
clips' subject tracks) expressible without a special case.

`EffectSpec.arity` is `1` or `2`. That is the whole difference.

### 1.5 Plugin interfaces are cut from ten to six

Built now, because each has ≥2 real implementations today:

| Interface | Implementations at MVP |
| --- | --- |
| `EffectPlugin` | 24 primitives + 9 looks + 5 transitions |
| `AnalyzerPlugin` | probe, scenes, sharpness, exposure, colour, motion, composition, subject, beats |
| `TemplatePlugin` | 11 templates |
| `RenderBackend` | `ffmpeg` (now), `null` (test double) |
| `Exporter` | `takeone-json`, `otio-json`, `ffmpeg-master` |
| `PlannerProvider` | `heuristic` (deterministic, offline), `responses` (LLM) |

Deferred with the seam in place, not built: `GenerativeVFXPlugin` (§23), `AssetProviderPlugin`,
`FrameInterpolationPlugin` as a *plugin* (it is three enum values inside the timing compiler until
there is a third implementation), `ModelProviderPlugin` (folded into `PlannerProvider`),
`RenderBackendPlugin` for GPU. §58 forbids "unused abstract interfaces"; an interface with one
implementation and no second candidate is exactly that.

### 1.6 OpenColorIO and ACES are deferred; the colour *architecture* is not

The spec (§19) asks for OCIO/ACES. For 15 seconds of Rec.709 phone footage this buys nothing and
costs a native dependency with poor Windows wheel reliability — against `AGENTS.md`'s pinned,
lightweight dependency policy, and a real demo risk.

What matters in §19 is the *separation*, not the library. Adopted: an explicit transfer-function
pipeline with named stages, implemented over `zscale` (already built into FFmpeg 6+, present in the
verification container):

```
Input transform  (gamma → linear, via zscale transfer)
      ↓
Working space    (linear light, Rec.709 primaries)
      ↓
Technical        exposure · white balance · contrast     ← measured, per shot
      ↓
Shot match       match to the sequence reference shot    ← measured, pairwise
      ↓
Tone curve       filmic S-curve                          ← creative, shared
      ↓
Creative look    3D LUT / gradient map                   ← creative, shared
      ↓
Output transform (linear → Rec.709 gamma)
```

`ColorNode` carries `input_space`, `working_space`, `output_space` fields from day one. Swapping the
implementation for OCIO later changes one compiler, not the graph, the operations, or the UI.
Apple Log and HDR are `input_space` / `output_space` values that do not yet have a compiler entry —
they fail loudly, not silently (§44).

### 1.7 Beat tracking is implemented, not imported

`librosa` pulls `numba` + `llvmlite`: a slow import, a large install, and Windows friction, for one
function. The onset-envelope → tempogram → dynamic-programming beat tracker is ~180 lines of NumPy
and SciPy — both already pinned in the `simulation` extra — and it is deterministic, unit-testable
against synthetic click tracks at known tempi, and explainable on stage. Implemented in
`editor/audio/beats.py`.

### 1.8 Repository layout: one Python subpackage, not fourteen packages

The spec's §43 tree (`packages/editor-core`, `packages/timeline-engine`, `packages/edit-operations`,
…) assumes a workspace-aware build system. This repository has `setuptools` with a single
`takeone` package and no workspace tooling. Fourteen distribution packages would mean fourteen
`pyproject.toml` files and a dependency-resolution problem, to enforce boundaries that Python module
structure plus one import-linter test already enforce.

Adopted: `packages/takeone/editor/` with the same internal boundaries, and a **test that asserts the
dependency graph is acyclic and layered** (`tests/editor/test_layering.py`). The boundary is
enforced by a check that fails CI, which is stronger than a folder convention.

The UI is a genuine second artifact and *does* get its own app: `apps/editor/` (Vite + React +
TypeScript), separate from the existing `apps/rehearsal`.

### 1.9 The planner's default provider is deterministic and offline

§9 requires the editor core to work without AI. The design goes further: the *planner* has a
deterministic implementation (`HeuristicPlanner`) that produces a complete, watchable film from
analysis signals alone, with no network call. The LLM provider replaces individual planning stages,
not the pipeline.

This is a hackathon-reliability decision as much as an architectural one: a dead Wi-Fi network
degrades the demo from "AI-authored" to "analysis-driven", not from "working" to "broken". The
existing repository already reasons this way ("degrade gracefully rather than gamble on unstable
subsystems in front of judges").

---

## 2. Final system architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  apps/editor            React + TypeScript + Zustand + Vite                  │
│                                                                              │
│  Intent → POST /api/editor/intent                                            │
│  State  ← SSE  /api/editor/stream          (operation, version, patch)       │
│  Media  ← GET  /api/editor/media/{id}      (range requests, proxy segments)  │
│                                                                              │
│  The client applies patches and animates transitions. It derives nothing.    │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │  loopback HTTP, JSON, bounded bodies
┌───────────────────────────────▼──────────────────────────────────────────────┐
│  apps/rehearsal/server.py     EditorAPI.get / .post / .stream                │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│  packages/takeone/editor                                                     │
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐     │
│   │ PLAN LAYER          (may call an LLM; may not touch pixels)        │     │
│   │                                                                    │     │
│   │  EditingOrchestrator                                               │     │
│   │    ├ IntentInterpreter   ├ RhythmPlanner    ├ AudioPlanner         │     │
│   │    ├ FootageUnderstanding├ ColorPlanner     ├ EditValidator        │     │
│   │    ├ ShotSelector        ├ EffectPlanner    └ OperationGenerator   │     │
│   │    └ StoryPlanner                                                  │     │
│   │                                                                    │     │
│   │  emits  EditOperation[]  ─────────────────────────────────────┐    │     │
│   └───────────────────────────────────────────────────────────────┼────┘     │
│                                                                   │          │
│   Templates ──┐  Human commands ──┐  Director metadata ──┐        │          │
│               └──────────────────┬┴───────────────────────┴───────┘          │
│                                  ▼                                            │
│   ┌────────────────────────────────────────────────────────────────────┐     │
│   │ CORE LAYER          (knows nothing about AI)                       │     │
│   │                                                                    │     │
│   │   reducer.apply(state, op) ──► (ProjectState', JsonPatch)          │     │
│   │              │                                                      │     │
│   │              ├──► repository  (SQLite: one atomic transaction       │     │
│   │              │                 per op + state + receipt + event)    │     │
│   │              │                                                      │     │
│   │              └──► compile.project_graph(state) ──► EditGraph        │     │
│   └────────────────────────────────┬───────────────────────────────────┘     │
│                                    ▼                                          │
│   ┌────────────────────────────────────────────────────────────────────┐     │
│   │ RENDER LAYER        (knows nothing about operations)               │     │
│   │                                                                    │     │
│   │   RenderPlanner   → what is missing from the cache                 │     │
│   │   RenderCompiler  → EditGraph subtree → argv + filter_complex      │     │
│   │   RenderExecutor  → subprocess, progress, cancellation             │     │
│   │   ArtifactCache   → keyed by node_id; never invalidated, only      │     │
│   │                     superseded                                      │     │
│   └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│   ANALYSIS LAYER (independent, feeds PLAN; never mutates state directly)     │
│     probe · scenes · sharpness · exposure · colour · motion · composition    │
│     · subject · beats                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          FFmpeg 6+ / FFprobe
```

### Layer rule (enforced by test)

```
analysis ──┐
           ├──► plan ──► core ──► render
robot ─────┘                │
                            └──► export
```

- `core` imports nothing from `plan`, `analysis` or `render`.
- `render` imports `core` (graph types) and nothing from `plan`.
- `plan` imports `core` (to emit operations) and `analysis` (to read signals); it must not import
  `render`.
- `export` imports `core` only.

`tests/editor/test_layering.py` walks the AST of every module and fails on a violating import.

---

## 3. Module tree

```
packages/takeone/editor/
├── __init__.py                 version, public façade
├── contracts.py                validators: identity, text, integer, seconds, unit, ratio,
│                               fields, encode, enum_value  — the director idiom, extended
├── ids.py                      canonical JSON + sha256 content addressing
├── errors.py                   EditorError hierarchy; every failure names its stage
│
├── operations.py               EditOperation, OperationType, per-type parameter schemas
├── state.py                    ProjectState, Timeline, Track, Clip, MediaItem, EffectInstance,
│                               SpeedCurve, AudioEvent, Marker, Selection — all frozen
├── reducer.py                  pure fold: (state, op) -> (state, patch); one handler per type
├── patch.py                    JSON Patch subset: diff(before, after), apply(doc, patch)
├── project.py                  Project envelope, schema_version, migrations v1→v2 harness
├── library.py                  per-project media folders and ingest placement
├── repository.py               SQLite: projects, operations, events, jobs, artifacts
├── jobs.py                     bounded thread pool; Job{id,type,status,progress,stage,error}
├── api.py                      EditorAPI.get/post/stream  (transport-independent)
├── cli.py                      takeone-edit: import, analyze, plan, render, export, replay
│
├── graph.py                    RenderNode, EditGraph, validation, topological order
├── compile.py                  ProjectState -> EditGraph   (pure)
│
├── effects/
│   ├── registry.py             EffectRegistry; id+version; uniqueness enforced at import
│   ├── spec.py                 EffectSpec, ParamSpec, ValidationResult, EffectUISchema
│   ├── primitives.py           colour, film, dynamic, transform and stylise primitives
│   ├── looks.py                creative looks as primitive compositions
│   └── transitions.py          two-input xfade effects
│
├── templates/
│   ├── registry.py             TemplateRegistry
│   ├── spec.py                 TemplateSpec: required clips, params, operation program
│   └── library.py              11 templates
│
├── color/
│   ├── spaces.py               transfer functions, primaries, working space
│   ├── statistics.py           histogram, percentiles, mean chroma, skin-tone mask
│   ├── match.py                shot-matching solve (exposure, WB, contrast)
│   └── looks.py                tone curves, LUT generation (writes .cube)
│
├── timing/
│   ├── curve.py                SpeedCurve v(t): eval, integrate, time map, inverse
│   ├── easing.py               linear, ease-in/out/in-out, cubic Bezier
│   └── retime.py               time map -> segmented setpts plan; interpolation mode
│
├── audio/
│   ├── decode.py               ffmpeg -> float32 mono PCM via stdout pipe
│   ├── beats.py                spectral flux -> tempogram -> DP beat tracking
│   ├── mix.py                  volume automation, ducking, fades
│   └── events.py               AudioEvent placement and quantisation to beats
│
├── analysis/
│   ├── registry.py             AnalyzerRegistry
│   ├── spec.py                 AnalyzerSpec, AnalysisResult
│   ├── probe.py                ffprobe -> MediaProbe (duration, fps, rotation, codec, ...)
│   ├── frames.py               deterministic frame sampler (ffmpeg -> raw rgb24 pipe)
│   ├── scenes.py               shot boundaries: HSV histogram distance + adaptive threshold
│   ├── quality.py              sharpness, exposure, composition, motion, stability scorers
│   ├── subject.py              subject presence/position (OpenCV; optional model backend)
│   ├── motion.py               camera-motion classification from optical flow
│   └── cache.py                analysis cache keyed by (media_sha256, analyzer, version)
│
├── render/
│   ├── planner.py              RenderPlanner: cache diff -> ordered work list
│   ├── ffmpeg.py               RenderCompiler for FFmpeg: graph subtree -> argv
│   ├── executor.py             RenderExecutor: subprocess, -progress parsing, cancel
│   ├── cache.py                ArtifactCache keyed by node_id
│   ├── proxy.py                ProxyManager, ThumbnailCache, WaveformCache
│   └── backend.py              RenderBackend protocol + NullBackend (tests)
│
├── plan/
│   ├── orchestrator.py         phase machine: UNDERSTAND…FINALIZE, gates, degraded paths
│   ├── intent.py               IntentInterpreter -> CreativeIntent
│   ├── understanding.py        FootageUnderstanding: analysis -> ShotUnderstanding[]
│   ├── selector.py             ShotSelector: scoring, rejection reasons
│   ├── story.py                StoryPlanner: narrative slots -> shot assignment
│   ├── rhythm.py               RhythmPlanner: cut timing, speed ramps, beat alignment
│   ├── colorplan.py            ColorPlanner
│   ├── effectplan.py           EffectPlanner
│   ├── audioplan.py            AudioPlanner
│   ├── validator.py            EditValidator: references, bounds, durations, feasibility
│   ├── generator.py            OperationGenerator: EditPlan -> EditOperation[]
│   ├── schema.py               strict JSON schemas for every LLM response
│   ├── provider.py             PlannerProvider protocol; HeuristicPlanner; ResponsesPlanner
│   └── explain.py              product-level explanations (never chain of thought)
│
├── assets/
│   └── registry.py             AssetRegistry: LUTs, SFX, music, overlays; tag search; licence
│
├── export/
│   ├── native.py               .takeone.json (full project + operation log)
│   ├── otio.py                 OpenTimelineIO JSON, hand-written, no dependency
│   └── master.py               final render + container muxing
│
└── robot/
    └── adapter.py              RobotMetadataAdapter: Director/robot telemetry -> edit signals
```

```
apps/editor/
├── index.html
├── package.json                react, react-dom, zustand, vite, typescript, vitest
├── tsconfig.json
├── vite.config.ts              dev proxy → 127.0.0.1:8766; build → apps/editor/dist
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── state/
    │   ├── store.ts            Zustand: projectMirror, operations, phase, jobs, selection
    │   ├── stream.ts           EventSource client, Last-Event-ID resume, patch application
    │   ├── patch.ts            JSON Patch apply (mirror of the server subset)
    │   └── api.ts              typed fetch wrappers
    ├── components/
    │   ├── TopBar.tsx          title · phase · progress · pause · export
    │   ├── ShotPanel.tsx       ShotCard[] — ANALYZING / SELECTED / REJECTED
    │   ├── Preview.tsx         proxy playback, before/after, scrubbing
    │   ├── ActivityPanel.tsx   AI operation feed with explanations
    │   ├── Timeline/
    │   │   ├── Timeline.tsx    track rows, ruler, playhead
    │   │   ├── ClipView.tsx    clip body, trim handles, enter/trim/move animation
    │   │   ├── SpeedCurve.tsx  v(t) drawn on the clip, animated stroke-dashoffset
    │   │   ├── EffectStrip.tsx effect span over its time range
    │   │   ├── AudioTrack.tsx  waveform + beat markers
    │   │   └── Ruler.tsx       timecode
    │   ├── Inspector.tsx       decision inspector for the selected clip
    │   ├── PhaseRail.tsx       UNDERSTAND … FINALIZE with per-phase progress
    │   └── IntentBar.tsx       intent-level controls (more cinematic, faster, …)
    ├── lib/
    │   ├── timecode.ts
    │   ├── animate.ts          motion primitives; single easing vocabulary
    │   └── format.ts
    └── styles/
        ├── tokens.css          the design system, as custom properties
        └── app.css
```

```
docs/editor/
├── architecture.md             this document
├── edit-operations.md
├── edit-graph.md
├── render-engine.md
├── effect-system.md
├── template-system.md
├── ai-editor.md
├── project-format.md
├── robot-metadata.md
├── ui-design-system.md
├── adding-an-effect.md
├── adding-a-template.md
└── adding-a-plugin.md
```

---

## 4. Data flow

### 4.1 The autonomous edit

```
 user intent text ─────────────────────────────────────────────┐
 media files ──► probe ──► proxy ──► analyzers ──► AnalysisSet │
                                                        │      │
                                                        ▼      ▼
                                            EditingOrchestrator
                                                        │
    ┌───────────────────────────────────────────────────┤
    │ UNDERSTAND  IntentInterpreter + FootageUnderstanding
    │ SELECT      ShotSelector           → selections with reasons
    │ STRUCTURE   StoryPlanner           → narrative slots
    │ RHYTHM      RhythmPlanner          → cuts, ramps, beat alignment
    │ COLOR       ColorPlanner           → technical + match + look
    │ EFFECTS     EffectPlanner          → effect instances
    │ AUDIO       AudioPlanner           → music, SFX, ducking
    │ FINALIZE    EditValidator          → validated EditPlan
    └───────────────────────────────────────────────────┤
                                                        ▼
                                          OperationGenerator
                                                        │
                                             EditOperation[]
                                                        │
              ┌─────────────────────────────────────────┤ one at a time,
              │                                         │ paced for legibility
              ▼                                         ▼
        repository.append(op)                     reducer.apply
              │                                         │
              │                            (ProjectState', JsonPatch)
              │                                         │
              ├── SSE: {operation, version, patch} ─────┤
              │                                         ▼
              │                            compile.project_graph
              │                                         │
              │                                  RenderPlanner
              │                                         │
              │                      missing nodes → RenderExecutor
              │                                         │
              └───────────────► SSE: {job, progress} ◄──┘
```

The pacing between operations is the *only* cosmetic element in the pipeline, and it is honest: the
operation has already been committed when the UI animates it; the delay controls dispatch rate, not
truthfulness.

### 4.2 Render data flow

```
EditGraph                                   ArtifactCache
    │                                            │
    ├─► RenderPlanner ──► for each node: sha256(node_id) in cache?
    │                            │                       │
    │                            no                     yes
    │                            ▼                       ▼
    │                    RenderCompiler            reuse artifact
    │                            │
    │                    argv: ffmpeg -i … -filter_complex "…" -f … out.mkv
    │                            │
    │                    RenderExecutor (subprocess, argv list, never a shell string)
    │                            │
    │                     -progress pipe:1 → {frame, out_time_ms, speed}
    │                            ▼
    │                    artifact written, then atomically renamed into the cache
    ▼
preview (proxy resolution) │ master (source resolution)
```

---

## 5. EditOperation schema

```python
@dataclass(frozen=True, slots=True)
class EditOperation:
    schema_version: ClassVar[int] = 1
    operation_id: str          # canonical UUID
    sequence: int              # monotonic per project, assigned on append
    type: OperationType        # StrEnum, closed set
    phase: Phase               # which editing phase produced it
    target: Target             # what it acts on
    parameters: Mapping        # validated against the type's ParamSchema
    status: OperationStatus    # PLANNED|EXECUTING|COMPLETED|FAILED|CANCELLED
    created_utc: str
    executed_utc: str | None
    public_explanation: str    # ≤180 chars, product-level, shown in the UI
    metadata: Mapping          # provenance: planner, provider, model, analysis digests
```

`Target` is a typed discriminated reference, not a free string:

```python
Target = ProjectTarget | MediaTarget | ClipTarget | TrackTarget | EffectTarget | AudioTarget
```

Every target validates that its referent *can* exist; the reducer validates that it *does*.

### Operation types (closed set, MVP)

| Phase | Types |
| --- | --- |
| UNDERSTAND | `IMPORT_MEDIA` `ANALYZE_CLIP` `SET_INTENT` |
| SELECT | `SELECT_CLIP` `REJECT_CLIP` |
| STRUCTURE | `ADD_CLIP` `REMOVE_CLIP` `MOVE_CLIP` `SPLIT_CLIP` |
| RHYTHM | `TRIM_CLIP` `APPLY_SPEED_CURVE` `FREEZE_FRAME` `APPLY_TRANSITION` `ALIGN_CUT_TO_BEAT` |
| COLOR | `APPLY_COLOR_CORRECTION` `MATCH_COLOR` `APPLY_CREATIVE_LOOK` |
| EFFECTS | `ADD_EFFECT` `UPDATE_EFFECT` `REMOVE_EFFECT` `APPLY_TEMPLATE` |
| AUDIO | `ADD_MUSIC` `ADD_SFX` `SET_VOLUME` `APPLY_AUDIO_DUCK` |
| FINALIZE | `FINALIZE_TIMELINE` |

`APPLY_TRACKING` / `APPLY_REFRAME` from the spec are deferred to milestone 5 — subject tracking is
a milestone-3 analyzer, and a reframe operation without a trustworthy track is an operation that
lies.

### Worked example (the one in §4 of the specification)

```json
{
  "schema_version": 1,
  "operation_id": "0f0a1a1e-2b7d-4c9a-9f0e-6d0a1f7c2b31",
  "sequence": 34,
  "type": "ADD_CLIP",
  "phase": "structure",
  "target": { "kind": "track", "track_id": "V1" },
  "parameters": {
    "clip_id": "c-9a1f2e",
    "media_id": "shot_007",
    "timeline_start_s": 2.4,
    "source_start_s": 1.2,
    "source_end_s": 4.8
  },
  "status": "COMPLETED",
  "created_utc": "2026-09-13T18:04:11.204Z",
  "executed_utc": "2026-09-13T18:04:11.209Z",
  "public_explanation": "Strongest hero framing; movement continues from the previous shot.",
  "metadata": {
    "planner": "heuristic@1",
    "signals": { "composition": 0.94, "subject": 0.97, "narrative": 0.96 }
  }
}
```

Resulting patch:

```json
[ { "op": "add", "path": "/timeline/tracks/V1/clips/3",
    "value": { "clip_id": "c-9a1f2e", "...": "..." } },
  { "op": "replace", "path": "/timeline/duration_s", "value": 6.0 } ]
```

---

## 6. Project schema

```
Project
├── schema_version          int, migrated forward, never silently
├── project_id              UUID
├── created_utc / updated_utc
├── metadata                title, aspect_ratio, fps, master_resolution
├── intent                  CreativeIntent (prompt, genre, emotion arc, target duration)
├── media {media_id: MediaItem}
│                           path, sha256, probe, proxy_path, thumbnail_path,
│                           waveform_path, source_space
├── analysis {media_id: {analyzer_id: AnalysisResult}}
├── timeline
│   ├── duration_s
│   ├── tracks [Track]      V1, V2, FX, A1, A2 — ordered, typed
│   │     └── clips [Clip]  clip_id, media_id, timeline_start_s, source_start_s,
│   │                       source_end_s, speed_curve, effects[], color, enabled
│   ├── transitions [TransitionInstance]
│   └── markers [Marker]    beats, impacts, narrative slots
├── audio
│   ├── events [AudioEvent] music, sfx, riser, impact, whoosh
│   └── automation [VolumeAutomation]
├── selection {media_id: SelectionState}   selected|rejected|pending + reasons + scores
├── render_settings         preview and master profiles
└── version                 int, increments on every applied operation
```

`EditGraph` and `Operations` are deliberately **not** fields of `Project`. The graph is derived; the
operations are the log that produced the project and live in their own table. `export/native.py`
writes both alongside the project so a `.takeone.json` is fully replayable.

Migration: `project.py` holds an ordered list of `(from_version, to_version, fn)`. Loading a project
runs every applicable step or refuses to load. There is no "best effort" path (§44).

---

## 7. EditGraph schema

```python
@dataclass(frozen=True, slots=True)
class RenderNode:
    node_id: str               # content address, derived — never assigned
    type: NodeType
    version: int               # compiler version for this node type
    inputs: tuple[str, ...]    # upstream node_ids, ordered
    parameters: Mapping        # validated, finite, typed
    time_range: TimeRange|None # timeline-relative, for nodes that have one
    enabled: bool
    metadata: Mapping          # origin clip/effect id — for the UI, not for rendering
```

Node types:

```
SourceNode      decoded media segment: the file *and* its in/out points
TimingNode      speed curve → time map → segmented setpts (+ interpolation mode)
TransformNode   position, scale, rotate, crop
TrackingNode    (milestone 5) subject track application
MaskNode        static, animated and scan masks
ColorNode       input/working/output space + technical + creative stages
EffectNode      a registered effect, arity 1
TransitionNode  a registered effect, arity 2
CompositeNode   layer stack with blend mode + opacity
AudioNode       source, gain automation, ducking
GeneratorNode   solid, gradient, noise, grain plate
OutputNode      the graph root
```

Structural invariants, all checked in `graph.validate()`:

1. Acyclic (Kahn's algorithm; a cycle is an error, not a warning).
2. Exactly one `OutputNode`, reachable from every other node.
3. Arity matches the node type and, for effects, the registered `EffectSpec.arity`.
4. Every parameter finite and within its `ParamSpec` range.
5. Every `time_range` non-negative, ordered, and inside the timeline.
6. Every referenced effect id **and version** is present in the registry.
7. `node_id` equals the recomputed content address (catches hand-edited graphs).

The graph has no FFmpeg types in it. `render/ffmpeg.py` is the only module that knows what a filter
string is; `render/backend.py` defines the protocol a second backend would implement.

---

## 8. Plugin interfaces

```python
class EffectPlugin(Protocol):
    id: str
    version: int
    name: str
    arity: int                    # 1 = effect, 2 = transition
    metadata: EffectMetadata      # category, tags, cost hint, licence

    def validate(self, parameters: Mapping) -> ValidationResult: ...
    def compile(self, context: RenderContext, parameters: Mapping,
                inputs: tuple[str, ...]) -> tuple[RenderNode, ...]: ...
    def ui_schema(self) -> EffectUISchema: ...
```

```python
class AnalyzerPlugin(Protocol):
    id: str
    version: int
    requires: tuple[str, ...]          # analyzer ids this one depends on
    def analyze(self, media: MediaItem, context: AnalysisContext) -> AnalysisResult: ...

class TemplatePlugin(Protocol):
    id: str
    version: int
    required_clips: ClipRequirement
    parameters: Mapping[str, ParamSpec]
    def program(self, context: TemplateContext) -> tuple[EditOperation, ...]: ...

class RenderBackend(Protocol):
    id: str
    def supports(self, node: RenderNode) -> bool: ...
    def compile(self, graph: EditGraph, target: RenderTarget) -> RenderPlan: ...
    def execute(self, plan: RenderPlan, progress: ProgressSink) -> RenderResult: ...

class Exporter(Protocol):
    id: str
    extension: str
    def export(self, project: Project, destination: Path) -> ExportResult: ...

class PlannerProvider(Protocol):
    id: str
    available: bool
    def plan(self, stage: PlanStage, request: Mapping) -> PlanResponse: ...
```

One `PluginRegistry` instance per kind, all constructed in `editor/__init__.py`. Registration is by
explicit call at import of the library module — never by directory scanning, never by import side
effects scattered through the package. Registering a duplicate `(id, version)` raises at import.

---

## 9. Render pipeline

**Three layers, as the spec requires, with a specific division of labour.**

`RenderPlanner` — *what*. Walks the graph in topological order, asks `ArtifactCache` for each node
id, and returns an ordered work list of *node subtrees* plus a cache-hit report. It also decides the
render target: `preview` (proxy resolution, fast preset, segment-level) or `master` (source
resolution, quality preset, whole timeline).

`RenderCompiler` — *how*. For FFmpeg: turns a subtree into `(argv, filter_complex)`. Rules:

- `argv` is always a **list**, never a string, and never passes through a shell.
- Filter strings are built only from validated typed parameters via `format` helpers that reject
  anything outside `[-0-9.a-zA-Z_:=@/ ]` after formatting.
- Every numeric parameter is formatted with an explicit precision so the same graph produces the
  same command bytes (determinism, and therefore a stable cache key for the command itself).
- Each node type has one compile function and one `version`. Changing a compile function *must*
  bump the node version, which changes every downstream node id, which correctly invalidates the
  cache.

`RenderExecutor` — *run*. `subprocess.Popen` with `-nostdin -hide_banner -loglevel error
-progress pipe:1`, parsing `out_time_ms`/`frame`/`speed` into `Job.progress`. Writes to a temporary
path in the cache directory and `os.replace`s into place on success, so a cancelled or crashed
render never leaves a half-written artifact that the cache would then trust.

### Preview vs master

| | preview | master |
| --- | --- | --- |
| source | proxy media | original media |
| resolution | 960 px on the long edge | source |
| codec | H.264 `ultrafast`, `yuv420p` | H.264 `slow` CRF 17, or ProRes |
| scope | only the segments the playhead needs | whole timeline |
| claim | "preview render" | "master render" |

A preview artifact is never presented, exported or reported as a master. (`AGENTS.md`: never claim
readiness from a lower-fidelity run.)

### Speed ramps

A `SpeedCurve` is a piecewise function `v(t)` over timeline time. The compiler:

1. Integrates `v` to get `source_time(timeline_time)` (cumulative trapezoid over a dense grid,
   analytic per segment for linear and Bezier segments).
2. Splits the curve into segments of near-constant rate under a tolerance.
3. Emits one `setpts=PTS*k` per segment plus a concat, rather than a single PTS expression —
   a single expression cannot represent a general piecewise integral without precision loss, and
   the segmented form is exactly reproducible and independently testable.
4. Applies the interpolation mode: `none` (drop/duplicate), `blend` (`tblend`), `mci`
   (`minterpolate`). Each is a distinct `TimingNode` parameter, so each has a distinct node id.

`timing/curve.py` is pure math over floats with no FFmpeg awareness, and is the most heavily
unit-tested module in the editor.

---

## 10. AI pipeline

```
CreativeIntent  ← IntentInterpreter(user text, brief, director metadata)
      │
      ▼
ShotUnderstanding[]  ← FootageUnderstanding(AnalysisSet, robot metadata)
      │
      ▼
Selection  ← ShotSelector(scorers, intent)             explainable, per-signal
      │
      ▼
NarrativeStructure  ← StoryPlanner(intent, selection)  opening/setup/development/hero/ending
      │
      ▼
RhythmPlan  ← RhythmPlanner(structure, beats, motion)  cuts, ramps, transitions
      │
      ▼
ColorPlan · EffectPlan · AudioPlan
      │
      ▼
EditPlan  ─► EditValidator ─► OperationGenerator ─► EditOperation[]
```

**Every stage has a deterministic implementation.** `HeuristicPlanner` scores, structures, times and
grades from analysis signals alone. `ResponsesPlanner` can replace any subset of stages; each
replacement is a separate strict-schema request with its own budget reservation, mirroring
`director/provider.py`.

Hard constraints on the LLM path, enforced in `plan/validator.py` *after* schema validation:

1. Output validates against the stage's strict JSON schema, or the stage falls back to heuristic.
2. Every referenced clip id exists in the project's media.
3. Every referenced effect id **and version** exists in the registry.
4. Every time is finite, ordered, inside the intended duration, and quantised to a frame.
5. No durations shorter than one frame or longer than the source.
6. Model output never reaches a filter string, a path, or a subprocess argument. It selects from
   enumerated ids and supplies numbers that are then range-clamped. (§45.)
7. The instruction block states that input JSON is untrusted creative material, exactly as the
   Director's adapter does.

`plan/explain.py` produces the `public_explanation` on each operation: one short product-level
sentence derived from the signals that drove the decision. Internal reasoning is never surfaced.

---

## 11. UI information architecture

```
Level 1  THE FILM          preview — largest element, always visible
Level 2  THE TIMELINE      the film's structure as it is being built
Level 3  THE EVIDENCE      shots (left) · AI activity (right)
Level 4  THE DETAIL        inspector — on demand, over the right column
Level 0  THE FRAME         title · phase · progress · pause · export
```

```
┌────────────────────────────────────────────────────────────────────────────┐
│ TAKE ONE            RHYTHM  ·  63%                        PAUSE   EXPORT   │  56px
├───────────────┬────────────────────────────────────────┬───────────────────┤
│               │                                        │                   │
│   SHOTS       │              FILM PREVIEW              │    AI EDITOR      │
│   240px       │                 flex                   │      300px        │
│               │                                        │                   │
│  ✓ 01   93    │                                        │ ✓ Analysed 27     │
│  ✓ 04   88    │                                        │ ✓ Selected 07     │
│  ✓ 07   96    │                                        │ ✓ Trimmed 0.62s   │
│  ○ 11         │                                        │ → Speed ramp      │
│  × 12         │                                        │                   │
│               │         [ ORIGINAL ⇄ FINAL ]           │                   │
├───────────────┴────────────────────────────────────────┴───────────────────┤
│  FX    ─────────── SPECTRUM ───────────                                    │
│  V2                    ███████████                                         │  timeline
│  V1    ███████  ███████████████  █████████                                 │  320px
│                   1×╲__0.42×__╱1×                                          │
│  A1    ════════════════════════════════════════                            │
│          ▲            ▲              ▲                                     │
│        00:00        00:04         00:08        00:12        00:15          │
└────────────────────────────────────────────────────────────────────────────┘
```

The phase rail lives inside the top bar as a thin progress element and expands on hover into the
eight-phase list (§36) rather than occupying permanent screen area.

---

## 12. Design system

Restrained, dark, film-tool. Tokens in `apps/editor/src/styles/tokens.css`.

```
SURFACES         --s-void      #08090A    page ground
                 --s-base      #0E1012    panels
                 --s-raised    #151719    cards, clips
                 --s-line      #1E2124    1px separators (never borders on everything)

INK              --ink-high    #ECEEF0    values, titles
                 --ink-mid     #9AA1A8    labels
                 --ink-low     #5C646B    metadata, disabled

ACCENT           --accent      #C8A24A    ONE accent. Selection, active phase, playhead.
                 --accent-dim  rgba(200,162,74,0.16)

SEMANTIC         --ok          #6FA96F    selected shot
                 --reject      #8A5A5A    rejected shot   (muted, never alarming red)
                 --analyze     #7A8794    in progress

TYPE             UI            "Inter var", system-ui  — 12/13/15/20/28
                 NUMERIC       "IBM Plex Mono", ui-monospace — tabular, for all timecode
                               and all scores, so digits never reflow

SPACE            4 · 8 · 12 · 16 · 24 · 32 · 48
RADIUS           2 (clips, chips) · 4 (panels) · 0 (timeline tracks)
ELEVATION        one shadow, used twice:  0 1px 0 rgba(255,255,255,.03) inset,
                                          0 8px 24px rgba(0,0,0,.45)

MOTION           --t-fast   120ms   state change (selection, hover)
                 --t-base   240ms   clip enter, trim, move
                 --t-slow   520ms   curve draw, colour interpolation
                 --ease     cubic-bezier(.22,.61,.36,1)      one easing, everywhere
                 no bounce, no overshoot, no spring
```

Motion is bound to state change (§28). Every animation in the app is driven by a patch arriving over
SSE; there is no `setInterval` decorating an idle timeline.

---

## 13. MVP scope

**In** — the thirteen proofs of §48, plus the structural work that makes them honest:

import · probe · proxy · thumbnails · waveform · scene detection · shot scoring · selection with
reasons · narrative structure · timeline construction through operations · trim · speed ramp with a
drawn curve · five transitions · technical colour correction · shot matching · creative look ·
twenty-four effect primitives composed into nine looks · beat detection · beat-aligned cuts · music
and SFX with ducking · preview render · master render · export (native + OTIO) · replay · undo ·
before/after · decision inspector · phase progress · job system.

**Out, with the seam in place** — generative VFX, subject tracking and reframe, GPU backend, HDR and
Apple Log compilers, OCIO, CapCut/FCPXML/Premiere exporters, multi-project library, collaborative
editing.

**Out, no seam** — manual keyframe editing, a full effects UI, nested sequences, multicam, colour
wheels. These are a different product (§32: the inspector explains; it does not become Premiere).

---

## 14. Risk analysis

| # | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| R1 | FFmpeg version drift between the build machine and the demo laptop changes filter behaviour or availability | High | Demo-fatal | `render/ffmpeg.py` probes `ffmpeg -filters` once at startup, asserts the required set, and refuses to start with a named missing filter. Only filters present in FFmpeg 6.0 are used. |
| R2 | Render latency makes the "watch it edit" experience feel like waiting | High | Product-fatal | Proxy media at 960px; content-addressed cache so only changed subtrees re-render; segment-level preview; operations dispatch immediately and the render catches up behind them. |
| R3 | The LLM returns plausible but invalid plans (unknown clip, impossible duration) | High | Silent corruption | Strict JSON schema + a second semantic validation pass + per-stage heuristic fallback. The validator, not the model, is the authority. |
| R4 | Two reducers (Python, TypeScript) drift, so the animation lies | Medium | Product-fatal | Only one reducer exists. The client applies server patches. |
| R5 | Speed-ramp time mapping drifts, so audio and video desynchronise | Medium | Visible | `timing/curve.py` is pure and property-tested: the integral of `v` over the clip must equal the source duration to within half a frame, asserted for every generated curve. |
| R6 | Colour matching overshoots and makes footage look worse | Medium | Visible | Matching is bounded: exposure ±1.5 stops, WB ±800K, contrast ±25%. Out-of-range solves clamp and report, they do not silently apply. |
| R7 | Windows path handling, spaces in filenames, and CRLF break media resolution | Medium | Demo-fatal | All paths are `Path`, resolved, and checked `is_relative_to` the project media root; argv lists mean quoting never enters the picture. Tested on Windows path fixtures. |
| R8 | Analysis is too slow on 27 clips to fit a live demo | Medium | Demo-visible | Analysis runs on proxy frames at a fixed sample rate, in the job pool, cached by `(media_sha256, analyzer, version)`; a second run of the same footage is instant. |
| R9 | Scope creep into a manual editor | High | Schedule-fatal | The inspector is explicitly read-only. Operations are the only mutation path, and there is no operation that a human UI control emits which the planner does not also emit. |
| R10 | The demo depends on network access for the planner | Medium | Demo-fatal | `HeuristicPlanner` is the default and needs no network. The LLM is an upgrade, not a dependency. |
| R11 | Audio licensing for the demo | Low | Legal | `AssetRegistry` requires a `licence` field; an asset without one cannot be registered, so it cannot reach a render. |
| R12 | A half-written cache artifact is trusted after a crash | Low | Corruption | Write to temp, `os.replace` on success only. |

---

## 15. Implementation order

Vertical slices. Each ends with a run and a verification, and nothing starts before the previous
slice is green (§58).

**M1 — the spine.** One video → probe → proxy → `ADD_CLIP` → real timeline → `TRIM_CLIP` →
`APPLY_COLOR_CORRECTION` → `ADD_EFFECT` → compile graph → render → export. No AI, no analysis, no
UI beyond proof. *Verification: an output file exists with the expected duration and frame count,
and measured pixel statistics differ from the source in the direction the colour operation
specified.*

**M2 — sequencing.** Multiple clips, tracks, speed ramps, transitions, audio tracks, templates.
*Verification: a three-clip montage with a ramp and two transitions renders with correct total
duration and correct cut positions to within one frame.*

**M3 — perception.** Analyzers, shot quality, beat detection, shot selection.
*Verification: scene boundaries within ±2 frames of hand-labelled fixtures; beat tracking within
±25 ms on synthetic click tracks at 90/120/140 BPM; quality scores rank a deliberately blurred
variant below its sharp original.*

**M4 — autonomy.** Orchestrator, planners, operation generation, visible autonomous editing, the
full UI, explanations.
*Verification: the §50 demo runs end to end from a prompt, with every visible event traceable to a
committed operation in the log.*

**M5 — the robot.** `RobotMetadataAdapter`, camera-motion-informed edit points, shot intent, actor
motion.
*Verification: identical footage with and without metadata produces measurably different, better-
timed cut points, and the editor still runs with the metadata absent.*

---

## 16. Test strategy

| Layer | What is tested | How |
| --- | --- | --- |
| Unit | `timing/curve.py` integral and inverse; reducer per operation type; `patch.diff/apply` round trip; graph validation rejects cycles, arity errors, unknown effects; content addressing stability; `color/match.py` solve bounds; `audio/beats.py` on synthetic clicks | `unittest`, no I/O, no FFmpeg |
| Property | For any valid curve: `∫v dt == source duration ± ½ frame`. For any operation sequence: `fold(ops)` equals `apply(patches)` applied to the empty project | generated sequences, fixed seed |
| Layering | No module imports across a forbidden layer boundary | AST walk over every module |
| Integration | import → analyze → select → build → compile → render on fixture media | real FFmpeg, tiny synthetic clips |
| Visual regression | Deterministic sample frames through each effect, compared against references within a per-effect tolerance | extract frame N, compare RMS in Lab |
| Planner | Output validates against schema; references only known clips and installed effect ids+versions; timeline positions valid; durations possible | recorded provider responses + adversarial fixtures |
| End to end | Upload → analyse → AI edit → timeline changes → preview → render → export | one script, asserted artifacts |
| Determinism | Two compilations of the same project produce identical node ids and identical argv | direct comparison |

Fixture media is **generated, not committed**: `tests/editor/fixtures/make_media.py` synthesises
clips with FFmpeg (a moving subject, a deliberately underexposed take, a warm/cool pair for
matching, a blurred take, and a click track at a known tempo). Deterministic, versioned by a
generator hash, and it keeps binaries out of the repository.

Verification entry point stays `scripts/TakeOne.ps1 -Command test`; editor tests are added to it and
are hermetic — no hardware, no network, no side effects at import.

---

## 17. Implementation record — what changed on contact with reality

Milestones 1 and 2 are built and verified. Four things in this document changed while
building them, each because a test or a render disagreed with the design. They are recorded
here rather than quietly edited above, because the reason is the useful part.

### 17.1 `TrimNode` is gone; a source node is a segment

The design had `SourceNode → TrimNode`. The first multi-clip render silently dropped its
trims: two clips cut differently from the same file produced two identical source nodes,
which the content address correctly deduplicated into one — and the FFmpeg compiler, which
fuses a sole trim into input-level seeking, then had two consumers and fused nothing.

The fix is not a special case. A source node *is* a decoded segment: the file together with
its in and out points. Two different reads of one file are two different nodes, which is
true, and identical reads still deduplicate. A separate trim node would have held the same
two numbers in two places. `tests/editor/test_render_compile.py` now asserts one `-i` and one
`-ss` per clip.

### 17.2 Overlap is a timeline rule, not a track rule

`Track` originally rejected overlapping clips. A transition *is* an overlap, so applying one
produced a state the track refused to construct. A track cannot judge the question —
transitions live on the timeline — so the rule moved up: `Track` reports its overlaps, and
`Timeline` requires every overlap to be accounted for by a transition of exactly that length.

This also forced a rule that turned out to matter generally: **a change and the thing that
explains it must be constructed together.** Lengthening a clip and rippling its neighbours,
or overlapping two clips and recording their transition, are two halves of one change.
Building the intermediate state would reject something that never existed, so ripple operates
on a plain list of clips and the container is constructed once.

### 17.3 A roll edit is refused on a retimed clip

`ALIGN_CUT_TO_BEAT` holds the programme length while moving the cut. On a clip with a speed
curve, the source consumed by an extra second of timeline depends on *where in the curve*
that second sits, so refitting the curve changes the clip's length by something other than
the roll. The first milestone-2 run caught this as a transition-length mismatch.

The honest fix is a refusal with an actionable message: align cuts before retiming. That is
the order the rhythm phase works in anyway (§7: cut timing and beat synchronisation precede
slow motion and speed ramps), so the constraint costs nothing and removes a class of silent
drift.

### 17.4 A client at sequence zero gets a snapshot, never a replay

The stream's resume contract originally sent a full-state event only when a project had no
operations. A fresh client therefore received the whole log as incremental patches and
applied them to nothing, producing a half-built object that rendered as a crash in three
components at once — found by loading the built interface in a real browser, not by a unit
test.

An incremental patch is only meaningful against the state it was computed from. A client at
sequence 0 now receives exactly one whole-state event; a client naming a sequence receives the
operations after it; a client too far behind receives a snapshot. The browser additionally
refuses to apply an incremental patch when it has no state, rather than inventing a project.

### 17.5 Verification as it stands

| Suite | What it proves | Result |
| --- | --- | --- |
| `tests/editor/test_*.py` | Timing identities, reducer rules, patch round trip, graph validation and content addressing, effect registry, compiler determinism and safety, module layering | 79 tests |
| `run_milestone1.py` | Import → proxy → clip → trim → grade → look → effect → compile → render → export, with duration, frame count and pixel statistics measured from the artifacts | 31 checks |
| `run_milestone2.py` | Three-shot montage with a speed ramp, two transitions, a beat-aligned roll edit and shot matching, rendering to the exact frame count | 13 checks |
| `run_api_check.py` | The HTTP surface: SSE framing and resume, byte-range media, and the error-to-status mapping | 16 checks |
| `apps/editor` | `tsc --noEmit`, `vitest` on the patch mirror, `vite build`, and the built interface loaded in a real browser with zero console errors | 9 tests |

Milestones 3, 4 and 5 — analysis, autonomy and robot metadata — are designed above and not
built. Nothing in the repository claims otherwise.
