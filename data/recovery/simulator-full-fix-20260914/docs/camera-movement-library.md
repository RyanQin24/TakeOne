# TAKE ONE movement library

## Implemented feature 06

The studio now contains **28 implemented movement presets**, plus the original
orbit study and the drawn-ground-path editor. The movement selector groups the
presets into six families. Selecting one calculates its cart, camera arm, light
arm, subject and simulated lens movement on the same timeline.

| Family | Working presets |
| --- | --- |
| Hold & reveal (6) | Static; pan left/right; tilt up/down; whip pan |
| Dolly & lens (6) | Push in; pull out; zoom in/out; Dolly Zoom in/out |
| Follow & travel (5) | Follow a walking actor; lead a walking actor; truck left/right; walk alongside |
| Arc & orbit (4) | Counterclockwise arc; clockwise arc; full 360-degree orbit; Hero reveal |
| Height & perspective (4) | Pedestal/boom up; pedestal/boom down; travelling jib-style rise; high-angle reveal |
| Roll & handheld (3) | Roll left/right; subtle handheld-style drift |

The supplied [StudioBinder movement article](https://www.studiobinder.com/blog/different-types-of-camera-movements-in-film/)
informs the vocabulary and distinctions between translation, pointing, roll and
lens changes. Preset descriptions suggest a purpose without asserting that a move
always produces one emotion. Boom and jib presets describe motions scaled to
this cart-mounted arm; the high-angle preset displays the achieved camera pose,
not an invented aerial or overhead drone position.

## Using the studio

Select a movement under **Camera movement**, then edit the parameters displayed
for that preset. **Reset preset** restores its defaults. Edits are retained while
switching among presets during the session. Save/Open preserve the full named
settings; exporting preserves the solved frames and timestamps.

When a movement changes, both views and the old shot readings clear while the
selected shot loads. The cart, actor and camera are revealed only after their
first solved poses have been applied. Failed loads show **Retry preview** rather
than an unpositioned robot or another preset's view. Rapid changes keep the last
selection, and requests from separate tabs wait for the planner in turn.

The planner's loaded-code check covers motion code and captured drive settings.
Editing independent Director, editor, recording or voice services no longer
blocks previews. Their file hashes still remain in the plan's provenance.
Changes to actual motion code or captured drive settings still require a server
restart before new motion is prepared.

Cart moves expose distance or sweep and pace. Stationary cart moves expose
duration. All presets can vary camera height, the change interval, and the light
arm's height. Begin/Finish are percentages of shot movement time, excluding the
initial calibrated-to-filming setup. The focal-length control sets the starting
lens; a zoom preset also exposes its ending focal length. Dolly Zoom computes
its lens curve from optical depth.

Every shot's filming pose starts with the physical phone in landscape. Stationary
setup moves from the saved calibration counts into that pose before the shot
clock starts. Roll presets then apply their intentional tilt from landscape.

**Actor & light** contains actor height, stationary/walking choice, walking
distance/direction and independent light heights. Tracking presets start with a
walking actor. A green line marks the actor's route; red marks the requested cart
route and amber marks the integrated motor prediction. Each grid square is
exactly **0.3048 metres (one foot)**.

The camera's position and aiming direction use FK of the displayed integer arm
goals. The phone monitor now offers upright output or the physical phone roll;
Auto retains intentional roll/handheld effects. Height, pitch and focal-length
readouts update with playback and scrubbing. A locked shot keeps its camera
still when the actor walks across the frame; its light may follow. See the
[iPhone camera and reusable zoom controls](iphone-camera-feature-08.md).

## Shared program and robot execution

Each preset expands into:

- A forward powered-axle route, or an all-zero wheel schedule for stationary moves.
- Independent camera height, camera aiming offsets and optical roll.
- An independent light-height curve and actor-directed light aim.
- The actor's ground position and gait/body-bob state.
- A simulated focal-length curve.
- A calibrated initial pose, stationary arm setup, then the shot timeline.

The existing wheel-response model chooses exact wire-precision commands.
Integrating those commands produces the cart poses used for arm IK and the
preview. Both arms start at their calibrated integer goals. Camera and light
positions/orientations come from FK of the same integer samples consumed by the
robot player. Phone wrist-roll ID 6 and light wrist-roll ID 5 remain unchanged.
No aiming-error stop threshold has been introduced.

The cart faces its route before travel, so clockwise arcs, pull-outs and lateral
trucking can use forward powered wheels. Trucking is performed with the cart
oriented along its ground path and the arms looking toward the actor; the cart
does not slide sideways.

Preparation and **Run on robot** use these cart/arm schedules. Phone zoom and
recording are still manual: the plan includes timestamped simulated lens cues,
but does not claim to transmit iPhone zoom commands. A scripted walking actor is
a rehearsal target, not live computer-vision tracking or physical actor feedback.
No hardware was activated during this feature's verification.

## Math and timing

Camera/light height and authored aim changes use quintic easing:
h = h0 + (h1-h0)(6u^5-15u^4+10u^3). The change begins and ends at rest. Pan, tilt
and roll supply distinct orientation objectives to the shared aiming solver.
The light retains an independent face target when the camera pans or tilts away.

The existing nominal arm pace remains in use. The default large vertical lifts
take 24 seconds; the travelling rise uses a longer cart route. Extreme user
settings can produce a requested-versus-achieved difference, which is displayed
rather than converted into a new execution gate.

For Dolly Zoom, pinhole projection gives image scale proportional to f/z.
Consequently f(t) = f0*z(t)/z0 preserves that scale. Here z is the achieved
optical-axis depth to the actor, not cart radius or Euclidean lens distance.
Both directions use this calculation; focal length holds at f0 during initial
arm setup. The iPhone camera layer supports 13–360 mm equivalent framing,
including the approximate 15x digital-video endpoint, and reports image-scale
drift if a lens endpoint is reached. Lens curves and Dolly Zoom can now be
applied to any movement through its camera controls.

The actor's translation, head target and body bob share the same samples. Its
repeatable walking cycle is driven by distance (one 0.9 m left/right stride).
The renderer articulates hip, knee and shoulder groups and reuses geometry and
materials. This is a lightweight procedural rehearsal figure, not a dynamics or
motion-capture model.

## API and future AI Director

GET /api/previs/templates returns the implemented catalog, defaults, parameter
labels, display conversions and ranges. The UI builds its controls from this
catalog. Unknown template IDs are rejected rather than replaced with an orbit.

A minimal example for POST /api/previs/templates:

    {"mode":"template","template_id":"dolly_zoom_in","distance_m":1.5,"focal_mm":50}

A walking follow example:

    {"mode":"template","template_id":"track_follow","distance_m":2,
     "actor_distance_m":2,"speed_m_s":0.17}

The response supplies canonical settings, solved frames, actual duration and a
matching robot-plan identity. Those settings can also be submitted to the
existing robot preparation endpoint. The future Director can choose a template
ID and adjust these parameters. Automatic Director-to-studio dispatch remains
a separate integration; this feature supplies the complete movement vocabulary
and execution path.

## Efficiency and recovery

Cart predictions are cached independently of arm/lens settings, with at most
eight routes retained. Complete compiled results have a six-entry cache and are
returned as independent copies. Source/configuration provenance changes the
cache key. Identical stationary aiming objectives are solved once; moving
subjects or aim changes use finer key samples. Playback performs interpolation,
not IK. Smooth/on-demand/offscreen rendering remains active.

| Before | After |
| --- | --- |
| Hero-only preset definition | Data-driven 28-preset catalog in previs/templates.py |
| Height-only choreography | Shared subject, pointing, roll and focal evaluation in previs/program.py |
| Drawn-route compilation | Shared stationary/moving motor-scene compiler in previs/path.py |
| Pointing-only IK | Optional yaw, pitch and roll objectives in previs/compiler.py |
| Hardcoded Hero controls | Catalog-generated controls in dist/shot-library.js |
| Rebuilt static actor | Reusable articulated figure in dist/walking-actor.js |
| Fixed preview focal length | Per-frame focal length and FK camera projection |
| Hero-only save names | Named preset settings and preview files |

Exact pre-feature source copies are under
data/recovery/movement-library-20260913/. The previous orbit, custom path,
calibration originals and unrelated editor work are retained. Tests and
reproducible measurements are under data/verification/movement-library/.

The subsequent loading fix preserves its five original files under
data/recovery/preview-loading-20260913/. Its changes are the process-input filter
in config.py, queued preview requests in server.py, and loading/failure handling
in orbit.js, index.html and orbit.css. Verification is recorded under
data/verification/preview-loading-20260913/.
