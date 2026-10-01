# Feature 03: drawn ground routes

Open the local simulator at `http://127.0.0.1:8766/`. This feature is one editable
shot; the Director, multi-shot editing and live subject tracking remain separate.

1. Choose **Draw a ground path**. The example is a half circle around the actor.
2. Click **Draw / redraw**. The camera switches to Top view. Click consecutive
   points or hold the pointer down and draw. Lift and continue to add another
   segment. **Undo** restores the previous stroke, including the previous route.
3. **Close loop** joins the end to the start. **Finish path** calculates the move.
4. Adjust Start/End X/Y in feet for precise placement. Adjust the cruise pace;
   default is 0.17 m/s (about 0.56 ft/s). The timeline shows setup plus calculated
   travel time. **Play preview** or scrub to inspect both arms and the phone view.
5. Red is the authored route. Amber is the powered-axle path predicted from the
   actual rounded wheel commands. Curves may cut inside the red line. The shot
   maths also reports predicted endpoint offset. Editing invalidates the earlier
   prepared robot run. Save/Open preserves route points and settings.
6. On the robot computer, place the powered-axle midpoint at START and align the
   powered front with the initial gold arrow. The actor is the map origin (0,0).
   **Prepare robot run** creates commands without opening devices. **Run on robot**
   uses the existing physical player for the same samples and wheel schedule.
   Stop/Esc retains the existing stop behavior. Each take first returns both arms
   to their calibrated starting counts, aims with the cart stopped, then travels.

## Calculation and hardware assumptions

Ground coordinates are world X/Y; Z is up. The powered axle follows the route,
not the cart's body origin. Its offset remains the configured +0.27 m. The large
powered wheels remain at +X and both complete arm mounts remain at +90 degrees.
No calibration files, hardware settings, firmware or torque behavior changed.

One grid cell is **0.3048 m**, the exact international foot, not the former half
metre cell. See [NIST's unit definition](https://www.nist.gov/pml/us-surveyfoot).
Internally all distances are SI. A ten-foot line is 3.048 m before quantization.

Hand-drawn corners are locally rounded with two endpoint-preserving Chaikin
passes. An offline pure-pursuit follower selects targets ahead along that route.
Projection is limited to the next stretch to preserve ordering at crossings.
At an axle-frame target (x,y), curvature is `2*y/(x*x+y*y)`. With track width B,
the wheel relationship is `vL = v - omega*B/2`, `vR = v + omega*B/2`.
This is standard [differential-drive kinematics](https://github.wpilib.org/allwpilib/docs/release/java/edu/wpi/first/math/kinematics/DifferentialDriveKinematics.html).
There is no sideways translation. This path mode uses nonnegative wheel commands
for both clockwise and counterclockwise routes; one wheel can stop for a tight
turn. The existing orbit template retains its own direction controls.

The planner chooses only wire-representable commands: zero or the existing
0.04–0.15 range in increments of 0.01. It holds a steering decision for 200 ms,
reduces demanded pace into bends, and normally changes a moving command by at
most 0.01 per decision. The deadband requires a direct transition from zero to
the minimum moving command. Sparse measured response tables can require a larger
step; their actual supported values are used. There is no invented velocity for
an unmeasured table point, nor rapid 20 ms on/off dithering in this path mode.

Every 20 ms transmitted segment is integrated with the exact constant-twist
solution: mean wheel distance sets forward travel, wheel-distance difference
divided by track width sets heading change. The result drives the amber path and
cart geometry. End detection stops at a close forward approach or when passing
the closest approach to the endpoint; reported offset remains visible. A route
that cannot finish in the bounded planning horizon needs wider turns or shorter
travel. These are finite-plan checks, not measured arm-error thresholds.

The existing wheel response is **provisional_symmetric**: the same approximate
speed model for both motors. The calculation assumes no slip and immediate
response; it does not model measured inertia, friction or stopping lag. There
are no encoders or localization feedback in this playback path. Therefore the
real robot receives the same commands and timing, but real-world drift can make
its physical line differ. Independent wheel-response tables are supported by
the existing response module when available. We do not claim a physical accuracy
bound from the mathematical preview.

For the arms, bounded IK is warm-started along the predicted cart poses every
0.8 s. Raw encoder goals are interpolated at 40 ms and their change is limited to
the nominal 25 degrees/s planning pace. The rendered frames use FK of those exact
integer goals. Residual aiming error is displayed as a framing note and does not
block a run. The phone wrist-roll remains ID 6; light wrist-roll remains ID 5.
All original calibration bytes are preserved.

## Source mapping and recovery

- `packages/takeone/previs/path.py`: new route geometry, wire-command prediction,
  moving-arm goals, shared preview and physical plan. No serial dependencies.
- `packages/takeone/previs/compiler.py`: existing orbit solver preserved; adds a
  warm-start option for neighboring path poses.
- `packages/takeone/motion/studio_plan.py`: drawn path dispatch added; existing
  artifact validator and physical player reused unchanged.
- `apps/rehearsal/server.py`: local `/api/previs/path`; path and robot preparation
  allow up to 128 KiB, with route input capped at 512 points and 65 m per take.
- `apps/rehearsal/dist/path-editor.js`: new draft/undo and feet conversion helpers.
- `apps/rehearsal/dist/{index.html,orbit.js,orbit.css,orbit-robot.js}`: default
  path editor alongside the existing orbit template and robot controls.
- Original edited sources are copied under `data/recovery/drawn-path-20260913/`
  with the same relative paths. Nothing unique was removed or moved. The `dist`
  directory remains authored product source.

Verification results are recorded separately in `data/verification/drawn-path/`.
Tests use fake devices or pure calculation. Hardware motion is not an automatic
verification step and has not been tested on this disconnected computer.
