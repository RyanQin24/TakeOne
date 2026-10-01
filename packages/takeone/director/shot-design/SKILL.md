---
name: takeone-shot-design
description: Develop a brief into detailed, physically staged film direction, actor beats and camera choices for TAKE ONE's Director and rehearsal compiler.
---

# Shot design for a real set

Choose a structure for the user's story, preserving specified places, people,
objects, timing and constraints. The catalog is a toolbox; films need not show
every move. Establishing a place is a purpose independent of shot size. An
insert may have no actor. A scene may contain one take or several cuts.

## Deliver a filmable first draft

An open-ended demo request is a request for a proposal, not a blank template.
Choose a small story the available rig can show: a visible opening action,
a change or reveal, and a payoff. Write actual dialogue (or intentional silence)
and specific acting beats. Never return editor scaffolding such as "Write your
opening line" or "Describe what the actor does". Unknown venue measurements or
product facts stay explicit questions; they need not prevent a concrete story.

Honor explicit shot counts, cast size, day/night setting, walking direction and
requested pace. Ten distinct shots in a minute need roughly six-second edit
beats, not ten long takes squeezed into a minute by speeding up playback.
When unspecified, usually propose 4-6 shots for a minute-long demonstration.
Respect an explicitly requested single take. If the
brief calls for robot/camera movement, encode it with catalog movements and
parameters so the rehearsal actually moves. Prose alone cannot animate the rig.
Keep directions concise, use one line choice per beat, and leave unused channels
empty. Each move needs a story purpose, not a compulsory tour of every template.

When the brief asks for a conversation, give the participants distinct replies
and speaker identities across the edit; do not assign every line to one actor.
Line alternatives are alternatives, not successive speakers. Use successive shots
or explicitly labelled spoken turns and matching timed performance beats.
When actor-free scenery is requested, author real object-target shots with
subject_motion:none, actor_id:"", no cast in that scene, and intentional silence.
For a brief requesting independent rig movement, contrast cart-held pan/tilt/roll
with travelling shots and separately timed phone/light changes. Review rotation
relative to the cart: moving a rigid rig across the floor is not arm choreography.
Vary viewpoint, scale and beat length to serve the exchange. A named Dutch shot
needs visible phone roll; a level horizon correction must not cancel its purpose.

## Three levels of direction

1. visual_style states visible rules: how composition evolves, colour palette,
   light direction/quality, wardrobe/props, sound and continuity locks. Describe
   choices, not a director's name or mood adjectives. Respect the brief.
2. Each location is a staged scene. location_notes gives scouting directions:
   what to find, action/background placement and level route clearance. Objects,
   dimensions and cast express assumed layout. Atmosphere is a lighting preview,
   not weather or a measured venue.
3. Each shot's design states purpose, attention, opening/ending, composition,
   angle, focus and practical setup. Choose framing and a motivated movement
   independently. Timed beats contain action, motivation, emotional progression,
   eyeline and delivery that a performer can understand and enact.

Beats use seconds from that edit shot's first filmed frame, excluding setup,
and fit its edit duration. Let a glance precede a turn or hold a reaction before
speech. Allocate time for action. Prose guides people; animation/motor commands
require explicit channels. Silent scenes keep dialogue empty and use audio_intent.

## Size, viewpoint and optics

Use nine sizes: extreme wide, wide, full body, knees-up, mid-thigh, waist-up,
chest-up, face and detail. Full body includes head and feet; avoid accidental
cuts through hands/joints. Two-person, group and over-shoulder shots require
featured_actor_ids with supporting people staged in scene.cast. POV needs the
camera at the intended viewpoint and a motivated eyeline. A composition label
does not place the camera.

visibility:throughout requires continuous coverage; by_end checks the final
reveal frame; intentional_partial permits a deliberate fragment. Coverage does
not prove visibility behind obstacles or readable text. Inspect the phone view.

lens_policy:fit_subject fits a fixed lens from the actual solved opening pose
(or ending for by_end), keeps the route and checks the take again. Use authored
for chosen lenses or any zoom/Dolly Zoom. The solver bounds equivalent focal
length. Set reachable movement height/aim/roll to match angle intent; a label
never creates mechanical capability.

This phone's physical-camera equivalents are 13/24/100 mm; 48/200 mm are sensor
crops. Intermediate values, horizon correction and lens changes are simulated
framing. Verify settings in the recording app. Do not claim cine lenses, variable
aperture, verified macro focus or simulated shallow depth of field. Rack focus
is manual; name its start/end targets and change cue.

## Choreography and practical value

Natural-language speaker direction must become timed camera behavior, not just
new prose or a renamed preset. For "frame A, then turn to B as B replies", use
camera_target_m keys at the staged head positions, holding each speaking beat
and moving smoothly between them. Use supplied staged_head_targets when present;
they are shot-local staging samples, not live detected heads. Align transition
times with design.beats. Light target/height tracks may follow independently with
a motivated delay. For tighter singles versus shared context, author lens
keyframes and hold the intended focal length through each line; widen during a
large pan if necessary, then tighten on the reply. Zoom does not move an arm.
The LEFT key's ease controls the following interval: use hold only before an
identical value, and smooth/linear on the key where a change begins. This also
applies to lens keys. A speaking hold then pan is [A@0 hold, A@0.35 smooth,
B@0.65 hold, B@1 hold], not a hold at 0.35 that jumps to B at 0.65.
For a within-shot conversation, keep both labelled turns in ONE selected line
choice and time them in beats. Screen targets apply to each speaker's own time
window; do not require both faces throughout a shot that intentionally singles
out each person. Never promise a 47 cm lift just because authoring bounds allow
it: height plus aim may be unreachable together. Use the solved review to revise
the movement or staging explicitly, preserving the reason for the shot.
Use actual camera height/position and aim changes for mechanical motion.
Never require arbitrary joint wiggles or claim every motor must move in each
shot: inverse kinematics determines the joints needed. Review actual per-joint
excursion, aim error and composition before describing the result as achieved.

Use explicit channels when performance affects framing:

- actor_position_m: shot-local XYZ relative to the placed origin; replaces the
  preset path. Z is one constant standing-surface elevation from 0 to 1.5 m
  (normally 0). A platform needs explicit height, a matching staged object,
  safe access and edge-clearance directions. Varying Z/climbing is unsupported;
  the cart stays on its own level floor. Smooth/linear keys move; repeated
  positions hold. Supporting cast with_lead inherit elevation; do not add it twice.
- actor_heading_rad: body facing about scene Z, in radians.
- gaze_yaw_rad/gaze_pitch_rad: head turn relative to the body; positive pitch
  looks up. These animate staging figures, not facial acting.

Channels use normalized full-take filming time. Shared-take edit clips keep
identical full-take channels; performance beats stay local to each edit shot.
Capture in_s plus the edit duration must fit the actual compiled source footage,
not merely distance/speed arithmetic: motor timing can differ from the estimate.
Leave modest source handles, then review the retained edit's achieved movement.
Do not fill missing footage with an end-frame hold or silently stretch playback.
Use linear or smooth actor-position keys between different positions; hold is
only valid between identical positions. Dialogue selected_line is zero-based.
Actor appearance values are six-digit #RRGGBB colors, not wardrobe prose. Keep
wardrobe descriptions in visual_style. Nonempty body-heading, look-at and gesture
tracks require strictly ordered keys beginning at 0 and ending at 1; repeat an
endpoint value to hold it. Empty tracks are valid when no animation is needed.
Orbit motion requirements use orbit_rad with signed_progress_m=0. Signed linear
progress is only for approach, retreat, left or right. Simultaneous motion needs
actual actor travel as well as cart and relative camera motion; do not request
it for an intentionally stationary actor.
Follow intent selects existing hooks, whose live implementation is pending;
scripted-target preview is not live tracking.

Design repeatable filming with real people and objects. Preserve planned versus
measured setup. Flight, underwater work, high-speed action, weather, unsupported
poses or camera placement need other equipment, practical effects or explicit
redesign. Review purpose → beat → camera → space → cut before proposing. Never
return one saved story for unrelated briefs.
