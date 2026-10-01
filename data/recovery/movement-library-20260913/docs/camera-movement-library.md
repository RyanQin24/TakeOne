# TAKE ONE camera movement library

## Current review step

**Implemented: Hero reveal / rising orbit.** The cart arcs around a stationary
actor while the phone moves from chest height toward eye level. The lens keeps
aiming at the face, so its upward pitch gradually reduces. The light arm moves
independently through the reveal while retaining its face aim. This is a compound
arc, vertical lift and tilt correction, not a constant arm pose on a moving cart.
The stationary actor faces the opening lens position and keeps that heading
throughout the take, so the default reveal begins on the face.

The user requested one reviewable feature at a time. Dolly Zoom, the remaining
movement presets and an actor walking on a ground path are the next review
steps; they are not presented as working features in this release. No live face
tracker or automatic phone zoom control is implied by a simulated target.

## Research translated into template design

These are suggested visual intentions, not rules that a movement always produces
one emotion. Acting, lighting, duration, framing and context also matter.

| Family | Possible intention | Coordinated controls |
| --- | --- | --- |
| Static / locked frame | Attention, restraint | Hold cart and optical frame; optionally track an actor |
| Pan / whip pan | Reveal, follow, abrupt transition | Horizontal optical aim, sweep, duration, easing |
| Tilt | Vertical reveal | Vertical optical aim, start/end target |
| Push in | Emphasize a realization | Cart approaches; arms maintain the chosen composition |
| Pull out | Reveal context or isolation | Cart retreats; arms maintain the subject framing |
| Tracking / trucking | Stay with a subject | Subject path, cart offset, face aim and matching pace |
| Arc / orbit | Change relationships and perspective | Radius, sweep, travel direction and independent arm motion |
| Roll / Dutch transition | Instability or disorientation | Optical roll and horizon through time |
| Handheld style | Intimacy or urgency | Small authored motion around an underlying path |

The supplied [StudioBinder movement guide](https://www.studiobinder.com/blog/different-types-of-camera-movements-in-film/)
provides the vocabulary. Cart translation and arm aiming are separate channels;
turning a differential-drive cart is not lateral sliding.

| Additional family | Possible intention | Coordinated controls |
| --- | --- | --- |
| Zoom in / out | Direct attention or reveal context | Focal length over time, independently of camera translation |
| Dolly Zoom | Disorientation, realization, relationship change | Dolly distance and inverse framing change together |
| Pedestal / boom | Reveal height and spatial relationships | Optical-origin height; specify whether tilt is held or corrected |
| Low-angle rising orbit | Presence, then a closer eye-level relationship | Arc plus rising optical origin and face tracking |
| Overhead / bird's-eye | Spatial overview | Elevated origin and downward aim; this describes a viewpoint, not one movement |

Research sources for these distinctions:

- [StudioBinder: zoom versus dolly](https://www.studiobinder.com/blog/what-is-a-zoom-shot-definition/).
- [StudioBinder: Dolly Zoom](https://www.studiobinder.com/blog/best-dolly-zoom-vertigo-effect/).
- [StudioBinder: pedestal movement](https://www.studiobinder.com/camera-shots/camera-movements/pedestal-shot/):
  moving the camera vertically is distinct from tilting its optical axis.
- [StudioBinder: low-angle framing](https://www.studiobinder.com/camera-shots/camera-angles/low-angle-shot/):
  a low viewpoint can communicate authority, admiration or tension.

The cart rig can compose translation, yaw, arm position, optical aim and simulated
zoom. Aerial crane/drone travel is not the same motion as an arm lift. An adapted
overhead request must describe the achieved camera position explicitly.

## Shared language for the future AI Director

Describe a shot using independent channels rather than just a camera-move name:

1. **Intent**: what should the audience notice or feel?
2. **Subject**: actor position, path, height and timing.
3. **Cart path**: start, end, radius/curve and pace in SI units.
4. **Camera origin**: height or position keyframes.
5. **Camera aim**: face, object, explicit direction, roll and framing offset.
6. **Lens**: focal length or subject-scale objective over time.
7. **Light**: its own position and aiming objective.
8. **Timing**: setup, movement, holds, easing and actual command duration.

The current working template can already be submitted to
`POST /api/previs/templates`, saved, reopened, exported, or passed as `settings`
to the existing robot preparation endpoint:

```json
{
  "mode": "template",
  "template_id": "hero_orbit",
  "radius_m": 2.5,
  "sweep_rad": 1.5707963267948966,
  "bearing_rad": 3.141592653589793,
  "speed_m_s": 0.17,
  "height_start_m": 1.25,
  "height_end_m": 1.59,
  "rise_start": 0.1,
  "rise_end": 0.85,
  "focal_mm": 35,
  "subject_height_m": 1.72
}
```

`GET /api/previs/templates` lists only implemented templates and their defaults.
Director-to-studio dispatch remains a separate integration step. Unknown template
IDs are rejected instead of silently substituted with an orbit.

## Mathematics and execution

The template generates a powered-axle arc and uses the existing forward wheel
planner. Its exact rounded wheel packets are integrated to make the cart preview.
The arm trajectory is solved along that predicted path. Every take still begins
at the existing calibrated integer goals, with stationary cart aiming first.

Lift timing is normalized to travel time, excluding setup. Between the chosen
start/end fractions, camera height follows `h = h0 + (h1-h0)(6u^5-15u^4+10u^3)`.
The lift starts and ends with zero velocity and acceleration. IK samples are
warm-started, interpolated into encoder goals, and retain the existing nominal
joint pace. Both views use FK of those same goals. Camera height and pitch shown
in the interface are achieved values; height mismatch is a note, not a new stop
threshold. Existing phone wrist-roll ID 6 and light wrist-roll ID 5 are preserved.

For the next Dolly Zoom step, the pinhole projection gives image size proportional
to `f/z`. A constant-size subject therefore needs `f(t) = f0 * z(t)/z0`: dolly
toward the subject while widening the lens, or dolly away while tightening it.
Use optical depth from the achieved lens pose, not the cart's radius. A pitched
or moving subject needs a projected framing check as well. Simulated focal
length must be shown separately from any actual phone zoom command; the current
robot player does not control the iPhone lens or recording.

## Walking actor and performance direction

The planned walking actor uses a small articulated figure with reusable geometry,
a ground path, and one playback clock. Body position and face target must be the
same data used by arm planning. It should not slide a static figure or run a new
IK solve during every rendered frame. The first hero shot keeps its actor still;
the walking behavior is a subsequent review step.

Current efficiency changes: a bounded four-entry cart-prediction cache is keyed
by route, speed and source/configuration provenance. Height changes reuse that
prediction while recomputing arm choreography. The existing two-entry complete
plan/preview cache returns independent copies. Source or calibration changes
invalidate cache keys. Playback only interpolates precomputed frames and keeps
the previous Smooth/on-demand/offscreen rendering improvements.

## Source mapping and recovery

| Previous behavior | New location / behavior |
| --- | --- |
| One fixed camera-height preference per drawn path | `previs/choreography.py` validates and evaluates a time-varying lift |
| Hand-drawn route only | `previs/templates.py` expands a named reveal into a route and choreography |
| Arm solves along the route at one height | `previs/path.py` solves both arms at changing heights; FK reports optical pitch |
| One whole-result cache | Small separate wheel-route cache reuses prediction across height edits |
| Path/orbit robot preparation | `motion/studio_plan.py` dispatches the template into the same validated player |
| Path/orbit controls | Studio adds reveal parameters, achieved height/tilt and save/open support |

Exact pre-change source copies are in `data/recovery/shot-choreography-20260913/`
with their workspace-relative paths. The previous orbit template, custom path
editor, full model, calibration originals and separate editor work are preserved.
Verification results are in `data/verification/shot-choreography/`.
