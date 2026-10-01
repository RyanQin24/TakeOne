---
name: takeone-shot-design
description: Develop a brief into detailed, physically staged film direction, actor beats and camera choices for TAKE ONE's Director and rehearsal compiler.
---

# Shot design for a real set

Choose a structure for the user's story, preserving specified places, people,
objects, timing and constraints. The catalog is a toolbox; films need not show
every move. Establishing a place is a purpose independent of shot size. An
insert may have no actor. A scene may contain one take or several cuts.

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

Use explicit channels when performance affects framing:

- actor_position_m: shot-local floor XYZ, Z=0, relative to the placed origin;
  replaces the preset path. Smooth/linear keys move; repeated positions hold.
- actor_heading_rad: body facing about scene Z, in radians.
- gaze_yaw_rad/gaze_pitch_rad: head turn relative to the body; positive pitch
  looks up. These animate staging figures, not facial acting.

Channels use normalized full-take filming time. Shared-take edit clips keep
identical full-take channels; performance beats stay local to each edit shot.
Follow intent selects existing hooks, whose live implementation is pending;
scripted-target preview is not live tracking.

Design repeatable filming with real people and objects. Preserve planned versus
measured setup. Flight, underwater work, high-speed action, weather, unsupported
poses or camera placement need other equipment, practical effects or explicit
redesign. Review purpose → beat → camera → space → cut before proposing. Never
return one saved story for unrelated briefs.
