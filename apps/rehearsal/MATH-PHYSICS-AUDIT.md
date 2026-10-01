> Historical record: subsequent source, calibration, geometry and ownership changes are documented in [the current real robot implementation](../../docs/real-robot-implementation-2026-09-12.md). The current measured platform height is 1.23 m, maximum extended height is 1.80 m and horizontal extension is 0.34 m per arm. Fake replay/timing results below remain historical software evidence and do not establish physical movement.

# TAKE ONE MVP — math, physics and logic audit

Audit date: 2026-09-11. Scope: the current illustrative MVP, not a measured robot.

**Historical snapshot notice / resize update:** The numerical tables and geometry findings below describe the pre-resize model (plan `ed3f76256486`, source model hash `6efaab07ad2393e0725708e4da08eef98d329777540b66b06403fa4499201908`). The current `rig_tall.xml` places both mounts at the measured 1.23 m platform height and adds an illustrative support/deck. An explicit unchanged-arm pose reaches about 1.731 m at the optical site; the separately reported 1.80 m is the measured physical maximum envelope. Current `audit_model.py` reruns against this variant, so its output intentionally differs from this historical snapshot. Vehicle-reference, adaptive-braking, scene-collision and stability findings below remain unresolved. See README and resize regression tests. No physical approval follows from the resize.

## Verdict

**The coordinate/kinematic calculations agree with an independent implementation. The MVP is not a physically validated digital twin. Its geometry does not yet match the newly stated 1.2 m cart and 0.60 m arm reach.**

The previous 10 passing tests demonstrate specific software behavior, not complete physics correctness. The UI's 10 nominal screens likewise do not establish hardware feasibility. No hardware approval is issued. This audit leaves the original evidence bundle and running geometry unchanged pending dimension clarification.

## Reproduce the evidence

From `E:/TakeOne/rehearsal-mvp`:

```powershell
& ../TAKE-ONE-Simulation-Evidence/takeone_validation/.venv/Scripts/python.exe audit_model.py
node tests/audit-controller.mjs
```

The Python audit asserts tolerances and prints numeric results, model SHA-256 and plan ID. It uses seed 20260911, 100 random configurations, 3,201 nominal trajectory evaluations, and 40 midpoint checks for the dynamics identity and browser interpolation. It reads the raw XML for independent forward kinematics; it does not call the compiler's FK to generate the expected transformations. Jacobian expectations come from central finite differences of that independent FK. This is reproducible numerical evidence, not a universal proof over every configuration.

## What passed, and exactly what that establishes

| Calculation | Evidence for the current model | Scope |
|---|---|---|
| Raw XML rigid-transform composition vs MuJoCo | Maximum site position difference 5.56e-16 m; rotation-matrix element difference 1.00e-15 | Transform implementation agreement across 100 sampled poses, not dimensional calibration |
| Position Jacobian vs independent finite differences | Maximum difference 4.42e-10 | Differential translation calculation for both optical sites and all 13 coordinates |
| Quintic cart timing | Calculated peak 0.114537223 m/s vs analytic 0.114537232 m/s | The intended center-point circular path, not rear-wheel no-slip feasibility |
| Circular path interpolation | Radius error at most 8.74e-9 m | Nominal 1.6 m radius shot |
| Inverse dynamics equation | Maximum residual 1.12e-16 in checked frames | Internal numerical consistency of the assumed model, not measured motor performance |
| Browser pose interpolation vs FK of interpolated joints | At tested midpoints, body-position difference <=4.00e-7 m and rotation difference <=5.42e-8 rad | Negligible display approximation for this slow nominal shot; not a guarantee for arbitrary future trajectories |
| Pause/loss characterization | Both demonstrably stop the phase position immediately | Confirms a synthetic HOLD, and disproves interpreting it as bounded physical braking |

For the timing result, `e(s)=10s^3−15s^4+6s^5`, so `e'(s)=30s²(1−s)²` and its maximum is `1.875` at `s=0.5`. Thus `v_max=R × orbit_radians × 1.875 / duration`. Units are meters/second.

The verified dynamics identity is `qfrc_inverse = M*qacc + bias − passive − constraint`. MuJoCo documents the relation between mass, bias, passive forces and constraints in its [computation reference](https://mujoco.readthedocs.io/en/stable/computation/index.html#general-framework). Matching the identity is a necessary numerical check, not experimental validation of its inputs.

## Findings that prevent physical approval

### 1. Geometry mismatch — must resolve before resizing

The compiled cart body is **0.46 × 0.38 × 0.13 m**. Its top is **0.20 m** above ground; the arm-mount origins are **0.22 m** high. The assumed total modeled mass is **5.806012 kg**. None is a measurement of the user's 1.2 m cart.

The raw camera-chain segment translation norms, starting at the arm-mount origin and ending at the optical site, are:

`0.0734979 + 0.0647752 + 0.1160000 + 0.1350002 + 0.0637246 + 0.0820061 = 0.5350040 m`.

Rotations preserve vector lengths. By the triangle inequality, the mount-to-optical-point distance cannot exceed this sum for **any** joint angles. This is a rigorous loose upper bound for this chain, not a claim that 53.5 cm is achievable with joint limits or desired camera orientation. The light has the same chain/site geometry. Therefore this model cannot support a 60 cm mount-relative optical displacement.

Pending clarification: does 1.2 m refer to cart height, length or width? Does 60 cm mean mount-to-tool maximum reach above/below the mount, and where exactly are the mounts?

If the mount is 1.2 m high and true radial reach is 0.6 m, then **0.6–1.8 m is only an outer vertical envelope**. It does not guarantee every pose in that range. A necessary idealized condition is `x²+y²+(z−1.2)² <= 0.6²`; joint limits, camera orientation, the cart body and self-collisions shrink that workspace. Full vertical reach and full horizontal reach cannot occur simultaneously.

Do not just enlarge the rendered meshes: link transforms, collision geometry, centers of mass, inertia tensors and actuator requirements must describe the same revised mechanism. Actual link dimensions and mass data are needed to call that revised model physical.

### 2. Cart center is incorrectly treated as a rear-axle bicycle reference

The trajectory sets the cart **center** velocity tangent to the arc. But the modeled rear wheels are at local `x=−0.16 m`. Rigid-body velocity gives `v_lateral,rear = v_lateral,center − 0.16*yaw_rate`.

The default shot has center lateral speed <=1.35e-7 m/s yet rear-wheel lateral speed reaches **0.011454 m/s**. Therefore center no-sideways-motion is not sufficient to prove a conventional nonsteering rear axle rolls without lateral slip. The steering screen's **11.3°** uses `atan(0.32/1.6)` while applying its radius to the wrong reference point.

Required correction: confirm drive/steering type, plan at the correct axle reference, and transform to the cart center and both mounts. Differential drive, Ackermann and four-wheel steering need different constraints. Do not silently choose the hardware topology.

### 3. Adaptive timing does not preserve nominal derivative limits

The browser's phase limiter is overridden by a position clamp. Reproducible example: at shared phase 0.4, previous rate 0.0625/s, and a 20 ms actor-pause step, the realized phase rate becomes **0**, but its stored `velocity` remains **0.0589/s**. Thus stored velocity is not the derivative of the emitted path. Tracking-loss HOLD similarly changes rate immediately to zero.

The architecture correctly requires:

`q_dot = q_s*s_dot`

`q_ddot = q_ss*s_dot² + q_s*s_ddot`

`q_jerk = q_sss*s_dot³ + 3*q_ss*s_dot*s_ddot + q_s*s_jerk`.

The MVP does not enforce those full expressions during actor pace changes, pauses or tracking faults. A physically smooth stop may necessarily continue a short distance beyond the actor's stopped phase. It needs a reserved stopping corridor and measured actuator/drive limits, not an instantaneous no-ahead clamp.

### 4. Nominal spline is not jerk-bounded through start/stop transitions

The cubic spline constrains endpoint velocity to zero, not acceleration. Its maximum arm acceleration at the endpoints is **0.131783 rad/s²**. Entering this trajectory from a stationary hold with zero acceleration creates an acceleration jump; bounded within-segment jerk does not bound jerk at that transition. The reported **1.076 rad/s³** only describes the sampled spline interior/pieces.

Required correction: a trajectory and approach/stop procedure with appropriate boundary derivatives, followed by checks of the actual controller output, not only nominal planning knots.

### 5. Visible world and collision world are not the same

The current compiler checks cross-arm geometry at only **41 samples**. It does not establish continuous all-pair collision clearance, actor clearance, cart clearance, cable clearance or complete swept-volume safety. The browser actor is at world origin and has adjustable height, while the inherited MuJoCo world contains static actor proxies at `x=1.8 m`. The rendered wall and set blocks are not synchronized collision geometry in the solver. The obstacle checkbox injects a synthetic fault; it does not discover an obstacle from perception or geometry.

Required correction: one authoritative scene description feeding rendering and collision checks; collision policy for adjacent links; actor/obstacle uncertainty envelopes and continuous or conservatively bounded swept checks.

### 6. Torque margin is an assumption and is not a playback gate

The current nominal demand screen reports **0.695 N·m** against an assumed **0.800 N·m** allowance. The compiler explicitly excludes this screen from `playable`. Therefore “playable” means visual rehearsal eligibility, not all physics checks passed.

A 0.30 kg payload at a 0.60 m **horizontal perpendicular gravity lever arm** alone needs approximately `0.30 × 9.81 × 0.60 = 1.7658 N·m`, before arm self-weight and dynamics. This is an illustrative load calculation, not the torque at every joint or at vertical full extension. It shows why increasing reach cannot retain the old torque conclusion.

Measured payload/link masses, inertia, motor continuous capability at the chosen voltage/temperature, and transmission properties remain missing. Slower motion does not remove gravity load.

### 7. No traction, tipping or measured sensing proof

The cart has planar x/y/yaw joints only; it cannot tip in this model. Wheels are rigid attached geometry with collision disabled, not rolling/contact-controlled wheel bodies. The MVP has no wheel-ground traction or suspension simulation, support-polygon/stability gate, physical braking validation, encoder feedback, actor tracking from images, lens calibration or calibrated photometry.

The camera monitor uses geometric rendering from the solved pose. Light coverage is a rendered cone, not a measured illuminance guarantee. Face target centering does not prove visibility, occlusion avoidance, focus, exposure or photographic quality.

## Acceptance path after dimensions are clarified

1. Record cart height/length/width, axle locations/steering, arm mounting transforms, link dimensions and joint limits. Clearly distinguish measured values from placeholders.
2. Update one authoritative robot/scene model; verify dimension and reach constraints before making visual claims.
3. Correct vehicle reference-frame constraints and physical timing/stop logic; add regression cases for the failures above.
4. Validate nominal and adaptive output with torque, stability, scene-clearance and stopping-envelope checks. Keep unavailable evidence marked unavailable.
5. Only after measured calibration and protected low-speed hardware tests consider real-world approval. A passing numerical model alone is not that approval.
