# Making TAKE ONE cinematic

Date: 2026-09-14
Scope: why the rig's shots read as robotic, what the hardware can actually do, and the
ordered work to close the gap. No hardware was activated for this audit; every number
below is either measured from the existing compiler or labelled as researched/derived.

---

## 1. The headline

**The machine is not the bottleneck. The shot vocabulary is.**

The compiler already solves compound curves at broadcast-usable accuracy. Measured, on
this repository, today:

| Route | Length | Filming time | Max aim error | Endpoint error |
| --- | --- | --- | --- | --- |
| Straight truck, 2.5 m standoff | 6.0 m | 29.2 s | **0.29°** | 0.2 cm |
| S-curve, ±0.9 m amplitude | 7.2 m | 40.0 s | **1.83°** | 1.4 cm |
| Spiral push-in with descent | 6.6 m | 36.4 s | **0.75°** | 1.2 cm |
| Quarter-orbit + boom to 1.7 m | 5.7 m | 31.0 s | **1.23°** | 0.9 cm |
| **Three-beat: arc → straight → arc** | **16.6 m** | **88.0 s** | **2.58°** | 0.7 cm |
| Serpentine, 3 full waves | 30.9 m | 163.6 s | not measured | 1.1 cm |
| Figure-eight, r = 1.2 m | 7.1 m | 49.0 s | not measured | 1.1 cm |

An 88-second continuous take that arcs in, straightens past the subject, and arcs out
the far side already holds the subject to under 3° of aim error and lands within 7 mm of
its mark. Nothing in this table required new code — only `mode: "path"` with a polyline.

Meanwhile **all 28 shipped presets are locked to a single geometric primitive**: one
circle, one straight line, or one stationary point. `previs/templates.py:path_settings`
returns exactly one of those shapes. No preset can curve.

That is the gap. The rest of this document is how to close it.

---

## 2. What the rig can actually do

Measured by enumerating the wire-command grid and running the compiler
(`packages/takeone/previs/path.py`, `cart/response.py`, `configs/rig.json`).

### Cart

- **Forward only.** `reverse_enabled: false`. There is no reverse and no lateral slide.
  Differential drive, powered wheels leading, casters trailing.
- **12 discrete straight-line speeds**, quantised by the two-decimal wire command:
  0.1375, 0.1719, 0.2063, 0.2406, 0.2750, 0.3094, 0.3438, 0.3781, 0.4125, 0.4469,
  0.4813, 0.5156 m/s. There is no creep below 0.1375 m/s — the motor deadband forbids it.
- **168 distinct usable command pairs**, giving a discrete set of achievable curvatures.
- **Tightest turn: 0.29 m radius**, but only at a 0.069 m/s crawl (one wheel stopped,
  one at minimum). At working pace the tightest is **~0.50 m radius**. Below ~0.5 m the
  follower corner-cuts: a requested 0.35 m circle travelled 1.86 m against 2.20 m
  requested, 15% short.
- **Curvature slew: 2.2 s** to swing from hard-left to hard-right, because each wheel
  command may change by only 0.01 per 200 ms control tick. Every S-curve inflection costs
  2.2 seconds of passing through straight. This is the single most important number for
  designing curved moves.
- Auto-slowdown in bends: `speed / (1 + |curvature| × 0.35)`.

### Arm

- 5 DOF per arm, two arms (phone, light), mounted at 1.23 m, reaching 1.80 m.
- **Trajectory rate ceiling: 24.18 °/s (0.42 rad/s)** — `max_delta` = 11 counts per
  0.04 s tick in `path.py`.
- **Commissioning limits permit 0.80 rad/s.** The planner is using **53% of the
  permitted rate.**
- IK is solved at keyframes and linearly interpolated between: **0.8 s spacing for static
  aims, 0.2 s for animated aims.**

### Take length

- Follower step ceiling **570 s**; compiled duration ceiling **600 s**; drawn path
  **0.15–65 m**. A 65 m route at the slowest legal pace is a **464-second single take.**
- Against that headroom, the shipped presets use 7 distinct durations, and **19 of 28
  land at either 8.82 s or 10.0 s.**

### Dead time

- Arm setup before the shot clock starts: **5.48–5.96 s**, effectively fixed regardless
  of shot. That is **57.8% of a whip pan's total runtime** and 5.0% of a 360° orbit.

### Headroom being left unused

| Channel | Planner uses | Hardware/policy allows | Unused |
| --- | --- | --- | --- |
| Cart pace | 0.35 m/s (UI field cap) | 0.5156 m/s (wire cap) | **+47%** |
| Arm rate | 0.42 rad/s (trajectory limiter) | 0.80 rad/s (commissioning) | **+90%** |
| Take length | ~10 s typical preset | 570 s | **~50×** |
| Route shape | 1 primitive | 512-point polyline | — |

---

## 3. Why the current output reads as robotic

Five structural causes, each traced to code.

### 3.1 One shot = one gesture

`templates.py` gives every preset exactly one `route` and one `aim`. `aim_offsets()` in
`previs/program.py` is a single `if/elif` chain — pan **or** tilt **or** roll **or**
handheld, never two. Camera height is a single start→end ramp with one
`rise_start`/`rise_end` window (`choreography.py`). Focal length is one ramp.

So every shot is a single monotonic gesture that starts, happens, and stops. Real
cinematic moves are multi-beat: move, settle, reframe, move again. **The system cannot
express a beat.** 28 of 72 route×aim combinations exist, and none of them compose.

### 3.2 Uniform duration

19 of 28 presets film for 8.82 s or 10.0 s. A cut list built from this library has almost
no rhythm — every shot is the same length. The reference the user cited (Apple product
films) works precisely because it alternates 1-second punches against 6-second holds.

### 3.3 No breath

Moves begin at the first frame and end at the last. There is no pre-roll hold, no settle,
no post-roll. Quintic easing (`6u⁵−15u⁴+10u³`) is correctly used for height and aim, which
is good — it is C² continuous with zero velocity and acceleration at both ends. But the
**cart** has no equivalent: it starts commanding motion immediately and stops immediately.

Researched: a trapezoidal velocity profile has **infinite jerk at phase transitions**
(Chuck Lewin, Performance Motion Devices, *Machine Design* 2007). More jerk excites more
structural modes, which lengthens settling. For camera work the recommendation is the
extreme S-curve — eliminate the constant-acceleration phase entirely so acceleration never
plateaus.

### 3.4 The light is furniture

The light arm has **no independent timeline**. In `path.py`, light height is
`light_height_start_m + change_progress(...) × (end − start)` — it reuses the *camera's*
rise window. `face_actor()` keeps it pointed at the actor's face permanently. Grepping
`packages/takeone` for `intensity|brightness|dmx|kelvin`: every hit is in
`editor/effects/` (post-production grading). **The physical light has no intensity,
colour, or timing channel at all.**

This is the highest-leverage omission. Researched, from a working tabletop director
(Timothy Hogan): lighting beats camera technology for improving product work, and the
leverage order is **subject orientation → light position → camera path**. TAKE ONE
currently automates only the last and least of those three.

Also geometric, and important: **specular highlights move at twice the camera's angular
rate** (law of reflection). A 20° arc sweeps a highlight 40°. A moving light on a second
arm is therefore worth more than a bigger camera move — and the rig already has that
second arm.

### 3.5 Inter-shot moves are planned with a primitive the cart does not have

`previs/reposition.py:plan()` moves between marks by turn-in-place, driving wheels in
opposite directions (`[-sign*SPEED_M_S, sign*SPEED_M_S]`). It never consults
`reverse_enabled`, which is `false`. The module honestly labels itself "kinematic
preview, never a qualified plan" — but it means the rehearsal clock **underestimates real
inter-shot time**, and the sequence timing shown to the director is optimistic.

---

## 4. The fix: specify four layers, not a preset

Researched finding that reframes the whole problem: **no motion-control vendor publishes
a named-compound-move taxonomy.** MRMC's Flair, which drives the Bolt Cinebot, exposes
*primitives* and lets the move emerge from four independently-timed layers:

1. **Camera path** — spline through control points
2. **Target path** — a *separate* spline (Flair calls this Target Tracking)
3. **Velocity profile** — independent per path, and reversible along it
4. **Lens envelope** — focus, zoom, iris

A compound move is what happens when those four layers have *different time envelopes*.
This is why "push-and-settle" and "drift-and-punch" are the same path with inverted
velocity envelopes — naming moves obscures that; layering exposes it.

TAKE ONE currently fuses all four layers into one preset with one shared progress
variable. **Splitting them is the core refactor**, and it is smaller than it sounds
because the compiler already accepts arbitrary paths.

### Proposed shot schema

```jsonc
{
  "mode": "compound",
  "path":   { "points_m": [[...]], "closed": false },
  "target": { "kind": "spline", "points_m": [[...]] },   // or "actor", or "point"
  "velocity": [
    { "at": 0.00, "pace_m_s": 0.00, "hold_s": 1.5 },     // pre-roll breath
    { "at": 0.15, "pace_m_s": 0.24 },
    { "at": 0.55, "pace_m_s": 0.24, "hold_s": 0.8 },     // mid-take settle
    { "at": 0.70, "pace_m_s": 0.34 },
    { "at": 1.00, "pace_m_s": 0.00, "hold_s": 2.0 }      // post-roll settle
  ],
  "camera_height": [ {"at": 0.0, "m": 1.10}, {"at": 0.45, "m": 1.10}, {"at": 0.9, "m": 1.68} ],
  "lens":   [ {"at": 0.0, "focal_mm": 35}, {"at": 0.6, "focal_mm": 35}, {"at": 1.0, "focal_mm": 85} ],
  "light":  { "path_offset": [...], "target": "subject", "height": [...] }
}
```

The key change is that each channel carries **its own keyframe list on its own timing**,
rather than every channel sharing `rise_start`/`rise_end`. Multi-beat shots fall out for
free: a beat is just a `hold_s` in the middle of the velocity list.

---

## 5. Compound moves that fit *this* envelope

These respect the measured constraints: forward-only, ≥0.5 m turn radius at pace,
2.2 s per curvature reversal, 0.42–0.80 rad/s arm.

| Move | Geometry | Fits because | Cost |
| --- | --- | --- | --- |
| **Arc-and-rise** | Helical segment: constant-radius arc + simultaneous boom | Verified: 1.23° aim error at 31 s | Height error 16 cm if the lift is fast — spread it over ≥50% of the take |
| **Spiral push** | Radius shrinks while angle advances | Verified: 0.75° aim error. Log spiral at constant angular rate gives an *accelerating* perceived approach for free | Keep final radius > 1.0 m |
| **Orbit-into-push** | Arc unwinding into a radial line | Single curvature transition, one 2.2 s cost | Curvature *discontinuity* reads as a hitch even when position and velocity are continuous — blend the join |
| **S-curve traverse** | Two opposed arcs | Verified: 1.83° at ±0.9 m amplitude | 2.2 s per inflection; budget it as intentional straight-through |
| **Pass-by** | Straight line offset from subject, target tracks across | Straight line is the most accurate route measured (0.29°) | Needs a target spline, not actor-lock |
| **Three-beat oner** | Arc → straight → arc | **Verified: 88 s, 2.58° aim error** | Requires the four-layer schema to hold mid-take |
| **Foreground reveal** | Slow camera, occluder near lens | Apparent lateral rate ∝ 1/distance — an occluder at ¼ subject distance moves **4× faster** | Set reveal speed via foreground distance, *not* camera speed. Keeps a slow premium camera velocity with a decisive uncover |
| **Highlight walk** | Camera near-static; **light arm** arcs | Specular sweep is 2× the light's angular travel. Uses the idle second arm | Needs the light timeline (§3.4) |
| **Mimic overlay** | Organic noise summed onto a clean spline | `handheld` aim already generates the noise — it just cannot combine with anything | The single highest-value composition unlock |

Deliberately excluded as out-of-envelope: whip pans faster than 24 °/s, turn-in-place
moves, anything needing reverse, radii below 0.5 m at pace, and lateral crabbing.

### Mimic overlay deserves its own note

Flair's documented approach to defeating the robotic read: *"Need a shaky camera effect?
Record the shakiness on a separate axis and add the motion."* TAKE ONE already computes
exactly this in `aim_offsets()` under `aim == "handheld"` — small sinusoidal pan/tilt/roll
at 0.45 Hz. But because `aim` is exclusive, handheld texture cannot be layered onto an
arc, a push, or an orbit. Making the handheld term **additive rather than exclusive** is
perhaps twenty lines of code and immediately makes every one of the other 27 presets look
less machined.

---

## 6. Shot length and rhythm

The user's instruction — some shots 2 s, some 10 s, driven by creative need — is correct
and is supported by the data.

**Verified** (Cutting et al., *i-Perception* 2011; 160 films 1935–2010; open access
PMC3485803): average shot length fell from ~10 s in the 1930s–40s to **below 4 s after
2000**. Longest in that sample 26.2 s, shortest 2.2 s. ~99% of transitions since the 1970s
are straight cuts.

Two cautions, both verified:

- **Use median, not mean.** Shot-length distributions are right-skewed; Redfern argues ASL
  is invalid as a cutting-rate measure.
- **Counterintuitive and directly relevant:** per Barry Salt's corpus, the proportion of
  shots with a *moving* camera **fell from 16% (1959) to 6% (1999)**. Films got faster by
  putting motion *in front of* the camera, not by moving the camera more. For TAKE ONE:
  moving the light and the subject is often better than moving the cart.

**Not verified, and I want to be straight about this:** there is no peer-reviewed shot-length
corpus for television commercials, and **no published shot-length measurement for Apple
product films exists at all.** The only commercial figure found is a 1998 trade article
("15–20 shots per 30 s"). What *is* verifiable about Apple: the agency is TBWA\Media Arts
Lab; the Apple Watch film "Between Beats" is 100 s; "1984" was 60 s; one September event
film took 38 filming days across 20 locations.

So the grid below is **derived engineering guidance, not observed data.** Label it as such
in any UI that surfaces it.

| Band | Duration | Use |
| --- | --- | --- |
| Punch | 0.5–1.5 s | Detail, texture, impact. Cart static; arm or light only |
| Beat | 1.5–3.0 s | Standard connective shot |
| Hold | 3.0–6.0 s | Premium product presentation; let the object be still |
| Hero move | 6–12 s | One compound gesture with breath at both ends |
| Oner | 60–140 s | Structural centrepiece |

Note the punch band is currently **unreachable**: the shortest preset films for 4.0 s, and
setup dead time alone is 5.48 s. Sub-2-second shots need the setup amortised across a
sequence (see §8, item 3).

Reference points for the oner band, verified: Honda "Cog" is 120 s but is **two 60 s
Technocrane takes stitched at the muffler roll** — 4 days of filming, ~100 takes, parts
positioned to 1.6 mm. Philips "Carousel" is 139 s, a single continuous track through a
frozen scene that loops back to its origin so the take feels closed. Volvo "Epic Split" is
a single take whose location was chosen for geometry: "road that was absolutely straight
for as long as possible."

The Cog lesson matters most here: **60 s is the practical ceiling for a physically
choreographed take**, and "oner" in advertising usually means stitched. TAKE ONE's
measured 88 s three-beat take is already past that ceiling — which is a genuine
capability, but plan for stitching rather than betting a shoot on one perfect run.

---

## 7. Breath: the numbers to program

Researched, with the unverified parts flagged.

**Verified.** The canonical seven-phase S-curve; a trapezoid is the degenerate case
containing only phases II, IV and VI. High-throughput applications set the S-transition
phases to 5–15% of the constant-acceleration phases — but for maximum smoothness the same
source prescribes **no phase II or VI at all**, i.e. acceleration never plateaus. **Camera
work wants that extreme, not the throughput setting.** Parabolic profiles are wrong for
camera work (very high start/end accelerations).

Also verified: motion-control practice programs **pre-roll and post-roll** so the rig
reaches speed before the recorded portion begins, keeping the usable take free of
acceleration artefacts.

**Not verified.** No authoritative source gives specific hold durations, and no published
structural resonance figure exists for Bolt, Cinebot or KIRA. Derived, with assumptions
stated: pre-hold **1.0–2.0 s**, post-hold **1.5–2.5 s** — longer at the tail because
residual ring-down must decay (assuming a 2–4 Hz first mode and 4–6 periods). Total
**2.5–4.5 s of non-moving time per compound move, asymmetrically weighted to the tail.**

That asymmetry — energy in fast, settle out slow — is the mechanical definition of breath,
and it is why a 6 s shot with correct breath leaves only 1.5–3.5 s of actual gesture. This
is the most common reason programmed moves feel rushed.

For this rig specifically: TAKE ONE's own quintic on height and aim is already the right
curve. **The work is to give the cart the same treatment** — currently it steps straight
from 0 to a commanded speed. Because the wire command is quantised in 0.01 steps and
slew-limited to 0.01 per 200 ms, an S-ramp from rest to 0.24 m/s already takes ~1.4 s of
command ramping; the profile is partly imposed by the hardware. Making it explicit and
symmetric is the change.

---

## 8. Implementation status — 14 September 2026

The eight upgrades are implemented in the existing Director → movement compiler →
Shot Studio path. Final repository verification passed: 660 product tests, 29 simulation
tests, 207 browser tests, syntax, preservation, lint and formatting checks. The historical
measurements above describe the pre-upgrade code; they are not hardware qualification.

| Item | Shipped behavior | Where to review it |
| --- | --- | --- |
| 1. Additive aim | Preset aim plus independent pan, tilt and roll keys, with an optional organic drift contribution on any template or drawn route. | Shot Studio → Independent timing & organic drift; Spiral enables a small overlay by default. |
| 2. Independent timing | Camera height, aim, camera target, light height and light target each have their own keys. Existing lens keyframes are reused. Pace keys use route progress. | The same channel editor is available in Director and Shot Studio. |
| 3. Compound routes and short cuts | Spiral, S-curve, arc into push, pass-by and three-beat oner are selectable. Consecutive edit beats can share one take and one calibrated setup. | Compound routes family; Director → Share one continuous take. |
| 4. Light timeline | Independent XYZ target and height. BR60 brightness/colour remain manual; no control adapter or remote protocol is documented. | Highlight walk preset; `configs/rig.json` electrical-control evidence. |
| 5. Cart breath | Opening/closing stationary holds and quintic entry/exit demand feed the existing quantized forward follower. Settling commands are integrated into endpoint evidence. | Cart breath in the channel editor. |
| 6. Configured policy, unchanged limits | Cart pace remains 0.35 m/s maximum; filming trajectories retain the exact previous 11 encoder counts per 40 ms. Policy now comes from arm commissioning configuration. | `configs/arm-execution.json` → `previs_policy`. |
| 7. Honest reposition timing | Inter-shot turns are explicitly an idealized diagram. Reset segments and the rehearsal total are labelled as a minimum, with extra forward-only/manual reset time unestimated. | Full rehearsal clock and move notes. |
| 8. Product study | Highlight walk, macro-style pass, object orbit, foreground reveal and negative-space drift. Scripts can contain zero actors. Product and plinth proxies join the object library. | Product study family; the saved cinematic demonstration. |

### Corrections and design decisions

- **No limit was raised.** The earlier proposal to lift ceilings requires new physical
  evidence. Moving the existing values into configuration does not provide that evidence.
  The audit rounded the trajectory rate to 0.42 rad/s; preserving its actual count step
  gives 11 × 2π / 4095 / 0.04 = approximately 0.42195 rad/s, unchanged.
- **Setup already sits outside edit time.** It never prevented a sub-two-second cut.
  Standalone stationary filming now accepts 0.5-second slots, with its full setup retained.
  Shared takes explicitly amortize setup across consecutive source windows. The last beat
  rehearses the complete remaining take, even when the edit trims its tail; the software
  never implies an unplanned mid-route stop.
- **Old rise_start/rise_end settings remain as a compatibility input.** Independent keys
  override only their own channel. Removing the old fields would lose saved intent.
  Golden fixtures capture the original 28 settings, camera/light poses, lens values, arm
  samples and every cart command; all matched exactly in the targeted regression.
- **Pace uses route distance; the other channels use filming time.** A speed key belongs
  to a bend even when the motor model changes the take duration. This avoids a circular
  dependency between the duration being solved and a speed schedule that defines it.
- **Smooth demand is not a claim of smooth physical motion.** The 0.01 command grid,
  200 ms decision interval and finite deadband remain visible in prediction. There is no
  invented slow creep, dynamics model, minimum focus distance or physical depth-of-field
  evidence. Macro-style means tight simulated framing.
- **The light ships position-only.** The [NEEWER BR60 product page](https://neewer.com/products/neewer-br60-5-ring-light-with-clip-mini-tripod-66605823)
  documents button controls and USB power; it does not document a remote/data protocol.
  No TakeOne electrical adapter is implemented. This does not establish that a later
  hardware modification is impossible.

Recovery, contracts, reproducible commands and final verification are recorded in
[`ai-director/implementation/06-cinematic-channels.md`](ai-director/implementation/06-cinematic-channels.md).

---

## 9. Evidence

Measured this session by running the existing compiler against
`configs/rig.json`, `configs/cart-response.json`, `configs/arm-execution.json`:

- Command grid enumeration: 168 usable pairs, 12 straight speeds, tightest radius 0.29 m,
  curvature slew 2.2 s.
- Compound route compiles: straight, S-curve, spiral, figure-eight, hairpin, 0.35 m and
  0.6 m circles, 31 m serpentine, 88 s three-beat. Endpoint errors 0.2–2.3 cm.
- Aim/height/pace sweeps with correct subject standoff: tables in §1 and §5.
- Setup overhead across 6 presets: 5.48–5.96 s.
- Template census: 28 presets, 8 routes, 9 aims, 7 distinct durations, 19 of 28 at
  8.82 s or 10.0 s.

**One correction worth recording.** An earlier pass of this audit measured 83° of aim error
on a *straight line* and nearly concluded the aiming solver could not track curves. The
cause was the test itself: those paths ran straight through the subject at the scene origin,
so the camera passed over the actor's head. Re-run with proper standoff, the same straight
line gives 0.29°. Any future envelope testing must keep the route clear of the subject.

Researched with sources, flagged where unverifiable:

- Verified: Flair's four-layer architecture, 500 axes, 512 DMX channels, independent
  and reversible target velocity; MRMC "Vertical Orbital" case study; *Severance*
  motion-control dolly zoom (15→40 mm while pushing away); Bolt track 5 m/s and camera
  11 m/s; KIRA ±0.05 mm repeatability; Cutting et al. ASL data; Lewin on trapezoidal jerk;
  Honda "Cog" two-take stitch and 1.6 mm part placement; Philips "Carousel" 139 s.
- **Not verified:** no vendor publishes a compound-move taxonomy; no peer-reviewed
  commercial ASL corpus exists; **no shot-length measurement for Apple product films
  exists**; no published resonance figure for any of these rigs, so the pre/post-roll hold
  durations in §7 are derived, not measured.

Nothing in this document was tested on hardware. Items 4, 5, 6 and 7 all touch real motion
limits and must go through the existing commissioning path with measured evidence before
they run on the robot.
