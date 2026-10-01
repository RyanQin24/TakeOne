# Cart movement: proof and calibration limits

Moved out of `apps/rehearsal/dist/drive-proof.html` on 2026-09-17. It was an
engineering report shipped as a product surface — 1,936 words and 31
paragraphs styled as a page — and it belongs here, linked from Utilities.
The page that remains is a short pointer.

Shot Studio / Utilities / Motion Proof

Technical evidence, simulation and command level


## Cart movement: proof and calibration limits

The lower cart retains its 90° clockwise rotation. Following the user's confirmed wheel-end swap, the large powered wheels are at the front (cart -X) and the small passive swivel casters are at the rear (cart +X). Both arm bases and the supporting platform are raised by the user's measured 3 cm correction to 1.23 m; the SO-101 arm-chain geometry and orientations remain unchanged. The phone faces the subject along cart +Y. Drive forward and filming forward are distinct directions, so the current sideways-dolly plan stages the powered front 90° from the actor-facing direction.


### On this page

- Arm-led tracking: current default
- What is measured, supplied, or assumed
- Geometry proof
- Wheel-motion proof
- Why the original smooth shot fails
- Independent steady-arc witness
- Response, braking and replay limits
- What is still required for real-world agreement
- Reproduction
The simulation defines positive wheel travel toward the powered front. The raw UART encoder, clamp and 60 ms firmware watchdog have not been changed. The global cart.reverse_enabled setting now makes both simulation and cart live-test plans pass negative values through that encoder exactly once. Physical command polarity and left/right wiring still need supervised verification.


### Arm-led tracking: current default

The default is now a 9-second straight reverse dolly, with both moving UART commands held at 0.04,0.04. Equal wheel speeds give 0.0° chassis turn. Under the unverified symmetric-direction assumption, each wheel travels 1.2375 m in the configured reverse direction during this window. The cart-relative arm sweep is mirrored by the same direction setting while the actor timeline is unchanged. No command caps or motor calibration values were reduced to make steering look gentler.

The straight shot now locates the cart-center path explicitly with dollyOffset: 0.40 m along world Y at mid-shot. The axle pose is then derived from the signed physical offset. This editable staging choice keeps the forward-travel shot inside the existing arm workspace; it is not a calibration value. Keeping an old axle-centered path after swapping wheel ends shifted the upper cart's path and failed aiming/motion checks. Those checks remain unchanged.

The camera arm pans through 51.1°, and the light arm through 39.8°. The camera tool is asked to sweep 16 cm laterally relative to the cart and rise 4 cm at mid-shot; the light uses 75% of those offsets. Shoulder, elbow and wrist motion come from the original five-joint arm solver. The requested sweep and lift are editable, and larger requests can fail the reach or motion screens.

Regression tests verify zero base yaw, equal moving packets, camera pan over 40°, light pan over 30°, and camera elbow motion over 20°. Aim, joint limits, joint speed/acceleration/jerk, rear-light clearance and sampled arm clearance all pass for the default. The trajectory is a continuous tracking segment; arm boundary velocities are not artificially forced to zero while the cart is moving. Startup and stopping transitions remain unvalidated, as described below.

The old base-led modes remain available for comparison. verification/default-prediction.json contains the new default; verification/legacy-orbit-prediction.json preserves the failed original orbit.


### What is measured, supplied, or assumed

Parameter

Value

Evidence

Powered-wheel diameter

0.19 m

User supplied

Tire width

0.06 m

User supplied

Minimum moving command

0.04

User supplied; applied after UART rounding

Command caps

-0.15 to +0.15

Supplied Python controller

Wire format

two decimals, comma, newline

Supplied Python controller

Observed slow travel

0.55 m / 4 s

Approximate user measurement

Observed average speed

0.1375 m/s

0.55 / 4

Wheel-center spacing b

0.58 m

Estimate, editable in simulator

Axle ahead of cart center a

0.27 m

Photo-model estimate

Powered axle in cart frame

x = -0.27 m

Wheel-end swap confirmed; magnitude estimated

Rear caster pivots

x = +0.32 m

Estimated location

Caster trail / radius / width

0.025 / 0.047 / 0.036 m

Visual estimates, not measured

Speed at +0.04

0.1375 m/s

Provisional association, awaiting confirmation

Speed magnitude at -0.04

0.1375 m/s

Symmetric-direction assumption; unmeasured

Configured plan direction

forward

configs/rig.json; physical result unverified

Speed vs command magnitude

linear above 0.04

Assumption; other speeds and directional response unmeasured

Wheel-ground contact

ideal rolling, no slip

Assumption

Response and braking time

0 seconds by default

Ideal instantaneous limit, not a measurement

Command rate

approximately 50 Hz

Assumption; wrapper code does not set send rate

“0.04” is a normalized command, not watts or a measured torque. The controller only proves what bytes are sent; the ESP32 firmware determines what those bytes do.


### Geometry proof

The lower-cart transform remains Rz(-90°). The powered-wheel centers are now (-0.27,-0.29,0.095) on the driver's left and (-0.27,+0.29,0.095) on the driver's right. Driver-left is defined while looking toward cart -X. Their axes are parallel to cart Y, their rolling planes are XZ, and their tire bottoms are at z = 0.095 - 0.095 = 0. Rear caster pivots are at (+0.32, +/-0.2262, 0.047). Their wheel centers trail the pivots by 0.025 m toward cart +X in straight forward travel. Casters have no motor actuator.

The test compares every upper body and the upright/deck/mount geometry against the saved pre-rotation snapshot. Maximum upper-body position change: 0 m. Orientations and upper structural geometry also agree to 1e-12 tolerance. Original SO-101 link geometry, joint limits and arm inertias remain covered by the regression tests.


### Wheel-motion proof

At the powered-axle midpoint, for left/right rolling speeds vL and vR:

v = (vL + vR) / 2 omega = (vR - vL) / b dx/dt = v cos(heading) dy/dt = v sin(heading) dheading/dt = omegaEqual speeds produce straight travel; equal negative speeds produce reverse; opposite speeds rotate about the axle midpoint. A constant pair traces a circle of radius R = b(vL+vR)/(2(vR-vL)). Each held command is integrated with the closed-form circular-arc equations, including the straight-line limit. Fifty random cases agree with an independent numerical differential-equation solver within 1e-9 m/rad tolerance.

The cart center is not the axle midpoint:

cart_center = axle_midpoint - a * (cos(heading), sin(heading)) cart_yaw = drive_heading - piHere a = +0.27 m is measured along the drive forward axis. In the unchanged cart frame the signed axle offset is -0.27 m. Confusing these signs would produce the wrong cart-center position during a turn.

Its local velocity is (v, -a*omega). That lateral component is normal for a point offset from a turning axle. The no-sideways-slip test must be applied at each powered wheel; both contact-point velocities have zero lateral component within 1e-7 m/s numerical tolerance. Applying a zero-lateral-speed rule to the cart center was the previous logical error.

Wheel circumference is 0.596903 m. Travelling 55 cm gives 0.921423 revolutions, or 13.8214 RPM over four seconds. Rendered drive-wheel rotation is distance / 0.095, using these same odometry distances. An independent contact-velocity check uses the compiled wheel axes, cart displacement and angular rotation to verify rolling direction for forward, reverse, curved and pivoting travel.

Passive casters align nominally with the velocity at each rear swivel pivot: in the drive frame this is (v - omega*y, omega*x), with x = -0.59 m and y = +/-0.2262 m. Direction is atan2(vy, vx), including reversing. The visible wheels trail the pivot; alignment is idealized. Caster drag, swivel lag and load-dependent dynamics remain unmodeled.

These are the standard differential-drive relationships described by WPILib. ROS 2 differential-drive control documentation distinguishes wheel radius/separation and command-based open-loop odometry from feedback-based odometry.


### Why the original smooth shot fails

The 1.60 m-radius, 35° orbit over 16 seconds requests peak axle speed of about 0.1145 m/s, already below the observed slow straight speed. The inner wheel asks for still less. Your driver clamps commands, rounds each to two decimals, then transmits them. Under the provisional deadband model a transmitted magnitude below 0.04 does not roll.

For this request the left powered wheel travels 0.5225 m and the right travels 0.0000 m. The cart therefore pivots around the stationary right contact point instead of following the requested arc. The maximum axle path error is 71.33 cm and maximum heading error is 26.61°. This is a conditional prediction, not a measured error on your hardware.

The simulator displays the requested cart-center curve as blue dashes and the command-predicted cart-center curve in orange. The numeric error is measured at the drive axle. Failed predictions remain viewable for diagnosis; passing or playing a preview does not approve a hardware shot. The arms are re-solved on the predicted chassis poses, so a failed drive can also violate framing or arm-motion checks. These failures remain visible.


### Independent steady-arc witness

Using transmitted commands 0.06,0.04, the provisional left/right speed magnitudes are 0.20625 and 0.1375 m/s in the configured direction. With b = 0.58 m, the analytic radius magnitude is 1.4500 m, and a -35° turn takes 5.153481 s. The integrated wheel-command trace and independent ideal circle differ by at most 1.78e-15 m. The simulator's comparison button rounds the duration to the input's 0.01 s resolution, so a small visible path error may remain.

This witness proves the wheel-command mathematics. It does not prove measured speed at 0.06, startup force, arm feasibility, or physical stopping. Its ideal instantaneous start/stop has discontinuous speed, so it cannot be used as a finite-force dynamics claim.


### Response, braking and replay limits

Optional response times use dv/dt = (target-v)/tau, integrated analytically for each wheel. With tau = 0.4 s and initial speed 0.1375 m/s, a zero command gives asymptotic travel v*tau = 5.5 cm, not an instantaneous stop. This is an editable scenario, not a calibration. If response times differ between wheel phases, the chassis uses 20 ms interval-average wheel displacement; this introduces an integration approximation in addition to the physical assumptions.

The preview ends at the recorded command window. A stop message is recorded at its end; nonzero assumed braking can imply additional coast beyond that window. The report includes its asymptotic predicted distance. Pause and scrub control playback, not physical braking. Actor-follow retiming and synthetic tracking-loss/obstacle holds are disabled for motor replay; otherwise they would silently invent lower speeds or immediate stops.


### What is still required for real-world agreement

- Confirm the 55 cm measurement used both motors at +0.04, and whether it includes acceleration from rest.
- Measure powered-wheel center spacing and powered-axle offset from the cart center.
- Supply the ESP32/hoverboard firmware and command mode. The Python UART wrapper contains no speed feedback or motion controller.
- Measure loaded left/right travel at multiple commands, in forward and reverse, plus startup, stop distance and turn angles.
- Record floor surface, payload/mass and ideally wheel-encoder or external pose measurements. Tire slip, caster friction and load sensitivity cannot be identified from one distance/time point.
The current implementation proves consistent geometry, serial-command emulation, differential-drive kinematics and transparent failure reporting. Exact real-world trajectory, traction, acceleration and braking are not established. The observed average speed alone cannot identify the motor dynamics; with a nonzero startup lag, average and steady speed differ.


### Reproduction

From the workspace root, run .venv/Scripts/python.exe apps/rehearsal/verify_drive.py. It runs 29 Python tests, then regenerates this report and the JSON evidence. Run scripts/TakeOne.ps1 -Command test for the complete local test set. Run node apps/rehearsal/export_models.mjs after geometry changes.

Evidence: verification/drive-proof.json, verification/test-results.txt, workspace tests/fixtures/upper_before_rotation.json, verification/default-prediction.json, and verification/steady-arc-prediction.json. Predictions include the complete timestamped UART command sequence and final stop packet. Model hash: 402c61d9ec68b8fb496f447c7306552bdd35fe297437512c316b4ce3aec181e8.

Motion ProofBack to Shot Studio · Motor Lab
