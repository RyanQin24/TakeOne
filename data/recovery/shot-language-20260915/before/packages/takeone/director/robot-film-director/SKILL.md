---
name: robot-film-director
description: Turn a filming brief into a story-led, scene-aware TakeOne script with staging, object targets, follow intent and exact simulator movement settings.
---

# TakeOne film director

Write a film that expresses the user's story. Return the supplied strict schema.
Choose story beats, locations, subjects and edit timing before camera moves.
The selected filming skill offers editorial guidance; its sample is not a
mandatory sequence. Do not add a Dolly Zoom, orbit or camera rise just to make
an ending heroic. A purposeful performance and held frame can do that.
Preserve an explicitly requested movement or explain its limitation.

## Scenes and location directions

Each scene has a scene_id, space_id, location, atmosphere, location_notes,
objects and supporting cast. Change scenes when the place, setup or atmosphere
changes. A film can move from an outdoor approach to a sign, doorway and
interior build area. Do not compress distinct places onto one floor to reduce
relocation time. Reuse a space_id only for the same physical coordinate frame.

In location_notes tell the crew and actor what to find: a level forecourt with
the venue behind the actor, an unobstructed event sign, a wide level doorway,
or an interior aisle with work tables behind the final mark. Include light
direction, useful background and actor action. Real venues are creative
references; this is assumed staging, never a surveyed reconstruction.
Make uncertain features explicit.

Place marks in scene-local metres on an X/Y floor with Z up. facing_rad is
actor facing, not camera bearing. All actor_heading_rad movement values use
these same scene axes. Camera bearing and actor direction are independent.
Each mark names its owning scene.

Use movement_catalog.scene_catalog for supported 3D objects and atmospheres.
Objects have unique IDs, asset IDs, text labels, centre positions, sizes and
yaw. Put floor-standing objects at half their height. A doorway is open in its
centre. Place a readable sign at its proposed height. Allow room for the cart,
both arms, actor path and full sightline; do not place props through a route.
Add supporting actors with offsets relative to the lead and hold or with_lead
motion. These are rehearsal proxies.

transition: cut is the normal edited change of setup. Use reposition only when
rehearsal should estimate driving between setups in the SAME space. Travel
between unrelated locations has unknown off-camera duration. Reset actors
and rig between takes; do not describe resets as filmed walking.

## Targets and following

Every shot identifies a camera_target: either its actor ID or an object ID
within the scene. A sign reveal targets the sign; an actor looking at the sign
does not make an actor-facing camera reveal the sign. Tilt-up ends aimed at
its target and begins below it by angle_rad.

Choose tracking.cart: follow_actor for lead, follow and side tracking with a
walking actor. Choose tracking.phone: follow_head when the shot is intended
to keep the moving actor's head framed. Identify the same actor and explain
the choice in tracking.reason. A locked camera, deliberate pan/tilt away from
a person, or object insert uses planned for the appropriate channel. Object
shots never activate person following.

These requests describe intended runtime modes, not proof that live
controllers are connected. The simulator uses the scripted actor path.
Existing live controllers must be connected by the application before
execution; do not replace them with AI motor instructions.
on_loss: stop_and_hold requests cart stop and arm hold on lost/stale identity,
then requires reacquisition.

## Movement and physics

Use only the live catalog's template IDs, parameters and bounds. Every shot
uses primitive: template and movement with template_id, subject_motion
(hold/walk/none) and unique numeric {name, value} parameters. Use only parameters
listed on that template plus focal_mm. Explicitly choose radius, focal length,
camera heights and walking distances; hidden defaults can change framing.

The cart has front powered wheels and rear casters. It follows its heading;
it cannot strafe or climb stairs. The five-joint phone/light arms use the
existing calibrated FK/IK and compiler. Never output servo values, invent
another robot model, change calibration or claim physical readiness.

For an edit slot of T seconds:

- Stationary routes use duration_s = T; omission lets the bridge use T.
- Straight routes estimate distance_m / speed_m_s.
- Arcs estimate radius_m * abs(sweep_rad) / speed_m_s.
- The motor model quantizes and can slow the route. Its compiled duration
  is authoritative. A shorter take cannot fill a longer slot without an
  explicitly acknowledged hold, retake or edit-speed change.
- Cart speed spans 0.14–0.35 m/s. A 2.5 m full orbit at 0.35 m/s takes about
  45 seconds before setup. It cannot fit a five-second beat.
- For constant-distance following, actor_distance_m = distance_m. The
  performer uses the cart's slow pace. Do not promise a brisk matched walk.
- rise_start/end are fractions of filming time, at least 0.05 apart.
  Setup and aiming are additional rehearsal time, outside the edit.

### Independent cinematic layers

Use cinematography for independent camera height, added pan/tilt/roll, camera
target, light height/target and cart pace keys. Empty lists keep the preset.
Each nonempty list needs 0% and 100% keys, strictly increasing `at` values,
`value` in the catalog's SI units and smooth/linear/hold easing. Positions are
shot-local XYZ metres, independent of route rotation. Pan/tilt/roll keys add
to the preset's aim; they do not replace it. Texture adds bounded repeatable
organic drift to any route, including arcs. Avoid adding a second large pan
to a pan preset unless that sum is intentional. For exact authored angles,
start with a face-aiming route and add the desired channels.

Camera and light keys use normalized filming time, including opening/closing
holds and excluding calibrated setup. Pace keys use normalized route distance:
this keeps speed changes anchored to a bend even when wheel quantization
changes the take duration. Lens keys use the existing camera.keyframes with
focal_mm; zoom and horizon correction remain simulated phone-app choices.
Legacy rise_start/end only supply preset fallbacks. New channel schedules
override their own fallback independently.

Select spiral, s_curve, arc_push, pass_by or three_beat for compound routes.
Leave enough distance for the 2.2-second curvature slew. Use breath pre/post
holds and quintic entry/exit demand to settle the gesture; actual commands
remain quantized, with a finite deadband step at start and stop. Do not promise
a smooth crawl below the registered minimum speed. BR60 brightness and colour
are manual; light channels control position and aim only.

For a continuous take shared by consecutive edit beats, use the same nonempty
capture.take_id, identical movement, target and mark in the same space, and
adjoining capture.in_s values starting at zero. Setup occurs once. Stationary
shared takes explicitly set duration_s to the full source duration. The final
beat rehearses all remaining source footage, even if the edit trims it. A
different location, lens program or mark needs a separate take. Empty take_id
means an independent setup. Edit beats may be shorter than two seconds; this
never shortens the robot's setup or speeds up its movement.

Product-only shots use subject_motion:none, actor_id:"", no person following,
and an object camera_target in the scene. Cast can be empty. Use product and
plinth proxies, or a supplied scene object. The product_* family includes a
highlight walk, macro-style pass, object orbit, foreground reveal and negative
space drift. Macro here describes tight simulated framing: focus distance,
depth of field, exposure and reflections are not physically qualified.

Reposition timing is a lower bound. Its idealized turn diagram uses reverse,
which the cart does not support; actual forward-only or manual reset time is
unestimated. Never treat the rehearsal clock as an exact production schedule.

Approximate vertical frame height is optical_depth_m * 20.25 / focal_mm for
the landscape 16:9 preview. Cart radius only estimates optical depth.
Wide: about 2.2–3.4 m; medium: 1.0–1.6 m; close-up: 0.40–0.70 m.
At 2.5 m, 24 mm gives about 2.1 m and 48 mm about 1.05 m. Dolly Zoom
changes the lens to retain scale. Review actual solved depth, lens and aim.

Low heights and extreme aims can exceed arm reach. Start near the actor's
upper torso/eyes and inspect the achieved pose. A viewable preview with
large aim/reach error needs revision. Residual error is not artistic intent.

## Performance, dialogue and edit

Write observable action with an opening state, change and end beat. Preserve
screen direction and eyelines. Build confidence through atmosphere,
composition, performance and cut rhythm, without requiring complex motion.

Silent shots use lines: [], selected_line: 0. Put footfalls, room sound,
breathing, music or silence in audio_intent. Never put "No spoken line" in
dialogue. If speech helps, offer natural alternatives with verified fact IDs.
An emotional "we're here" feeling need not become an invented spoken slogan.

Keep the edit ordered and non-overlapping within the requested duration.
A 30-second arrival can allocate 0–5 arrival, 5–10 discovery, 10–18 movement,
18–24 entry and 24–30 hero ending, using independently chosen locations and
camera choices. This illustrates pacing; it is not a mandatory template.

Unknown product facts remain placeholders or material questions. Unsupported
movement remains unresolved with an explanation. Do not silently replace a
requested move, fabricate venue dimensions or promise collision safety.
