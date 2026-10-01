> **Superseded on 2026-09-17** by the design-system pass in prompt 16: the
> fifteen stylesheets described here became four, the per-literal re-tone
> became a per-token collapse onto one neutral ramp, and `/recording.html`
> became `/record.html`. Kept as the record of what was done on 2026-09-14.

# TakeOne interface unification — 2026-09-14

One visual system and one navigation system across every active surface. This
document is the before/after map the change was built from: what each surface
was, what it is now, and which contracts were held while it moved.

Nothing in this change touches robotics maths, inverse kinematics, camera
geometry, cart control, calibration, motor mapping, serial transport, firmware,
motion limits or hardware qualification. No Python under `packages/takeone` was
modified.

## 1. Route and surface map

| Route | Served by | Surface | Purpose (unchanged) | Ambient identity |
| --- | --- | --- | --- | --- |
| `/` | `apps/rehearsal/server.py` | Shot Studio | Movement library, path drawing, previs, transport, robot preparation | Stage blue, instrument layer dimmed |
| `/director.html` | same | Director | Idea → brief → script → shots | Violet creative glow, ambient drift on |
| `/voice.html` | same | Voice Rehearsal | Scripted read-through | Violet sound-stage glow from below |
| `/recording.html` | same | Record | Session, takes, review | Coral slate wash |
| `/motor-test.html` | same | Motor Lab (Utilities) | Direct calibrated joint diagnostics | Cool instrument grey, quiet layer |
| `/drive-proof.html` | same | Motion Proof (Utilities) | Cart movement evidence and limits | Cool document grey |
| `http://127.0.0.1:5178/` (dev) or the editor API's `--static` build | `takeone.editor.cli serve` + Vite | Editor | Timeline, preview, render, export | Same tokens, mirrored |

`apps/rehearsal/dist/dist/` is a recovery copy of an earlier Shot Studio build.
It was classified, left untouched and is not served as an active route.
`apps/rehearsal/dist` itself is authored application source and was treated as
such throughout.

## 2. Navigation

Primary workflow, in production order, present in the header of every active
surface:

```
01 Director → 02 Shot Studio → 03 Voice → 04 Record → 05 Edit
```

Secondary **Utilities** menu, present on every surface: Motor Lab, Motion Proof.

Every surface therefore reaches every other in at most two deliberate actions
(one click for a primary step; menu → item for a utility). At widths ≤1080px the
navigation and the utilities menu collapse into one compact drawer, built by
cloning the header's own links so the two can never disagree.

The current page is marked three ways at once: `aria-current="page"`, a tonal
violet field, and an animated rule under the entry — never colour alone. Each
surface also carries a breadcrumb-style workspace label whose first element is a
link back to the previous production step.

### The editor link is honest

The editor is a separate local process. A loopback liveness probe cannot tell it
apart from any other server on that port — the rehearsal server answers a request
for the editor's health route with a 404, which an opaque `no-cors` probe reports
as success. Presenting that as "connected" would be a claim the interface cannot
support.

So **Edit** opens a connection panel instead of pretending. The panel states what
the editor is, shows the address it will open (default `http://127.0.0.1:5178`,
overridable and remembered), offers **Open the editor**, and offers a
**Check this address** button whose result is worded exactly as strongly as the
evidence allows: *"Something is answering at …"* or *"Nothing is answering at …"*.
It also prints the two commands that start the service.

In the other direction, the editor's **Production** menu links to the rehearsal
surfaces on an address resolved in this order: an address the operator set, the
loopback origin this tab was opened from (so arriving through the rehearsal flow
configures it for free), then the documented default `http://127.0.0.1:8766`. The
panel says plainly that the editor cannot tell whether that server is running.

## 3. Design-system architecture

```
apps/rehearsal/dist/
  takeone.css          canonical tokens, @font-face, ambient ground, shell,
                       primitives, motion utilities, reduced motion   (loaded FIRST)
  <page>.css           each page's own layout, aliasing the tokens     (unchanged role)
  takeone-refine.css   cross-surface refinements that must win over page CSS,
                       per-surface ambient identity, the editorial document
                       layout, the responsive priority ladder          (loaded LAST)
  takeone-shell.js     shell behaviour: compact drawer, utilities menu, entrance
                       and reveal motion, marquee pausing, editor handoff panel,
                       environment pill                                (ES module)
  fonts/               self-hosted Instrument Serif, Inter, IBM Plex Mono (OFL)

apps/editor/
  src/styles/takeone-tokens.css   GENERATED mirror of the token block + font faces
  scripts/sync-takeone-tokens.mjs the generator; run by hand, never part of the build
  src/styles/tokens.css           the editor's own names, now aliases onto the tokens
  src/components/TakeOneNav.tsx   the production menu
  public/fonts/                   the same font files
```

The static pages were **not** migrated to React, and no animation or framework
dependency was added anywhere. The editor keeps its React architecture, its
one-reducer contract and its API/state flow.

Page stylesheets were re-toned programmatically rather than by hand
(`apps/rehearsal/tools/retone.py`). Every colour keeps its **lightness** and moves
only in hue and chroma, so existing contrast relationships — and the legibility
of dense simulator labels and technical readings — survive by construction:

* near-neutrals (absolute chroma ≤ 0.10 + 0.10 × lightness) become one charcoal
  ramp, cool in shadow and warm ivory in the highlights, replacing five separate
  grey / green / blue casts;
* saturated colours keep their semantic family and snap to the single palette
  value for it, so camera stays blue, light stays gold, success and actor stay
  mint, faults stay red and the action accent stays coral;
* Director's olive creative accent becomes the violet creative accent; its
  authored study illustrations were re-toned at reduced chroma so they read as
  filmic plates.

## 4. Typography

| Role | Face | Where |
| --- | --- | --- |
| Editorial display | Instrument Serif 400 (OFL, self-hosted) | Director's opening question and project titles, the Shot Studio shot title, Voice and Record page titles, the Motor Lab rail title, Motion Proof's title, the editor's launch question |
| UI | Inter 400/500/600 (OFL, self-hosted) | every control, label, table, form and body |
| Technical numeric | IBM Plex Mono 400/500 (OFL, self-hosted) | timecode, motor values, focal length, coordinates, percentages, plan identifiers, evidence tables |

The display serif is never used for dense settings, safety messages, tables,
motor data or long body copy. The editor's remote Google Fonts link was removed;
the same files are now served locally by both applications.

## 5. Motion

Tokens: 150 ms feedback, 240 ms interaction, 380 ms panel, 620 ms page entrance,
7 s ambient, 48 s rail. Two curves: `cubic-bezier(.16,.84,.34,1)` for settle and
`cubic-bezier(.4,.14,.3,1)` for balanced transitions. Only `transform` and
`opacity` are animated.

* Creative surfaces (Director, Voice, Record, Motion Proof) get the slow ambient
  drift and sectional reveals; operational surfaces (Shot Studio, Motor Lab) do
  not, and their headers never hide on scroll.
* The ambient layers are painted on `<html>` at `z-index: -1` with
  `pointer-events: none`, so they are always behind page content and never over a
  canvas. Nothing was attached to the simulator's render loop and no new
  `requestAnimationFrame` loop was introduced.
* All decorative animation pauses when the document is hidden.
* The one continuous motion in the product — the Director movement rail — is
  built from the real `/api/previs/templates` catalogue (28 movements, six
  families), pauses on hover and keyboard focus, has an explicit pause control in
  its section heading, and does not run under reduced motion.
* Reduced motion disables ambient drift, stops the rail, removes translations and
  page transitions, and keeps every piece of content visible. Canvas playback —
  the functional motion of a rehearsal the operator started — is deliberately
  exempt.

## 6. Contracts held

Page markup changed, so the DOM contracts were checked rather than assumed. Every
`getElementById`, `$()` and `querySelector` literal is extracted from the module
graph each page actually loads, and resolved against the rendered DOM on both the
original tree and the changed one:

| Route | Contracts checked | New missing | New console errors |
| --- | --- | --- | --- |
| `/` | 103 | 0 | 0 |
| `/director.html` | 78 | 0 | 0 |
| `/voice.html` | 30 | 0 | 0 |
| `/recording.html` | 29 | 0 | 0 |
| `/motor-test.html` | 75 | 0 | 0 |

One contract needed deliberate care: `orbit.js` rewrites the workspace subtitle
through `document.querySelector('.workspace small')`. The shared header keeps that
exact hook on the Shot Studio (`class="t1-workspace workspace"`, subtitle in a
`<small>`), so the selector still resolves.

## 7. Known limitations

* `scripts/TakeOne.ps1 -Command test` is a PowerShell wrapper and was not run.
  The commands it invokes for the changed code were run directly.
* Adding `/apps/**/fonts/*.woff2 -text` to `.gitattributes` would make the binary
  classification of the new typefaces explicit. Git auto-detects it, so this was
  left to the repository owner rather than edited concurrently.
* The Shot Studio's 3D scene keeps its bright studio lighting. That is the previs
  look of the real set, not interface chrome, so it was framed rather than
  re-lit.
