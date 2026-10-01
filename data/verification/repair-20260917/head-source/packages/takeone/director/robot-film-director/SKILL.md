---
name: robot-film-director
description: Turn a filming brief into a story-led, scene-aware TakeOne script with staging, object targets, follow intent and exact simulator movement settings.
---

# TakeOne film director

Express the user's story in the supplied strict schema. Choose story beats,
locations, subjects and edit timing before movement. Apply the accompanying
shot-design and rehearsal-review skills. A selected filming skill's sample is
optional guidance, never a fixed answer. Preserve explicitly requested moves
or explain their limitations. A held performance can carry a hero ending.

## Stage distinct places

Each scene has scene_id, space_id, location, atmosphere, location_notes,
objects and cast. Change scenes with place, setup or atmosphere. Reuse space_id
only for the same physical coordinate frame. Keep distinct places distinct;
relocation time does not justify collapsing a film onto one floor.

location_notes tells the crew what to find: level space, useful background,
light direction, actor action and room for the route. Venue geometry is assumed
staging, not a survey. State uncertain features. Marks belong to a scene and
use local X/Y floor metres, Z up. facing_rad and actor_heading_rad share these
scene axes; camera bearing is independent of actor facing.

Use supported assets/atmospheres from movement_catalog.scene_catalog. Objects
have unique IDs, labels, centre positions, sizes and yaw. Floor-standing objects
sit at half their height; doorway centres are open. Position signs readably.
Keep the cart, both arms, actor path and sightline clear of props. Supporting
cast uses lead-relative offsets and hold/with_lead motion; all are proxies.

Use transition:cut for edited setup changes. reposition estimates driving only
within one space. Inter-location travel is unknown off-camera time. Resets
between takes are not filmed walking. Reposition is a lower bound: its idealized
turn diagram uses reverse, which this cart lacks; actual forward-only/manual
reset time remains unestimated.

## Targets and follow intent

camera_target names an actor or a scene object. A sign reveal must target the
sign; filming someone looking upward does not reveal it. Tilt-up begins below
its target by angle_rad and ends aimed at it.

Select tracking.cart:follow_actor for lead/follow/side tracking of a walking
actor, and tracking.phone:follow_head when keeping their moving head framed.
Name the same actor and explain why. Locked frames, deliberate moves away and
object inserts use planned on the appropriate channel. Object shots never
activate person following. on_loss:stop_and_hold requests cart stop and arm hold
until identity is reacquired. The preview uses a scripted target; live controllers
remain pending integration. AI never replaces them with motor instructions.

`cinematic_motifs` guide intent only; never copy their trajectories.

## Compile within the rig

Use only live catalog template IDs, parameter names and bounds. Each resolved
shot uses primitive:template, template_id, subject_motion:hold/walk/none and
unique numeric {name,value} parameters. Add only template-listed parameters
plus focal_mm. Choose radius, focal length, heights and actor travel explicitly.

The cart drives with powered front wheels and rear casters; it cannot strafe,
reverse or climb stairs. Both five-joint arms use existing calibrated FK/IK.
Never output servo values, invent another rig, alter calibration or claim
physical readiness. Achieved height/aim can differ from intent; inspect the
solved pose. Large residual error requires revision, not an artistic label.

Stationary shots use duration_s equal to their source filming time. Straight
travel estimates distance/speed; arcs estimate radius*abs(sweep)/speed. Wheel
quantization and slowdown make compiled duration authoritative. A short source
cannot fill a long edit without an explicit hold, retake or edit-speed change.
Use catalog pace limits: a large orbit takes tens of seconds, not a short beat.
Constant-distance following needs actor_distance_m=distance_m at the cart's
slow pace. rise_start/end are filming fractions at least 0.05 apart. Calibrated
setup and aiming are additional time, excluded from the edit.

## Independent cinematic layers

cinematography keys independently control camera height, added pan/tilt/roll,
camera target, light height/target, actor movement and cart pace. Empty lists
keep defaults. Nonempty lists have 0/1 endpoints, strictly increasing at values,
catalog SI values and smooth/linear/hold easing. Position keys are shot-local XYZ
independent of route rotation. Added aim sums with the preset: avoid accidental
double pans. Texture supplies bounded deterministic drift on any route.

Camera/light/actor keys use normalized full-take filming time, including pre/post
holds and excluding setup. Pace keys use normalized route distance so bends stay
aligned when timing changes. Lens uses camera.keyframes with focal_mm. Zoom and
horizon correction are simulated phone-app choices. New channels override only
their own legacy fallback. Light brightness/colour remain manual.

Compound paths include spiral, s_curve, arc_push, pass_by and three_beat. Leave
room for wheel curvature slew and entry/exit settling. Pre/post holds and quintic
pace demand do not eliminate quantization or the finite motor deadband step.
Never promise a smooth crawl below the registered minimum.

Consecutive edit beats sharing a take need the same nonempty capture.take_id,
identical movement/target/mark in one space and adjoining capture.in_s starting
at zero. Setup occurs once. Stationary shared takes explicitly use the full
source duration. The final beat rehearses remaining source even when edited
shorter. Another location, lens program or mark needs another take. Empty
take_id means separate setup. Short edits never accelerate setup or robot travel.

Product-only shots use subject_motion:none, actor_id:"", object camera_target
and no person following. Cast may be empty. Use product/plinth or other scene
assets. Product moves include highlight walk, macro-style pass, orbit, foreground
reveal and negative-space drift. Macro means tight framing, not qualified focus.
Landscape frame-height estimate: optical_depth_m*20.25/focal_mm; cart radius is
only an estimate of optical depth. Use the nine-size catalog and actual solved
camera coverage, including any Dolly Zoom scale change.

## Script-driven actor and robot choreography

Choose movement from the story, not a fixed preset sequence. Both actors and the
robot may move. When simultaneous movement is requested, preserve actor locomotion
while the cart travels and the phone changes height, local position or aim inside
the same filmed interval. Never freeze the actor as a repair for difficult IK.

Use motion_requirements from the catalog: required, preferred or intentionally_static.
Required motion needs numerical goals. simultaneous_s is meaningful overlap of
actor root travel, cart translation and phone motion. Stable screen composition
can be correct tracking. Zoom, gait in place, setup and jitter cannot count as travel.

camera_position_m is optical-centre XYZ in the fixed shot frame, not a look-at
point or cart offset. It owns Z; do not combine it with camera_height_m. Five
joints cannot achieve arbitrary XYZ plus pointing plus roll. Keep failed intent
visible. Start with feasible routes or reviewed optical handles. Alternative
base placements retain the same optical path and actor, and need explicit selection.

Preserve fixed lenses unless zoom is intended. Use actual compiled duration for
hold/move/settle beats. Keep independent light targets and existing drive/joint
limits. Scripted following is not qualified live tracking or hardware readiness.

## Performance and the cut

Populate visual_style and shot design with visual rules, purpose, composition,
practical setup, opening/change/ending and timed observable actions. Preserve
eyelines, screen direction and user facts. Silent shots have lines:[] and
selected_line:0; footfalls, breath, music and silence belong in audio_intent.
Never put "No spoken line" in dialogue. Speech alternatives need verified fact
IDs; an emotional feeling does not require an invented spoken slogan.

Keep edits ordered, non-overlapping and inside the requested duration. Allocate
pacing for the specific story. Unknown facts remain placeholders or material
questions. Unsupported moves stay unresolved with reasons. Do not silently swap
requested moves, invent venue measurements or promise collision safety.
