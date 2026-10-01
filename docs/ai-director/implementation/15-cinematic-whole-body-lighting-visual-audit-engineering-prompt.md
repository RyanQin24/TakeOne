# TAKEONE — Cinematic Whole-Body Choreography, Day/Night Lighting & Visual Proof Engine

## Engineering implementation prompt

You are the lead robotics, cinematography, controls, simulation, frontend, and software-quality engineer responsible for the next major TakeOne upgrade.

This task is **not** “add more camera movement presets.”

This task is to transform TakeOne from a library of individual robot movements into a **cinematic choreography system** capable of planning coordinated story-driven motion among:

```text
ACTOR
+
CART
+
PHONE CAMERA ARM
+
LIGHT ARM
+
CAMERA AIM
+
CAMERA HEIGHT
+
LENS
+
SCENE / FOREGROUND
+
DAY / NIGHT LIGHTING
+
SHOT TIMING
```
The finished system must generate and rehearse shots that feel like intentional movie-camera choreography, rather than a robotic demonstration of `push`, `pull`, `orbit`, `pan`, or `boom` in isolation.

Do not merely make actuators move more.
Do not increase motor limits to create excitement.
Do not claim a shot is cinematic because several numbers changed.
The final result must be **visibly convincing in the rendered camera view**.
You must prove that visually.

## 0. Non-negotiable working rule

Do not report this feature complete because tests passed, because cart distance or arm encoder deltas are nonzero, or because source code contains the new feature.

You must:

1. inspect the current codebase;
2. audit every existing movement visually;
3. establish numerical baseline evidence;
4. implement the new architecture;
5. render all relevant shots again;
6. inspect those renders using visual intelligence;
7. identify bad-looking movements;
8. iterate;
9. rerun the visual audit;
10. provide reproducible evidence proving what changed.

The final evaluation is based on **what the camera actually sees**, not primarily on internal actuator activity.
## 1. First read the real project

Before modifying code, read:

```text
AGENTS.md
CLAUDE.md
README.md
docs/architecture.md
docs/arm-movement-design.md
docs/calibration-inventory.md
docs/robot-commissioning.md
docs/ai-director/implementation/06-cinematic-channels.md
docs/ai-director/implementation/07-shot-language.md
packages/takeone/director/robot-film-director/SKILL.md
packages/takeone/director/filming-skills/*/SKILL.md
packages/takeone/previs/templates.py
packages/takeone/previs/compound.py
packages/takeone/previs/channels.py
packages/takeone/previs/program.py
packages/takeone/previs/path.py
packages/takeone/previs/choreography.py
packages/takeone/director/motion_contract.py
packages/takeone/director/scenes.py
apps/rehearsal/dist/orbit.js
apps/rehearsal/dist/scene-library.js
apps/rehearsal/dist/shot-library.js
apps/rehearsal/dist/choreography-review.js
```
```text
scripts/moving_camera_showcase.py
scripts/cinematic_upgrade_demo.py
scripts/shot_language_demo.py
scripts/first_turn_demo.py
configs/rig.json
configs/arm-execution.json
configs/cart-response.json
configs/iphone-camera.json
```

Also inspect the current dirty working tree.
Do not overwrite unrelated changes.
Do not restore files indiscriminately.
Do not rewrite calibration files.
Do not open serial ports.
Do not actuate real hardware.

Everything in this work package must remain **simulation/offline only** unless the user separately authorizes a supervised physical run.

## 2. Current audit findings — treat these as problems to solve

The current movement library contains **38 movement presets in 8 families**.
Only three default presets actually contain a walking performer:

```text
track_follow
track_lead
side_track
```
Five presets are product-only. Approximately thirty default to a stationary performer.

Many existing shots technically coordinate cart and arms but do not produce a visually meaningful camera transformation. Basic follow/lead/side tracking can move the cart around 1.5 m while the phone arm changes only modestly; visually this often reads as a centered subject with only a mild background shift.

Some current presets do contain substantial cart + phone-arm choreography:

```text
hero_orbit
crane_reveal
s_curve
arc_push
pass_by
three_beat
product_reveal
```

Those are important foundations. Do not delete them.

## 3. Current duration problem

Some existing capability demonstrations are too long for ordinary cinematic beats at the current cart pace:

```text
spiral         ~35 s
s_curve        ~43 s
arc_push       ~58 s
pass_by        ~26 s
three_beat     ~58 s
orbit_360      ~104 s
```
These remain useful low-level capability studies and should stay available, but a normal short-film camera phrase should often operate around **4–12 seconds** unless a deliberately long take is requested.

Do **not** solve this by exceeding existing motor or cart policies. Create shorter cinematic variants through smaller paths, smaller arcs, better base placement, purposeful phone-arm movement, foreground blocking, actor choreography, and camera-target changes.

## 4. Core architectural change

Stop treating **cart path** as the primary cinematic object. The primary object is the **desired camera experience**.

```text
USER BRIEF
    ↓
STORY BEATS
    ↓
SHOT INTENT
    ↓
CINEMATIC MOTIF
    ↓
DESIRED OPTICAL TRAJECTORY
    ├─ composition
    ├─ framing
    ├─ target
    ├─ camera position/orientation
    ├─ lens
    └─ timing
    ↓
WHOLE-BODY CHOREOGRAPHY SOLVER
```
```text
WHOLE-BODY CHOREOGRAPHY SOLVER
    ├─ CART
    ├─ PHONE ARM
    ├─ ACTOR
    ├─ LIGHT ARM
    └─ LENS
    ↓
EXISTING TAKEONE MOTION COMPILER / IK
    ↓
ACTUAL ACHIEVED OPTICAL TRAJECTORY
    ↓
SHOT REVIEW
    ↓
VISUAL SIMULATOR
```

The system should reason **“What should the audience see?”** before **“Which wheels and joints move?”**

## 5. Do not replace the 38 low-level movements

The existing movement templates are low-level mechanisms. Keep them.
Do not turn the library from 38 into 70 arbitrary presets unless a genuinely new physical primitive is required.

Instead introduce a layer above them: **CINEMATIC MOTIFS**.

A cinematic motif is a story-driven recipe composed from existing movement capabilities, independent channels, actor blocking, foreground staging, lens behavior, and lighting.

Potential module location:

```text
packages/takeone/director/cinematic_motifs.py
```
## 6. Implement a cinematic motif catalog

Initial motifs must include at least these concepts:

### Walk-and-talk lead → angle change

Actor and cart initially travel together. Phone framing remains relatively stable. Near the end, the actor slows, the cart continues briefly, and the phone arm changes aim or height so the visual relationship evolves rather than remaining a constant follow.

Target filming duration: **6–10 s**.

### Side-track → push

Actor walks while the cart matches laterally. Then the actor slows or stops while the cart transitions into a small forward emphasis and the phone arm compensates framing.

Story rhythm:

```text
movement
→ recognition
→ emphasis
```

### Foreground reveal → short push

Use a doorway, screen, shelving edge, tree, pillar, or other foreground object. Camera begins partially occluded, cart clears the obstruction, phone arm makes a subtle height/aim adjustment, then the system performs a short approach.

Target filming duration: **5–9 s**.
### Low-to-eye hero push

Do not use the current huge hero-orbit default as the only “hero” answer. Use a small cart approach plus optical rise, small target correction, and light repositioning.

Example intent:

```text
start around upper torso / lower perspective
approach ~0.5–0.9 m
rise ~0.08–0.20 m where feasible
finish near eye-level emphasis
```

Actual IK and constraints determine the achievable values.

### Pass-by → pan back

The cart passes the actor or object while the phone arm retains attention. The base may continue forward while the camera looks progressively sideways/backward within feasible arm limits.

This motif must demonstrate why a moving phone arm matters: **cart movement and camera viewing direction are not the same thing.**

### Dialogue attention arc

Do not continuously orbit talking actors. Begin in one conversational composition, move only when dramatic attention changes, then settle.

Typical pattern:

```text
hold
→ short 15–30° arc
→ settle
```

Respect the line of action and eyeline continuity.
### Retreat-to-context reveal

Begin relatively close. The actor completes a decision or reaction. The cart retreats while the phone arm adjusts height/aim so the performer becomes smaller and new environment enters the composition.

### Actor stop / camera continue

Actor moves during the first half, then stops. Camera continues for another roughly 0.5–1.5 s, producing parallax and emphasis without forcing simultaneous motion across the entire take.

### Camera stop / actor continue

Inverse motif. Robot settles first; actor continues through the composed frame. This proves that cinematic choreography is not “move everything constantly.”

### Three-beat oner

Reimplement the existing conceptual `three_beat` as a practical short-film motif:

```text
BEAT 1 — DISCOVER
short lateral reveal

BEAT 2 — FOLLOW
actor walks + cart follows

BEAT 3 — SETTLE
actor stops
cart finishes
arm reframes
light settles
```

Target: **8–12 s**, not ~58 s.
### Product parallax + light sweep

Product stays fixed. Cart performs a short lateral or shallow arc movement. Phone arm performs small framing compensation. Light arm independently changes target/position to reveal form.

The rendered product must visibly show:

```text
background parallax
+
highlight position change
+
surface/form change
```

### Doorway arrival

Actor emerges from or passes a doorway. Use foreground architecture. Robot first discovers the actor, then begins tracking. Actor and robot movement do not need to begin at exactly the same time; the temporal relationship is the point.

## 7. Represent shots as phases

Cart and arm do **not** need to move simultaneously for the whole shot.

Represent choreography explicitly by phases or an equivalent minimal validated structure. Conceptual example:

```json
{
  "beats": [
    {"at": [0.0, 0.18], "actor": "walk", "cart": "hold", "phone": "hold", "light": "track"},
    {"at": [0.18, 0.62], "actor": "walk", "cart": "travel", "phone": "track_and_rise", "light": "side_key"},
    {"at": [0.62, 0.82], "actor": "settle", "cart": "travel", "phone": "reframe", "light": "settle"},
    {"at": [0.82, 1.0], "actor": "hold", "cart": "hold", "phone": "hold", "light": "hold"}
  ]
}
```
Do not necessarily expose that exact JSON publicly. Design the smallest representation that fits TakeOne's existing contracts.

## 8. Introduce optical trajectory intent

Use existing capabilities such as:

```text
camera_position_m
camera_target_m
camera_height_m
pan_rad
tilt_rad
roll_rad
focal keyframes
```

as one coherent **optical path**, not miscellaneous overrides.

A desired camera state at time `t` should conceptually contain:

```text
C*(t) = {
    optical_position,
    target,
    horizon,
    focal_length,
    subject_screen_goal
}
```

The physical state contains cart pose, five phone joints, five light joints, performer pose, and lens state.

The achieved camera transform remains based on the real chain:

```text
T_world_camera =
T_world_cart · T_cart_phone_mount · FK_phone(q_phone) · T_tool_camera
```
The lighting transform is analogous.

## 9. Whole-body decomposition

Do not introduce ROS or a giant robotics framework. Do not rewrite the current planner. Build on TakeOne's deterministic compiler with a bounded offline decomposition strategy.

Suggested flow:

```text
1. Generate desired optical keyframes.
2. Generate several feasible base-route candidates.
3. Sample the shot timeline.
4. For each base candidate:
   - solve phone-arm IK
   - solve light-arm IK
   - evaluate actor composition
   - evaluate camera error
   - evaluate joint margin
   - evaluate clearance
   - evaluate smoothness
5. Adjust candidate placement/path where needed.
6. Select the best valid candidate.
7. Compile through the existing canonical planner.
8. Independently verify achieved FK and screen-space composition.
```

Do not directly send desired optical trajectories to hardware. The existing compiler remains authoritative.

## 10. Optimization / selection objective

Use explicit costs rather than an arbitrary “cinematic score.”
Conceptually:

```text
J =
w_pos       * camera_position_error²
+ w_aim     * camera_target_error²
+ w_screen  * screen_composition_error²
+ w_horizon * horizon_error²
+ w_joint   * joint_limit_margin_penalty
+ w_delta   * joint_motion_smoothness
+ w_base    * undesirable_base_motion
+ w_clear   * clearance_penalty
+ w_light   * lighting_geometry_error
```

Do not invent a single “cinematic score = 93.” Cinematic quality is not a scalar we can truthfully prove. Expose concrete measurements instead.

## 11. Respect the nonholonomic cart

Use the real cart constraints.

Conceptually:

```text
x_dot     = v cos(theta)
y_dot     = v sin(theta)
theta_dot = omega

v_left  = v - b * omega / 2
v_right = v + b * omega / 2
```

Continue using TakeOne's existing exact wheel integration and UART policy. Do not create sideways cart motion, fake strafing, silently reverse the cart, or exceed current forward-only behavior.
## 12. Do not change current hardware limits

Current software policies are not measured motor capabilities. Preserve the configured cart pace ceiling, arm command policy, UART cap, forward-only/reverse restrictions, and existing arm calibration ranges.

Do not increase these values to make shots shorter. Current loaded dynamic capability remains unqualified.

## 13. The light arm must become cinematographic

A large light-arm motion is useless if the camera image barely changes. The light arm is not merely “point light at actor face.”

Introduce cinematographic light roles such as:

```text
key
fill
eye_fill
edge
product_glint
practical_motivated
background_accent
```

A role defines a spatial intention, not a servo pose.

Example side-key intention:

```text
target: actor upper face / torso
desired side: approximately 30–60° away from camera axis
vertical relationship: slightly above face where feasible
distance: bounded by real arm/cart geometry
intent: model dimensionality rather than frontal flattening
```

These are goals constrained by reach and staging, not universal hard-coded truths.
## 14. Add light position control

Current independent channels include:

```text
light_height_m
light_target_m
```

Investigate adding a validated optional:

```text
light_position_m
```

analogous to `camera_position_m`.

It must represent the desired light emitter centre in the fixed shot frame, never a servo position. The light IK solver decides the joints.

If arbitrary light position + aim is infeasible, report the achieved result rather than clipping silently. Preserve legacy behavior when this channel is absent.

## 15. BR60 hardware truth

Do not invent remote brightness control.

Treat BR60 brightness and colour-temperature mode as **setup metadata**, not automatically actuated channels, unless a supported electrical-control adapter is actually implemented and verified.

Current automated light variables are position, height, aim, relative side, distance, and timing.

The Director should be able to give an operator pre-take cue such as:

```text
LIGHT PLAN
Role: soft side fill
Robot position/aim: automated
Brightness: set manually before take
Colour temperature: set manually before take
```
## 16. Rebuild atmosphere / time of day

TakeOne currently supports:

```text
exterior_day
exterior_dusk
exterior_night
interior_day
interior_warm
interior_cool
studio
```

These must become real, visually differentiated **lighting profiles**, not background-color aliases.

Create a deterministic profile structure similar to:

```text
AtmosphereProfile {
  background
  ground
  hemisphere_sky / hemisphere_ground / hemisphere_intensity
  key_color / key_intensity / key_direction
  rim_color / rim_intensity
  robot_light_scale
  practical_scale
  optional_fog
}
```

Keep it compact, testable, and free of hardware effects.
## 17. Exterior day

Day exterior should communicate a dominant directional source, clear shadow direction, bright environmental fill, and the robot fixture acting mainly as local fill / eye light.

The BR60 proxy must not overpower simulated daylight. Its contribution should still be visible when close enough, but never behave like a giant cinema lamp.

## 18. Exterior dusk

Dusk should use a weaker warm directional source, cooler environmental fill, and stronger relative practical / robot-light contribution. Do not simply tint everything orange.

## 19. Exterior night

Night must actually look like night:

```text
significantly reduced ambient contribution
cool or neutral environmental baseline
very weak moon-like directional contribution if used
practicals visibly meaningful
robot light visibly meaningful
background retains readable information
```

Do not produce a dark-blue background with daytime subject illumination.

## 20. Interior day / warm / cool

Interior profiles need distinct source logic: window-like daylight for `interior_day`, motivated warm practical logic for `interior_warm`, and a different cool-source balance for `interior_cool`.
## 21. Practical light objects must actually light the scene

A scene object with `asset_id = practical_light` must not merely be an emissive-looking box. Give it an actual bounded Three.js light proxy.

Manage its lifecycle correctly. When switching scenes, remove/dispose old practical lights. Do not leak lights across scenes. Limit active practical sources and avoid hundreds of dynamic shadow casters.

## 22. Robot light must affect the camera output

The simulated BR60 source must follow the actual simulated light-arm pose:

```text
frame.light.pos
frame.light.quat
```

The camera monitor must visibly show its effect.

Provide an optional debug visualization for emitter position, target ray, approximate cone, and light role, but keep those overlays out of final captured camera output unless explicitly enabled.

## 23. Do not claim photometric accuracy

The BR60's real distribution and installed bracket transform are not fully calibrated. Label simulator lighting as **visual lighting preview**, not predicted lux.

Relative influence can be measured; physical illuminance cannot be claimed until photometric calibration exists.

## 24. Day/night camera capture plan

Add a capture/setup concept for frame rate, shutter mode/angle, white balance, ISO, and exposure lock, while keeping requested, operator-confirmed, and actual device-readback evidence distinct.
## 25. Lock exposure / white balance for a take

The cinematic workflow should assume:

```text
meter/setup
→ confirm
→ lock
→ record
```

not continuous arbitrary auto-exposure during a choreographed shot.

If a requested lock cannot be performed remotely by the verified Blackmagic integration, state **manual operator setup required** instead of pretending.

## 26. Update Director reasoning

Update:

```text
packages/takeone/director/robot-film-director/SKILL.md
packages/takeone/director/filming-skills/cinematic/SKILL.md
packages/takeone/director/filming-skills/dialogue/SKILL.md
packages/takeone/director/filming-skills/reaction/SKILL.md
packages/takeone/director/filming-skills/product/SKILL.md
```

Teach the chain:

```text
story beat → audience attention → actor blocking → camera relationship → lighting relationship → physical movement
```

not “pick random fancy preset.”
## 27. Stillness remains valid

Do not create a rule saying every shot must move. A static shot can be excellent, but stillness must be intentional.

The planner should distinguish `intentionally_static` from “we used static because it was easy.”

## 28. Motion diversity

For a normal cinematic short containing action/locomotion, avoid generating an entire film of static frames.

The Director should consider at least one meaningful moving-camera beat and, where the story contains performer locomotion, at least one shot where performer movement and robot/camera movement form one choreography.

Do not force these where inappropriate.

## 29. Update curated examples

Examples influence model behavior and therefore must be reauthored.

### Product sample

Use a short push-in, intentional static detail, and a small product arc/parallax + light change.

### Dialogue sample

Use a small conversational establishing arc, intentional static reaction, and a small release/pull-back without crossing the line of action.

### Reaction sample

Use a lateral reveal, short push, and a walking side-track/exit. The final shot is a strong place for actor travel + cart travel + phone-height or aim adjustment.
### Cinematic sample

Make this the strongest general demonstration of actor + cart + phone + light + foreground + lighting + lens + story beats without turning it into a long robot-demo reel.

## 30. Extend motion requirements

Extend existing motion requirements carefully to cover light behavior. Potential additions:

```text
light_translation_m
light_rotation_rad
light_role
```

Maintain backward-compatible defaults.

Review evidence should expose:

```text
actor path
cart path
optical camera path
phone-arm-relative movement
light-arm-relative movement
lens change
overlap intervals
```

## 31. Distinguish coordination from simultaneity

Report both simultaneous overlap and coordinated sequential phases.

Example:

```text
0–2 s  actor walks
1–5 s  cart joins
3–6 s  phone rises
5–7 s  actor holds
5–8 s  cart finishes and arm settles
```
## 32. Measure meaningful movement

Do not count tiny numerical jitter as meaningful camera choreography.

Track actor root travel, cart powered-axle travel, optical camera path, phone optical motion relative to cart, and light emitter motion relative to cart. Use documented thresholds for diagnostics/evidence only, not as artistic scores.

## 33. Add parallax evidence

For known staged objects, project object centres into camera space and measure relative screen-space displacement across the shot.

Report a concrete proxy such as:

```text
foreground/background screen separation changed by X normalized units
```

Use this to detect “robot moved but shot still looked visually dead.” Do not call it a cinema score.

## 34. Make foreground part of shot design

Use existing scene objects such as doorway, arch, screen, shelf, table, counter, tree, wall edge, and practical light to create reveal, depth, occlusion, entrance, exit, and parallax.

Do not move the set during the shot to fake camera motion.

## 35. Lighting motivation

Connect the light role to the scene: window motivation, practical lamp, doorway spill, night practical, soft camera-side fill, or product edge light.

Do not create a random roaming spotlight merely because the light arm can move.
## 36. Frontend

In Director and Shot Studio expose only information that helps the filmmaker. Potential UI additions:

```text
Cinematic motif
Lighting role
Atmosphere
Camera movement phases
Actor / cart / phone / light timeline
```

A compact timing view may look like:

```text
TIME       0──────2──────4──────6──────8
ACTOR      WALK──────────SETTLE────HOLD
CART       HOLD──MOVE──────────────HOLD
PHONE      HOLD────TRACK+RISE──────HOLD
LIGHT      TRACK────────SIDE KEY───HOLD
LENS       35mm────────────────────────
```

## 37. Do not overload the UI

Most users should choose story, mood, and shot intention — not manipulate every joint.

Keep the product boundary:

```text
Director    = intent
Shot Studio = inspect / refine / prove
```

Advanced controls may expose low-level channels.
## 38. Rendering performance

Respect the existing invalidation-driven renderer architecture. Do not add an unconditional `requestAnimationFrame(...)` loop.

Dispose created geometries, materials, textures, and lights when scenes change. Night lighting must not turn the simulator into a GPU benchmark.

## 39. No hardware side effects

Absolutely no serial open, torque enable, cart packet, camera record command, or motor movement during imports, unit tests, visual audit, browser testing, or CI.

Physical playback remains a separately authorized operator action.

## 40. Before implementation: capture a visual baseline

Before changing the targeted subsystem, capture the current visual state of **every one of the 38 existing movement templates**.

For every template render:

```text
0%
25%
50%
75%
100%
```

of the filmed portion.

This produces at least **190 rendered states**.

Use `window.takeonePreview.frame(...)` or the existing deterministic browser capture system. Do not depend on FFmpeg merely to inspect PNG frames.
## 41. Create contact sheets

Group baseline images by family:

```text
Hold & reveal
Dolly & lens
Follow & travel
Arc & orbit
Height & perspective
Roll & handheld
Compound routes
Product study
```

Each template row must show name, start, 25%, 50%, 75%, and end. Produce actual PNG contact sheets, not only JSON.

## 42. Use visual intelligence

After generating contact sheets, **open them and inspect them visually**.

For every family write specific observations such as:

```text
actor framing barely changes
arm motion is not perceptible
foreground object creates useful reveal
subject leaves desired area
movement feels mechanically constant
night lighting remains too bright
light highlight is visually absent
camera rise is visible
composition settles well
```

Do not infer these observations from code or metrics. Actually inspect the images.
## 43. Audit all stored examples

Do not only inspect the 38 template defaults. Audit every active cinematic example/demonstration that matters to the product, including at minimum:

```text
cinematic sample
product sample
dialogue sample
reaction sample
shot-language demonstration
moving-camera showcase
cinematic-upgrade demonstration
First Turn
current saved/rehearsal examples referenced by maintained docs
```

Do not recursively treat recovery snapshots as active examples; recovery is evidence/history.

## 44. Create a baseline metrics report

For each shot collect:

```text
template / motif
filming duration
cart path length
actor path length
optical camera path length
phone-arm-relative translation / rotation excursion
light-arm-relative translation / rotation excursion
focal change
screen-target error
meaningful overlap intervals
parallax proxy
atmosphere
```

Store these in machine-readable JSON.
## 45. Implement the feature only after the baseline exists

Suggested implementation order:

```text
1. atmosphere / lighting-profile engine
2. real practical lights
3. robot-light rendering improvements
4. light role + optional light-position channel
5. cinematic motif schema/catalog
6. optical trajectory abstraction
7. whole-body decomposition
8. movement-phase representation
9. extended choreography review
10. Director skill/sample upgrades
11. Shot Studio timeline / evidence UI
12. audit tooling
```

## 46. Preserve legacy movement contracts

Existing legacy movement tests deliberately pin old motion behavior. Do not casually rewrite them.

The 38 low-level templates should remain reproducible unless a change is explicitly intended and reviewed. The new system should live **above** the low-level library whenever possible.

## 47. Automated tests — motif layer

Every motif must have tests for schema validation, deterministic output, duration, valid low-level template use, valid parameter bounds, actor/cart/camera/light paths, no teleport, no NaN/Infinity, clear timing, and compatibility with the canonical compiler.

## 48. Automated tests — whole body

Test forward-only base constraints, route continuity, camera position error, target error, IK feasibility, joint margins, trajectory smoothness, clearance, and failed-intent behavior.
## 49. Automated tests — atmosphere

For every atmosphere profile verify finite values, known color representation, bounded intensities, required lights, cleanup, and no accumulated practical lights.

Also verify actual rendered output differs between `exterior_day` and `exterior_night`.

## 50. Image-based day/night test

Render the exact same scene/camera pose as:

```text
exterior_day
exterior_dusk
exterior_night
```

Store all images. Pixel/luminance statistics are supplemental only; visual inspection is required.

Night must visibly have a darker environmental baseline, a different source relationship, and stronger relative practical/robot-light contribution.

## 51. Robot-light A/B test

Construct one night scene and capture the exact same camera pose with:

```text
robot light disabled
robot light enabled
```

The actor/object must visibly change. Moving the lamp object alone is not evidence; the camera image must change in the intended subject region.
## 52. Light-target movement test

For a product-lighting shot render start, middle, and end.

The highlight/form on the product must visibly change. If the light arm moves thousands of counts but the product looks identical, **FAIL THE VISUAL TEST** and fix the renderer/lighting design.

## 53. Actor + cart + phone test

Create at least one canonical verification shot where:

```text
actor travels
cart travels
phone optical relationship changes
```

The phone motion must be more than aim compensation or tiny jitter. Capture at least five frames and make all three effects visually understandable in the contact sheet.

## 54. Sequential choreography test

Create another canonical shot where the subsystems deliberately start/stop at different times:

```text
actor begins
cart joins
actor stops
cart continues
arm settles
```

Visually prove those phases.

## 55. Light + camera coordination test

Include one shot where cart, phone, and light have independent timings. The final camera images must show that the light is doing visual work rather than merely moving in the world view.
## 56. Curated motif acceptance targets

For the new cinematic showcase, aim for at least **10–12 useful motifs**.

At least **6** should visibly combine meaningful cart motion with meaningful phone-camera-arm behavior.
At least **3** should involve actor locomotion plus robot/camera motion.
At least **4** should demonstrate an intentional light-arm contribution.

These are showcase acceptance targets, not universal artistic rules imposed on every generated film.

## 57. Shorter default cinematic demos

New motif demonstrations should normally target **4–12 seconds** of filmed motion.

Do not modify original long-form low-level presets merely to satisfy this; parameterize compact motif variants above them.

## 58. Check screen composition

Use TakeOne's existing projection/framing systems. Measure actual achieved face/body region, subject size, screen position, and visibility.

Do not trust intended framing labels alone.

## 59. Check set depth

Cinematic sample scenes should intentionally consider foreground, subject plane, and background where appropriate.

A blank stage is not sufficient to evaluate parallax.

## 60. Exposure / white-balance proof boundary

Software tests may prove validated setup plans, persistence, readback distinction, manual-required state, and REST mapping logic. They may not prove that a real iPhone captured correct exposure without actual device evidence.
## 61. Cross-platform development

The project runs on Windows and is also developed from macOS. Make offline/simulator tooling work on both where practical.

Do not make a new audit tool PowerShell-only unless the underlying functionality is also callable through Python/Node. Hardware execution may remain Windows-specific.

## 62. Build a reproducible audit command

Add something similar to:

```bash
python scripts/cinematic_motion_audit.py \
  --base-url http://127.0.0.1:8766 \
  --output data/cinematic-choreography-audit-YYYYMMDD
```

Exact interface is your design decision.

It should produce:

```text
manifest.json
movement-metrics.json
atmosphere-metrics.json
contact-sheets/
frames/
visual-audit.md
browser-console.json
summary.json
```
## 63. Visual-audit report

`visual-audit.md` must be specific, not generic.

Good example:

```text
PASS — foreground-reveal-push
Start: screen obscures approximately one-third of subject.
25%: screen edge crosses frame and reveals actor.
50%: cart now contributes lateral parallax.
75%: phone arm raises optical origin and preserves eye placement.
End: camera stops before actor; clean held final frame.
Lighting: night practical remains background motivation while robot fill keeps eyes readable.
```

Bad example:

```text
Looks cinematic. PASS.
```

Do not write the bad form.

## 64. Iterate from the images

The first implementation is not automatically final. After visual audit, identify bad shots, change parameters/architecture, rerender, reinspect, and repeat until acceptance conditions are met.

## 65. Test visual jumps

Render adjacent frames around phase boundaries, keyframes, and motif transitions. Look for camera teleport, actor teleport, light teleport, frame jumps, sudden lens jumps, horizon snaps, and IK branch switches.
Automated delta checks should supplement visual inspection, not replace it.

## 66. Test the simulator camera, not only world view

World view is useful for robot geometry, but final cinematography is judged primarily through the **SIMULATED PHONE CAMERA**.

Preserve both where useful:

```text
WORLD | PHONE
```

but make cinematographic judgements from phone output.

## 67. Do not fake success

A shot is allowed to fail. Examples:

```text
desired optical trajectory unreachable
phone arm saturates
light cannot reach desired side
cart geometry collides
subject leaves frame
night scene becomes unreadable
duration too long
```

Keep the failure, explain why, and revise the intent. Do not weaken validators merely to turn a red result green.

## 68. Hardware reality

Do not change motor PID, servo voltage, firmware, calibration, command cap, watchdog, or loaded limits as part of this feature.

Smarter choreography is preferable to simply faster or larger motion.
## 69. Final full verification

After focused tests succeed, run the appropriate complete repository verification.

On Windows:

```powershell
.\scripts\TakeOne.ps1 -Command test
```

On macOS, run the equivalent supported Python/npm checks if PowerShell tooling is unavailable.

Record every failure and distinguish:

```text
new regression
existing environment issue
pre-existing dirty-tree failure
missing optional dependency
```

Do not hide unrelated failures.

## 70. Final visual proof package

Before declaring completion, provide visual evidence containing:

```text
all-38 movement baseline contact sheets
all-38 post-change regression contact sheets
cinematic motif contact sheet
actor+cart+phone choreography sheet
sequential choreography sheet
day vs dusk vs night comparison
robot-light off/on comparison
product-light movement comparison
day cinematic scene
night cinematic scene
```
If video export is available, also provide short rendered previews. Still-image evidence must exist even if FFmpeg is unavailable.

## 71. Final machine-readable evidence

Include:

```text
git commit / working-tree state
tested source hashes
browser version
Python version
Node version
38-template results
motif results
compile durations
movement metrics
visual artifact paths
test results
known limitations
hardware evidence boundary
```

## 72. Final acceptance criteria

Do **not** finish until all relevant conditions are satisfied:

- [ ] Existing 38 low-level movement templates still work.
- [ ] Legacy motion contracts remain preserved unless explicitly versioned.
- [ ] Cinematic motif layer exists above the primitive library.
- [ ] At least 10 useful motifs are implemented.
- [ ] New cinematic motifs generally fit short-film timing rather than 30–100 s robot demos.
- [ ] At least six showcase motifs visibly coordinate cart + phone-arm movement.
- [ ] At least three showcase motifs include actor locomotion + robot/camera motion.
- [ ] At least one verified example deliberately staggers actor, cart and arm movement instead of moving them simultaneously.
- [ ] Actor/cart/phone timing is visible in UI or review evidence.
- [ ] Phone optical movement is evaluated, not inferred from servo movement.
- [ ] Light-arm choreography is independently represented.
- [ ] Robot light visibly affects the simulated camera image.
- [ ] Practical lights illuminate scenes rather than being decorative meshes only.
- [ ] Exterior day visibly reads as day.
- [ ] Exterior dusk visibly differs from day and night.
- [ ] Exterior night actually reads as night.
- [ ] Interior day/warm/cool are visually differentiated.
- [ ] Night scenes use motivated practical/robot lighting rather than daytime ambient with a blue background.
- [ ] Product lighting changes are visible in rendered output.
- [ ] Camera exposure/WB setup distinguishes requested, manual-confirmed and device-readback evidence.
- [ ] No unsupported remote BR60 brightness/CCT control is claimed.
- [ ] Existing Blackmagic integration boundaries remain truthful.
- [ ] No motor/serial/hardware action occurs during tests or audit.
- [ ] No existing calibration or hardware limits were relaxed.
- [ ] All new schemas are backward compatible where required.
- [ ] Every motif compiles deterministically.
- [ ] Failed cinematography remains visible as failure rather than silently degrading.
- [ ] Every one of the 38 existing presets has been visually rerendered.
- [ ] Every contact sheet has actually been inspected with visual intelligence.
- [ ] Day/night contact sheets have actually been visually inspected.
- [ ] Light A/B contact sheets have actually been visually inspected.
- [ ] Cinematic motif contact sheets have actually been visually inspected.
- [ ] Visual problems found during audit were iterated on and rerendered.
- [ ] Focused unit/integration/browser tests pass.
- [ ] Full repository verification has been run and honestly reported.
- [ ] Final evidence package is reproducible.
## 73. Final product test

The old system:

```text
Actor stands there.
Choose: ARC LEFT.
Robot follows the arc.
Camera points at face.
```

The new system should be able to express:

```text
The actor enters through a doorway.
For the first beat, the camera waits.
The actor crosses the threshold.
The cart begins moving as the foreground clears.
The phone arm rises slightly while maintaining the eyes in the upper third.
The light arm shifts from soft frontal fill toward a motivated side fill.
The actor stops at the workbench.
The cart continues for another second, producing parallax.
The phone arm makes the final reframe.
The robot settles.
The actor looks toward the object.
Hold.
Cut.
```

That is the target behavior.
## 74. Engineering philosophy

TakeOne is not valuable merely because it has wheels, two arms, and moving motors.

Its defensible product value is:

```text
creative intent
    ↓
understanding of physical space
    ↓
cinematic optical planning
    ↓
whole-body robot choreography
    ↓
lighting choreography
    ↓
actor direction
    ↓
real physical camera capture
    ↓
evidence-based review
```

The simulator must prove why the physical robot is useful.

If the finished shots could be replicated just as convincingly by a stationary tripod with a digital crop, the implementation has not gone far enough.

## 75. Final instruction

Do not be satisfied with code-level success.
Do not be satisfied with actuator-level success.
Do not be satisfied with one cherry-picked demo.
Audit the system comprehensively.
Render it.
Look at it.
Criticize it.
Fix it.
Render it again.
Only stop when the evidence demonstrates that TakeOne now understands and rehearses **cinematic relationships between performer, camera, robot base, phone arm, light arm, environment, and time**, while preserving the real physical limitations of the rig.

When reporting completion, show the user:

```text
WHAT CHANGED
WHY IT CHANGED
WHICH FILES CHANGED
WHICH MOTIFS EXIST
WHICH EXAMPLES WERE UPGRADED
HOW DAY/NIGHT WORKS
HOW THE LIGHT ARM CONTRIBUTES
HOW ACTOR/CART/PHONE/LIGHT TIMING DIFFERS
THE MOTION METRICS
THE ACTUAL VISUAL CONTACT SHEETS
BEFORE/AFTER EXAMPLES
TEST RESULTS
VISUAL-AUDIT FINDINGS
KNOWN PHYSICAL LIMITATIONS
```

If any one of those is missing, the work is not complete.

## Research basis to preserve while implementing

Use professional camera-movement, mobile-manipulation, exposure, and lighting references as design input, but do not copy artistic styles or claim physical capabilities not established by TakeOne evidence.

The architectural principle is **cinematic motif → desired optical trajectory → whole-body physical decomposition → achieved visual evidence**.

Keep the existing 38 low-level movements as tested physical building blocks; the new value is the planning and proof layer above them.
