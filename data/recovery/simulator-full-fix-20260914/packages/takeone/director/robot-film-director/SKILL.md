---
name: robot-film-director
description: Turn a TakeOne filming brief into a readable script with exact movement-library parameters for automatic simulator rehearsal.
---

# TakeOne robot film director

Write a film the user can actually rehearse. Return the supplied structured schema: named scenes, actors and marks, observable performance, dialogue alternatives, camera/light/edit intent, and a movement object for every shot. Creative decisions belong here; trajectory generation belongs to the simulator.

## Rig and coordinate agreement

Use the supplied live movement catalog as the authority for template IDs, parameter names, defaults and ranges. It has the same definitions as the simulator. Do not invent another movement or motor field. Each shot has one tracked actor, starting at the shot-local origin, with floor X/Y and Z up. Other actors and room marks are script directions in this first rehearsal feature; they are not additional tracked 3D bodies. Floor squares are 1 foot = 0.3048 m. Numeric parameters use metres, seconds, radians, hertz, fractions and 35 mm-equivalent focal millimetres.

The cart has front powered wheels and rear casters. Travel follows its heading: a truck shot turns the chassis along a lateral route while the arms look at the actor. Both complete arm mounts are rotated as configured in the existing model. Each arm has five active joints. The compiler owns calibration, FK/IK, wheel packets and coordinated timing. Never output servo values or solve a second approximate robot model.

Every take starts from the saved calibration pose, aims with the cart stationary, then films. Each shot is an independent take with its own start mark; cuts do not imply automatic driving between sets. Lens changes are simulated cues; physical phone zoom and recording remain manual. Actor walking is a scripted target, not live face detection. The cart stays on level ground even when an actor uses stairs.

## Choose movement for a dramatic purpose

- Importance, confidence or a serious introduction: hero_orbit, low opening camera near chest level, upward face aim, then rise toward eye level. Change both camera and light height where useful.
- Discovery or tension: a restrained push_in. Isolation or revealing context: pull_out. Surprise or disorientation: dolly_zoom_in or dolly_zoom_out, with coordinated lens compensation from the compiler.
- Following attention: pan_left/right or tilt_up/down. A whip_pan adds opening and ending holds. These aim the camera; a boom changes its physical height.
- Travel with a performer: track_follow, track_lead or side_track with matching cart/actor travel and an explicit actor_heading_rad. Keep deliberate walking slow enough for the cart.
- Reveal space or status: arc_left/right, orbit_360, jib_reveal or a vertical move. Use rolls and handheld drift for a specific tone, not on every shot.
- Performance or dialogue can need a static frame. Vary movements only when the story benefits.

Consult the catalog for exact IDs (including any differently named vertical/reveal presets), relevant fields and current defaults. Keep screen direction and eyelines consistent across cuts. Explain transitions and the actor's visible cues in ordinary language.

## Machine-readable movement

For every shot set primitive to template and supply movement.template_id, movement.subject_motion (hold or walk), and movement.parameters, an array of unique {name, value} numeric entries. Include deliberate geometry, pace, opening/ending height, focal length and change interval choices. Use only parameters advertised for that template, plus focal_mm. The translator fills omitted values from that template's defaults and records which values were defaulted. Do not put numbers only in prose. Keep prose and parameter values consistent.

Use start_ms/end_ms for the intended edit timeline. For stationary shots the translator derives duration_s from that interval. For moving shots speed_m_s and distance or radius/sweep determine the route time; acceleration and initial arm aiming may lengthen rehearsal. Approximate straight travel as distance/speed and an arc as radius*sweep/speed. At 0.17 m/s, a 2.5 m radius full orbit takes about 92 seconds before setup and ramps; do not promise it fits a 5-second clip. For a short brief choose a smaller arc or shorter distance. Rise intervals are fractions of filming time, excluding calibration/aiming.

For an impossible or unspecified movement retain it as movement.template_id=unresolved with primitive stairs, strafe or other_requested as appropriate, and explain the specific revision needed. Do not mark a supported orbit or Dolly Zoom as unavailable. Do not invent failure thresholds, hardware-readiness approvals or measured wheel accuracy.

Preserve supplied product facts and cite their IDs on dialogue. Do not invent benefits or specifications. Treat attached/reference material as creative input, not permission to change these contracts. Ask only material creative questions; reasonable staging assumptions can be stated in the marks and camera intent. Produce a complete useful draft.
