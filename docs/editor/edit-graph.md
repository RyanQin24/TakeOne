# The edit graph

The graph is **derived**. It is recomputed from the timeline every time it is needed, never
edited, never stored as the truth. That is what makes "the interface animates a real project
mutation" a property of the system rather than a promise: the graph cannot disagree with the
timeline, because it is a function of it.

```
ProjectState ──compile.project_graph(state, target)──► EditGraph ──►
        RenderCompiler ──► RenderPlan ──► artifact
```

## Content addressing

```python
node_id = sha256(canonical_json(type, version, sorted_inputs, parameters, time_range))[:16]
```

A node's identity *is* its meaning. Three things fall out, and they are the reason the
editor feels fast:

1. **Incremental render.** An artifact keyed by `node_id` is correct forever. Changing a
   colour parameter changes that node's id and every descendant's, and leaves everything
   else usable. `ArtifactCache.report(graph)` can therefore say "17 of 41 nodes cached" and
   mean it.
2. **Determinism.** Two compilations of the same project produce identical ids and identical
   FFmpeg argument vectors. `tests/editor/test_render_compile.py` asserts both.
3. **Honest invalidation.** Changing a compile function in `render/ffmpeg.py` *requires*
   bumping that node type's `version`, which changes every id downstream, which invalidates
   exactly the cached artifacts that are now wrong. Forgetting is the one way to serve a
   stale frame, so the rule is written next to the code.

Parameters are canonicalised before hashing — floats rounded to nine places, keys sorted —
so `1.1` and `1.1000000001` are the same node and float formatting cannot split an identity.
A non-finite parameter is refused here, with its path, rather than failing later as a JSON
encoding error.

## Node types

| Type | Inputs | What it is |
| --- | --- | --- |
| `source` | 0 | A decoded media **segment**: the file plus its in and out points |
| `transform` | 1 | Conform to the project format: scale, crop or pad, frame rate, SAR, pixel format |
| `timing` | 1 | A speed curve as a time map, plus the frame-interpolation mode |
| `color` | 1 | Input/working/output space, exposure, white balance, contrast, saturation, lift |
| `effect` | 1 | One registered primitive |
| `transition` | 2 | One registered two-input effect |
| `sequence` | 2 | Temporal concatenation |
| `composite` | 1–16 | Layer stack with blend mode and opacity |
| `mask` | 1–2 | Static, animated and scan masks |
| `tracking` | 1 | Subject track application (milestone 5) |
| `audio` | 0–8 | Primary-track source sound plus timed audio events, source ranges, placement, gain and fades |
| `generator` | 0 | Solid, gradient, noise, grain plate |
| `output` | 1–2 | The graph root: target, resolution, frame rate, quality |

There is deliberately **no trim node**. The specification listed one, but a source node and
a trim node would hold the same two numbers in two places, and two clips cut differently
from one file would then share a source — which is both untrue and the thing that made the
first multi-clip render silently drop its trims. A source node is a segment, so identical
reads deduplicate and different reads do not.

## Invariants

`EditGraph.validate()` runs on construction and checks:

1. Acyclic, by Kahn's algorithm. A cycle is an error, never a warning.
2. Exactly one `output` node.
3. Every node reachable from the output — an orphan means the compiler built something it
   forgot to connect, which is a bug worth failing on.
4. Every input resolves to a node in the graph.
5. Arity matches the node type, and for effects, the registered `EffectSpec.arity`.
6. Every parameter finite and within range; every time range non-negative and ordered.
7. `node_id` equals its recomputed content address, so a hand-edited or corrupted graph is
   caught rather than rendered.

## What the graph does not know

The graph contains no FFmpeg types, no filter strings and no file handles. `render/ffmpeg.py`
is the only module that knows what a filter is; `render/backend.py` states the protocol a
second backend would implement. That separation is what makes a GPU compiler later a new
file rather than a rewrite.
