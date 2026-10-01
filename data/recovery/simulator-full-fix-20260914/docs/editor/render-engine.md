# The render engine

Three layers, with a specific division of labour.

```
EditGraph ──► RenderPlanner ──► RenderCompiler ──► RenderExecutor ──► artifact
              (what)            (how)              (run)
```

**`RenderPlanner`** asks the cache what already exists and returns an ordered work list plus
a cache-hit report. It also decides the target: `preview` (proxy media, ~960 px, fast preset)
or `master` (original media, full resolution, quality preset).

**`RenderCompiler`** turns a graph into `(argv, filter_complex)`. One compile function per
node type and per effect primitive, each with a version.

**`RenderExecutor`** runs it: `subprocess.Popen` with `-progress pipe:1`, parsing
`out_time_ms` into job progress, writing to a temporary file in the cache directory and
`os.replace`-ing it into place only on success. A cancelled or crashed render therefore never
leaves a half-written artifact that the cache would then trust.

## Safety rules

These are enforced in code, not by convention.

1. **The command is always a list.** No string is handed to a shell, ever.
2. **Filter fragments are built only from validated typed parameters**, formatted with
   explicit precision. Model output never reaches a filter string; a planner selects from
   enumerated ids and supplies numbers that are then range-clamped.
3. **The finished filter graph is checked against a character allowlist** before it leaves
   the compiler. A value that somehow carried a quote or a semicolon fails loudly there
   rather than changing the meaning of a command.
4. **Media paths must be absolute and inside the project's roots.** `media.resolve_inside`
   refuses traversal; the API refuses to serve a file outside the media roots or the cache.
5. **The backend is checked at startup.** `assert_backend_ready()` probes `ffmpeg -filters`
   and refuses to start with a *named* missing filter, rather than failing mid-demo. Only
   filters present in FFmpeg 6.0 are used.

## Source seeking

A source node carries its in and out points, so the compiler opens it as
`-ss <in> -t <span> -i <path>` and the graph statement is only `setpts=PTS-STARTPTS`.
Input-level seeking is far faster than decoding into a trim filter, and because the segment
is part of the node's identity the two cannot drift apart.

## Speed curves

`timing/curve.py` is pure mathematics over floats: a piecewise rate function `v(t)`, its
exact integral, and its inverse. The one identity everything depends on is

```
∫ rate dt over the clip  ==  the source span the clip consumes
```

computed analytically — each easing shape ships its own antiderivative — rather than by
sampling, so it is exactly true rather than approximately true.

Two ways exist to execute that on a frame-based backend: cut the clip into many
constant-rate pieces and concatenate, or hand `setpts` one expression for the time map. The
second is one filter instead of dozens, so that is what `timing/retime.py` produces. A
`setpts` expression is piecewise linear, so the knots are refined until the linear
interpolant is within **a quarter of a frame** of the true map everywhere, and the measured
deviation is returned rather than assumed. The compiler refuses a curve it cannot express
within one frame.

Frame interpolation is a mode on the timing node: `none` (drop/duplicate), `blend`
(`tblend`), `mci` (`minterpolate`). Each is a different node id, so each caches separately.

## Colour

Technical correction and creative look are separate stages, and the *architecture* is the
named pipeline rather than the library:

```
input transform → linear working space → exposure → white balance
  → shot match → tone curve → creative look → output transform
```

Exposure is applied in linear light: `zscale` into a linear, full-range planar RGB working
space, `exposure`, then back. Every field of the conversion is stated explicitly —
transfer, matrix, primaries, range — because an unstated matrix is the usual cause of a
silent or failed conversion, and guessing would make a grade wrong in a way nobody notices
until the master render. (Linear transfer cannot be combined with a YUV matrix at all; that
combination is what FFmpeg's "no path between colorspaces" means.)

`color/spaces.py` separates spaces we can *describe* from spaces we can *convert*. Apple Log
and Rec.2100 PQ are describable inputs with no conversion in this backend, so a project that
names one fails loudly with that name in the message rather than being treated as Rec.709.

OpenColorIO and ACES are deferred, not designed out: `ColorNode` carries `input_space`,
`working_space` and `output_space` from day one, so swapping the implementation changes one
compiler and nothing else.

## Proxies and the cache

Editing never touches the original. `ProxyManager` builds a ~960 px H.264 proxy with a short
GOP (so scrubbing is responsive), a thumbnail, and a waveform image when the media has
audio. The original is read again only for the master render, which is the one place
fidelity matters more than latency.

A **preview artifact is never reported as a master.** They are different targets, different
node ids and different cache entries, and the distinction is carried through the API.
