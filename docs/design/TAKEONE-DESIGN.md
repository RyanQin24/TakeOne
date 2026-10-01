# TAKE ONE — NOCTURNE

Nocturne is TakeOne's canonical visual and interaction system. It keeps the Director expressive and cinematic while keeping Shot Studio calm, precise, operational, and highly legible.

## Principles

1. The primary action required to finish the current task is always visible.
2. Progressive disclosure hides engineering detail, never the next required action.
3. The viewport is the dominant surface in Shot Studio.
4. Motion communicates state, continuity, and filmmaking metaphors; it is not decoration.
5. Semantic color names describe intent rather than implementation values.
6. Normal readable text targets at least 4.5:1 contrast against its actual background.
7. Spacing uses the 4px family: 4, 8, 12, 16, 24, 32, 48, 72.
8. Physical robot actions are visually distinct from simulation and creative playback.

## Primary action contract

| State | Always-visible actions |
| --- | --- |
| Ground path · editing | Finish path, Undo |
| Ground path · ready | Edit path, Simulate Shot, Reset |
| Movement template · ready | Simulate Shot, Reset |
| Director script · ready | Rehearse Film, Reset, Shot Types, shot navigation |
| Preview error | Retry preview |
| Robot prepared | Hold to Run Robot |
| Robot moving | STOP |

## Surface hierarchy

- `surface.void`: #090B0D — deepest app ground.
- `surface.canvas`: #0D1014 — operational canvas and timeline.
- `surface.panel`: #13171C — panels and inspectors.
- `surface.raised`: #191E24 — selected/raised groups.
- `surface.control`: #222830 — inputs and secondary controls.
- `border.default`: #303842; `border.strong`: #45505C.

## Ink

- `text.primary`: #F4F1EA.
- `text.secondary`: #C9CED5.
- `text.metadata`: #98A2AD.
- `text.disabled`: #737D87; disabled only, never ordinary metadata.

## Semantic accents

- Coral #FF8A67 — primary creative action and playhead.
- Violet #A998FF — AI/directorial active state and selection.
- Mint #7ED6B8 — ready/safe/tracking.
- Camera blue #79B9EF — camera path/optics.
- Amber #E7B96B — light/caution.
- Danger #FF7068 — fault/stop.

## Typography

Instrument Serif is reserved for film titles, creative questions, scenes, and editorial moments. Inter carries operational UI and instructions. IBM Plex Mono is restricted to timecode, coordinates, calibration, and telemetry.

## Timeline grammar

The timeline is a temporal instrument, not a decorative card. It uses the canvas ground, clear ruler labels, precise ticks, a neutral graphite clip with a restrained mint motion edge, and a coral playhead that spans ruler through track. Sequence segments remain in one family: shots, reposition, unavailable, and selected differ by value/border rather than rainbow color.

Vertical rhythm: 12px breathing room, 20px ruler, 8px relationship gap, 40–48px track, 8px relationship gap, 28px transport footer.

## Technical evidence

Shot Studio leads with **Shot Facts**, not equations. Current duration, rehearsal lower bound, cart travel/speed, lens distance, and camera height are immediately scannable. Exact derivation and assumptions live one disclosure deeper under **How this is calculated**. The explanation must name what the metric includes and excludes; it must never present an estimate as a measured physical result.

On Director-script timelines, ruler marks align to authored shot boundaries rather than arbitrary equal time divisions. A selected shot uses violet, the playhead uses coral, and the current shot progress remains readable without opening the inspector.

Below 950px, the shot navigator collapses automatically and the Director Monitor remains picture-in-picture while space permits, so the stage and timeline preserve their relationship. Resizing back to a professional desktop width restores the navigator.

## Studio environment

The generic rehearsal environment is a neutral graphite/mineral stage. It is deliberately mid-tone rather than black so the dark cart, actor, framing guides, semantic paths, and lighting remain readable. Imported authored scenes keep their own atmosphere profiles.

Three directions were evaluated during UX-03: neutral graphite, warm cinema, and cool technical. The neutral graphite direction was selected because it best harmonizes with the application shell while preserving coral route, actor, and robot separation.

## Motion grammar

- Micro feedback: 120–180ms.
- Panel/state transitions: 180–260ms.
- Creative spatial transitions: 280–450ms.
- Director may use expressive film motion; Shot Studio stays stable.
- Film Engine reels use inertia-like continuous rotation only while visible.
- Planning uses a camera-gate light pulse and moving perforation feed.
- Landing typography settles into registration; operational typography never moves.
- Ambient motion pauses when hidden/offscreen and all motion respects reduced-motion.

## Validation rule

A visual change is unfinished until the live product has been captured and inspected at 1728×1117, 1440×900, 1280×900, 1024×768, plus a narrow viewport. No console exceptions, horizontal overflow, hidden primary action, or affected-test failure may remain.
