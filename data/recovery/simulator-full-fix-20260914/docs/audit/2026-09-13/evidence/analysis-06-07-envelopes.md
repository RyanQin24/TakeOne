# Analyses 6 and 7 - tracking envelope, cart speed, torque re-screen, height band, track width

## Inputs (quoted)

- TakeOne-main/takeone/timing.py::MotionLimits (via plan['limits']): arm v=0.8 rad/s, a=1.8 rad/s^2, j=12.0 rad/s^3; yaw v=0.6 rad/s; cart v=0.25 m/s; source=ASSUMED_placeholder
- configs/arm-execution.json::commissioning_limits: velocity_rad_s=[0.8, 0.8, 0.8, 0.8, 0.8], acceleration_rad_s2=[1.8, 1.8, 1.8, 1.8, 1.8], jerk_rad_s3=[20.0, 20.0, 20.0, 20.0, 20.0] (policy for supervised trials, not measured capability)
- configs/rig.json::cart: minimum_speed_m_s=0.1375, minimum_command=0.04, command_cap=0.15, track_width_m=0.58, wheel_diameter_m=0.19
- configs/cart-runtime.json: commissioning_max_command=0.05, commissioning_max_duration_s=4.0, commissioning_equal_commands_only=True, watchdog_s=0.06, period_s=0.02
- configs/cart-response.json: mode=provisional_symmetric, wheel tables empty=True

## Analysis 6 - tracking envelope (pan axis), closed form checked numerically

theta(t) = atan(v t / d); omega = v d / (d^2 + v^2 t^2); peak omega = v/d at t=0.
omega_dot = -2 v^3 d t / (d^2+v^2 t^2)^2; extremum at v t = d/sqrt(3): |omega_dot|max = (3 sqrt(3)/8) v^2/d^2 = 0.6495 v^2/d^2.
omega_ddot(0) = -2 v^3/d^3 (peak magnitude at closest approach).
numeric check (v=d=1): peak omega=1.000000 (expect 1.0); peak |omega_dot|=0.649519 (expect 0.649519); peak |omega_ddot|=2.000003 (expect 2.0)

Standoff constraints: d >= v/omega_max; d >= v*sqrt(0.6495/alpha_max); d >= v*(2/J_max)^(1/3).

### ceilings: omega_max=0.80 rad/s, alpha_max=1.80 rad/s^2, Tree B MotionLimits jerk 12.0 rad/s^3 (ASSUMED_placeholder)

| subject speed v (m/s) | d_vel = v/0.80 | d_acc = v*sqrt(0.6495/1.80) | d_jerk = v*(2/J)^(1/3) | binding | required standoff (m) | vs 6.0 m clamp (intent.camera_track / planner.sample_goals) |
|---|---|---|---|---|---|---|
| 1.0 | 1.250 | 0.601 | 0.550 | velocity | 1.25 | inside clamp |
| 2.0 | 2.500 | 1.201 | 1.101 | velocity | 2.50 | inside clamp |
| 3.0 | 3.750 | 1.802 | 1.651 | velocity | 3.75 | inside clamp |
| 5.0 | 6.250 | 3.003 | 2.752 | velocity | 6.25 | EXCEEDS clamp |

### ceilings: omega_max=0.80 rad/s, alpha_max=1.80 rad/s^2, configs/arm-execution.json jerk 20.0 rad/s^3 (commissioning policy)

| subject speed v (m/s) | d_vel = v/0.80 | d_acc = v*sqrt(0.6495/1.80) | d_jerk = v*(2/J)^(1/3) | binding | required standoff (m) | vs 6.0 m clamp (intent.camera_track / planner.sample_goals) |
|---|---|---|---|---|---|---|
| 1.0 | 1.250 | 0.601 | 0.464 | velocity | 1.25 | inside clamp |
| 2.0 | 2.500 | 1.201 | 0.928 | velocity | 2.50 | inside clamp |
| 3.0 | 3.750 | 1.802 | 1.392 | velocity | 3.75 | inside clamp |
| 5.0 | 6.250 | 3.003 | 2.321 | velocity | 6.25 | EXCEEDS clamp |

Coefficients: d_vel = 1.250 v; d_acc = 0.601 v; d_jerk = 0.550 v (J=12) / 0.464 v (J=20). Velocity binds at every speed.

### Vertical axis (tilt)

Head bob: z = A sin(2 pi f t), A=0.05 m, stride frequency f=2.7 Hz for a 3 m/s jog (assumed gait figure, not measured). At standoff d the tilt angle is ~z/d.
- d=1.8 m: peak tilt rate 0.471 rad/s (ceiling 0.80), accel 7.994 rad/s^2 (ceiling 1.80), jerk 135.62 rad/s^3 (ceiling 12) -> jerk binds
- d=3.75 m: peak tilt rate 0.226 rad/s (ceiling 0.80), accel 3.837 rad/s^2 (ceiling 1.80), jerk 65.10 rad/s^3 (ceiling 12) -> jerk binds
- d=6.0 m: peak tilt rate 0.141 rad/s (ceiling 0.80), accel 2.398 rad/s^2 (ceiling 1.80), jerk 40.69 rad/s^3 (ceiling 12) -> jerk binds
Descending steps: rise 0.17 m per step at 2 steps/s = 0.34 m/s sustained vertical rate; at d=3.0 m the tilt rate is 0.113 rad/s, at d=1.8 m 0.189 rad/s; both inside the 0.80 rad/s ceiling. Vertical is not the binding axis; horizontal pan is.

## Analysis 7 - cart speed against a 3 m/s jog

| figure | value (m/s) | provenance | 3 m/s jog / value | 1.4 m/s walk / value |
|---|---|---|---|---|
| configs/rig.json minimum_speed_m_s (55 cm / 4 s at command 0.04, provisional) | 0.1375 | single operator observation, provisional | 21.8x short | 10.2x short |
| linear extrapolation of that sample to command_cap 0.15 | 0.516 | UNEVIDENCED extrapolation (response tables empty; drift reported) | 5.8x short | 2.7x short |
| TakeOne-main drive.py DriveLimits.max_speed_mps | 0.25 | ASSUMED_placeholder | 12.0x short | 5.6x short |

Supervised envelope (configs/cart-runtime.json): command <= 0.05 for <= 4.0 s, equal commands only (straight line). At the provisional 0.1375 m/s-per-0.04 slope, 0.05 -> ~0.172 m/s; net displacement in 4.0 s ~0.69 m. That is the whole displacement budget of a qualified cart move today.
Walking speed the qualified envelope supports: 0.172 m/s (provisional slope) for at most 4.0 s -- slower than a slow walk (~1.0 m/s) by 5.8x. Following a walking subject is not inside the qualified envelope either; following a runner is not available.

## Key-light angle from one cart

- lateral offset 0.290 m at subject distance 2.0 m: max key angle ~ atan(0.29/2.0) = 8.3 deg (planner uses asin(comfortable/dist) = 8.3 deg)
- lateral offset 0.290 m at subject distance 3.75 m: max key angle ~ atan(0.29/3.75) = 4.4 deg (planner uses asin(comfortable/dist) = 4.4 deg)
- lateral offset 0.374 m at subject distance 2.0 m: max key angle ~ atan(0.3745/2.0) = 10.6 deg (planner uses asin(comfortable/dist) = 10.8 deg)
- lateral offset 0.374 m at subject distance 3.75 m: max key angle ~ atan(0.3745/3.75) = 5.7 deg (planner uses asin(comfortable/dist) = 5.7 deg)
A 35 deg key at 2 m needs a lateral offset of 2*tan(35deg) = 1.40 m; no arm on this cart reaches it. Ring-light irradiance falls as 1/d^2: moving from 2.0 m to 3.75 m keeps 28% of the light.

## C6 - torque re-screen against STS3215 datasheet figures (spec, not measured)

Datasheet figures (spec, not measured): STS3215 7.4 V variant (C001): stall 19.5 kg*cm at 7.4 V, 16.5 kg*cm at 6 V; rated 5 kg*cm at 7.4 V, 4 kg*cm at 6 V; gear 1:345
(https://pages.switch-science.com/comparison/files/feetech/serial-sts/STS3215_datasheet.pdf). 12 V variant (C047/C018): stall 30 kg*cm, rated 10 kg*cm, gear 1:345
(https://www.seeedstudio.com/STS3215-30KG-Serial-Servo-p-6340.html). 1 kg*cm = 0.0980665 N*m.
Bus voltage on this rig (docs/robot-commissioning.md line 68): phone arm read 11.9-12.6 V; light arm read 5.8 V at rest and 4.9 V during approach on a 5 V supply. Motor variant of each arm is unconfirmed there.

| take | status (0.800 N*m assumed) | worst joint | peak N*m | gravity N*m | cam arm peak | vs cam rated 0.981 | vs cam stall 2.942 | light arm peak | vs light rated 0.392 (6 V) | vs light stall 1.618 (6 V) |
|---|---|---|---|---|---|---|---|---|---|---|
| Shot 1 · static | fail | light_shoulder_lift | 0.840 | 0.904 | 0.734 | conditional | conditional | 0.840 | fail | conditional |
| Shot 2 · orbit | conditional | cam_shoulder_lift | 0.755 | 1.080 | 0.755 | conditional | conditional | 0.497 | fail | conditional |
| Shot 3 · static | conditional | cam_elbow_flex | 0.734 | 0.904 | 0.734 | conditional | conditional | 0.497 | fail | conditional |
| Shot 4 · tilt | fail | cam_shoulder_lift | 4.913 | 1.115 | 4.913 | fail | fail | 0.527 | fail | conditional |
| Shot 5 · static | fail | light_shoulder_lift | 0.849 | 0.906 | 0.733 | conditional | conditional | 0.849 | fail | conditional |
| Shot 6 · pan | fail | cam_shoulder_pan | 15.296 | 1.029 | 15.296 | fail | fail | 2.555 | fail | fail |
| Shot 8 · static | fail | light_shoulder_lift | 0.851 | 0.906 | 0.733 | conditional | conditional | 0.851 | fail | conditional |
| Shot 9 · pull_back | fail | cam_shoulder_lift | 1.332 | 1.260 | 1.332 | fail | conditional | 0.980 | fail | conditional |
| Shot 11 · static | conditional | cam_elbow_flex | 0.734 | 0.904 | 0.734 | conditional | conditional | 0.618 | fail | conditional |

Verdict changes vs the 0.800 N*m assumption: 3 of 9 takes change against RATED figures; 4 of 9 change against STALL figures.
Gravity-only demand on the light arm (0.73-0.77 N*m per the plan) already exceeds the light arm's 6 V RATED torque (0.392 N*m) on every take: at its measured 4.9-5.8 V supply the light arm is holding more than its continuous rating on gravity alone. That is a build/supply finding, not a planning finding.

## C9 - camera-height band arithmetic

- mount 1.20 m, reach bound 0.535 m, reach_fraction 0.70: comfortable=0.3745 m, max_dz=0.3635 m, band [0.84, 1.56] m
- mount 1.20 m, reach bound 0.535 m, reach_fraction 0.85: comfortable=0.4547 m, max_dz=0.4458 m, band [0.75, 1.65] m
- mount 1.20 m, reach bound 0.535 m, reach_fraction 1.00: comfortable=0.5350 m, max_dz=0.5274 m, band [0.67, 1.73] m
- mount 1.23 m, reach bound 0.535 m, reach_fraction 0.70: comfortable=0.3745 m, max_dz=0.3635 m, band [0.87, 1.59] m
- mount 1.23 m, reach bound 0.535 m, reach_fraction 0.85: comfortable=0.4547 m, max_dz=0.4458 m, band [0.78, 1.68] m
- mount 1.23 m, reach bound 0.535 m, reach_fraction 1.00: comfortable=0.5350 m, max_dz=0.5274 m, band [0.70, 1.76] m
The UI slider (dist/app.js renderAnchors nominal_camera_height_m) offers 0.5-2.0 m; camera keys accept up to 2.2 m (sample_goals clamp); the measured rig reaches 1.80 m (configs/rig.json max_extended_height_m). At reach_fraction 0.70 from a 1.20 m mount the band top is 1.56 m: 0.24 m of the measured 1.80 m envelope is removed by the choice of 0.70 plus the 0.03 m mount error.

## B3 - track width effect on differential kinematics

- track 0.34 m: yaw rate for a 0.10 m/s wheel-speed difference = dv/track = 0.294 rad/s; wheel speed difference needed for the 0.6 rad/s yaw ceiling = 0.204 m/s
- track 0.58 m: yaw rate for a 0.10 m/s wheel-speed difference = dv/track = 0.172 rad/s; wheel speed difference needed for the 0.6 rad/s yaw ceiling = 0.348 m/s
Ratio 0.58/0.34 = 1.71: for the same wheel-speed difference the real cart yaws 1.71x SLOWER than the simulated one; equivalently the in-place rotation phases (which the governor already times at the yaw ceiling, not at a wheel-speed limit) are unaffected in duration, but the WHEEL speeds the drive screen infers per phase are 1.71x too low for a rotation and the no-slip/turning-radius checks are evaluated on the wrong wheel geometry. The tipping screen uses cart_footprint (0.46 x 0.38 m assumed) not the track; with the real 0.58 m track the support polygon is wider, so the assumed screen is conservative in roll and unmeasured in pitch (axle -0.27 m, casters +0.32 m per configs/rig.json).
