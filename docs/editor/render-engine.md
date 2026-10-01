# The render engine

Three layers, with a specific division of labour.

```
EditGraph ──► RenderPlanner ──► RenderCompiler ──► RenderExecutor ──► artifact
              (what)            (how)              (run)
```

**`RenderPlanner`** asks the cache what already exists and returns an ordered work list plus
a cache-hit report. It also decides the target: `preview` (proxy picture, ~960 px, fast preset)
or `master` (original picture, full resolution, quality preset). Both targets reopen original
media for source audio because the video proxies are deliberately silent.

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
second is one filter instead of dozens, so that is what `timing/retime.py` produces. The
complete authored curve is stored on the timing node. Its knots are refined until the linear
interpolant is within **a quarter of a frame** of the true map everywhere, and the measured
deviation is returned rather than assumed. The compiler refuses a curve it cannot express
within one frame. It pads and trims the retimed picture to the declared final frame so a
speed-up at the end cannot move the following cut.

Source sound follows the same curve. The audio compiler derives constant-rate windows from
the same knots, applies bounded `atempo` stages with source context, and crops each result on
the 48 kHz output sample grid before concatenation. Clip audio overlaps across the same
transition intervals as picture. Independently placed music and sound events retain their
authored source range, timeline placement, gain and fades before the final mix.

When a media probe carries measured first-audio-stream bounds, the compiler intersects that
stream with the clip's source range. A disjoint stream becomes silence. An overlapping stream is
read only across the intersection, receives exact 48 kHz leading silence, and is padded or trimmed
to the clip's picture span before speed mapping. Delayed or short embedded audio therefore cannot
shift a following cut or remove sound from the next clip.

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
Rendered H.264 output is explicitly tagged with BT.709 matrix, primaries and transfer
metadata rather than relying on a player or container default.

OpenColorIO and ACES are deferred, not designed out: `ColorNode` carries `input_space`,
`working_space` and `output_space` from day one, so swapping the implementation changes one
compiler and nothing else.

## Proxies and the cache

Editing never changes the original. `ProxyManager` builds a silent ~960 px H.264 picture
proxy with a short GOP (so scrubbing is responsive), a thumbnail, and a waveform image when
the media has audio. Preview picture reads the proxy, but preview audio reopens the original;
master picture and audio both read the original. This preserves sound without pretending the
lower-fidelity preview picture is a master.

A **preview artifact is never reported as a master.** They are different targets, different
node ids and different cache entries, and the distinction is carried through the API.
