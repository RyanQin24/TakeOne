# Interface and design system

## The one contract

**The client mirrors state. It does not derive state.**

There is exactly one reducer, and it is in Python. For every applied operation the server
publishes `{operation, version, patch}` over Server-Sent Events; the browser applies the
patch to its mirror and animates the difference. A second reducer in TypeScript would drift,
and drift here means the animation lies about what happened — the precise failure the
architecture exists to prevent.

So the division is:

| The server owns | The client owns |
| --- | --- |
| Project state, timeline, graph, renders | What is selected, where the playhead is, how a change animates |

The stream carries the *semantic* event (the operation, with its explanation) alongside the
*structural* change (the patch). The interface animates from the operation and stays correct
from the patch.

**Resume.** A client connects with the last sequence it saw. At sequence 0 it receives one
whole-state event — never a replay of the log, because an incremental patch is only
meaningful against the state it was computed from. With a sequence it receives exactly the
operations after it. Too far behind, and it gets a snapshot instead. The client refuses to
apply an incremental patch when it has no state, rather than inventing a project.

## Layout

```
Level 0  the frame      title · phase · progress · undo · render · export      56px
Level 1  the film       preview — the largest element, always visible
Level 2  the timeline   the film's structure as it is being built              320px
Level 3  the evidence   shots (240px, left) · AI activity (300px, right)
Level 4  the detail     the decision inspector, replacing the activity column
```

The inspector is still the **explanation** surface. The **studio** on the right — Adjust,
Looks, Effects, Cuts — is the human command surface. Every slider and chip posts an
operation through the existing API; the client still does not derive project state.

## Tokens

```
SURFACES   --s-void #08090A   --s-base #0E1012   --s-raised #151719   --s-line #1E2124
INK        --ink-high #ECEEF0 --ink-mid #9AA1A8  --ink-low #5C646B
ACCENT     --accent #C8A24A   one accent: selection, active phase, playhead, AI activity
SEMANTIC   --ok #6FA96F (selected)  --reject #8A5A5A (rejected, muted — never alarming)
           --analyze #7A8794 (in progress)
TYPE       UI "Inter var", system-ui · NUMERIC "IBM Plex Mono", tabular
           every timecode and every score is tabular, so digits never reflow
SPACE      4 · 8 · 12 · 16 · 24 · 32
RADIUS     10 (clips) · 16 (cards) · 22 (preview) · pill 999 (buttons, fields, tabs)
MOTION     --t-fast 120ms (state)  --t-base 240ms (clip enter, trim, move)
           --t-slow 520ms (curve draw, colour interpolation)
           --ease cubic-bezier(.22,.61,.36,1) — one easing, everywhere
           no bounce, no overshoot, no spring
```

## Motion rules

Animation communicates a state change, or it does not exist. There is no `setInterval`
decorating an idle timeline; every animation in the application is driven by a patch arriving
over the stream.

- A clip **enters** at its real timeline position, once, then settles.
- A trim animates the real clip edge to its new boundary via CSS transitions on `left` and
  `width`, so the motion is the state change rather than a copy of it.
- A speed curve **draws itself** across the clip with `stroke-dashoffset`, sampling the same
  control points the renderer executes.
- An effect appears as a strip over the exact time range it covers.
- A transition is a hatched ribbon across the **top 13 px** of the frames it spans: visible on
  the cut, never covering the clip names underneath it.

## Timeline visual language

```
FX    ────────── LETTERBOX ──────────
                    ▓▓ WHIP ▓▓                       ▓▓ DIP ▓▓
V1    │ Opening                  │ Hero reveal              │ Ending
      │ luxury warm   1 fx       │ luxury warm  matched     │ luxury warm
                                 ╰──╮___0.42×___╭──╯  0.42×
A1    ═══════════ MUSIC ══════════════ IMPACT ═══════════════════
        ▲     ▲     ▲     ▲     ▲     ▲     ▲     ▲     ▲     ▲
      00:00     00:01     00:02     00:03     00:04     00:05
```

Clips carry their own evidence: the look applied, whether the colour was matched to another
shot, how many effects, and the slowest rate of their speed curve. Anything more belongs in
the inspector.

## Building it

```
cd apps/editor
npm install
npm run dev      # Vite on :5178, proxying /api/editor to the Python server on :8767
npm run build    # tsc --noEmit && vite build  →  apps/editor/dist
npm test         # vitest: the patch mirror must match the server's subset exactly
```

`apps/editor/dist` is genuine build output and is ignored by Git. (This is the opposite of
`apps/rehearsal/dist`, which contains authored source files and must not be treated as a
cache.)
