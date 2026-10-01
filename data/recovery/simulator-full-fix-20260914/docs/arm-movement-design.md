# Arm movement design

The planner describes the desired camera/light result first, then solves the five real joints. It never treats a camera pan as a single servo command or sends preview radians directly to hardware.

## Read the code in this order

```mermaid
flowchart TD
    Request[Shot request] --> Settings[settings.py: immutable validated settings]
    Settings --> Targets[targets.py: independent phone and light programs]
    Targets --> IK[kinematics.py: bounded five-joint solve]
    Wheels[simulation/drive.py: transmitted-wheel prediction] --> Timeline[trajectory.py: shared clock and joint spline]
    IK --> Timeline
    Timeline --> Validate[validation.py: forward checks across preview]
    Validate --> Plan[compiler.py: plan and provenance]
    Plan --> Preview[shared curve, existing FK and execution preview]
    Plan --> Gate[execution.py: freshness and hardware qualification]
    Gate --> Adapters[explicit cart and arm adapters]
```

The compiler is the application service that calls these stages in order. Rendering/mesh serialization lives in `simulation/robot.py`, separate from the arm solver. Simulation modules do not import the application or planning modules. No compatibility imports or sys.path bootstrap are used by the active app.

## Motion vocabulary and current implementation

| Intent | Implemented behavior | Where to configure/use |
|---|---|---|
| Track an actor | Hold a preferred tool position relative to the moving cart and aim at the world-space subject target | `TrackingMotion.at()`; default for both arms |
| Sweep | Translate from minus half to plus half the requested distance along cart X | Camera `armTravel`; light `lightTravel` |
| Lift / lower | Rise smoothly to the requested lift at mid-shot, then return to the starting height | Camera `armLift`; light `lightLift` |
| Combine sweep and lift | Compose both translations while maintaining subject pointing and horizon preference | Same tracking program; not a separate controller |
| Hold a world-space target | Keep one explicit position and look-at point while solving joint compensation for cart travel | `FixedWorldTarget`, available to code through `TargetStrategy`; not a UI preset |
| Joint hold / manual jog | Physical servo hold uses a fresh measured pose through the qualified adapter; a movement planner does not guess the pose | Existing execution/adapter contract; live bring-up remains gated |
| Optical roll / Dutch angle | No independent roll-shot control is exposed yet. Wrist roll currently participates in the IK horizon preference | Requires measured lens transform, cable limits and a specified horizon target before adding a preset |

Pan and tilt are achieved by solving the pointing constraint, not by assuming one motor rotates around the lens. All five joints can participate. A five-joint arm generally cannot meet six arbitrary position/orientation constraints, so the solver uses weighted position, pointing, horizon and continuity objectives, then independently measures the result. A converged optimization result is not automatically a feasible shot.

The phone has logical joints shoulder pan, shoulder lift, elbow flex, wrist flex and wrist roll. The recorded motor IDs are 1,2,3,4,6. The light uses the same logical joint order with IDs 1,2,3,4,5. Those identities belong to the device/calibration layer; they are not encoded into camera-space motion curves.

## One motion clock, independent arm programs

For normalized shot phase `u`, the translation uses `s(u) = 10u³ - 15u⁴ + 6u⁵`:

```text
cart_relative_x = sweep_m * (s(u) - 0.5)
height_addition = lift_m * sin(pi * s(u))²
world_position = cart_transform * (preferred_local_position + translation)
```

The default camera requests a 16 cm sweep and 4 cm lift. The light independently requests 12 cm and 3 cm. These happen to preserve the previous 75% lighting motion, but the light's values are now explicit settings and changing the camera no longer silently changes the light. The UI exposes all four values and includes an “Arm movement plan” explanation. Both comparison presets set all four values explicitly.

Drive forward is cart -X while filming forward remains cart +Y. Cart-relative authoring is resolved once against the reference dolly and stored as 321 immutable world-space phone/light targets. The coordinated solver may then adjust the shared cart without moving the desired shot. The accepted default stages the cart by `[-0.1331 m,+0.0794 m,-4.070°]`, applies a small differential-drive turn, and reintegrates its exact two-decimal UART schedule.

The light targets the subject 15 cm below the camera's aim point. The phone's preferred cart-relative forward position is 0.38 m; the light's is -0.12 m. These are preview preferences, not measured optical transforms. The entire light-arm bound must remain behind the lens plane for the clearance screen to pass.

## Solver and validation

Each compile owns one model and private solver scratch state. Warm starts and deterministic alternate seeds preserve branch continuity. The coordinated default solves 13 shared cart/arm horizon points, projects 17 arm keyframes, and validates the resulting spline on 541 task-space samples including every dispatch instant. Cart poses always come from powered-axle differential-drive integration and the cart-origin offset. This is prediction rather than measured odometry.

The solver rejects invalid seeds, coincident look-at targets and non-finite results explicitly. Vertical pointing uses a projected continuous right-axis reference rather than an undefined world-up cross product. It does not clip a failed solution into validity. Numerical optimizer termination, measured task feasibility and hardware readiness are separate. Failed predictions may still be inspected with their failed checks shown.

Forward kinematics checks full phone and light position, aim, phone height and true optical roll. The public policy is phone 1 cm preferred/2 cm fail, light 2 cm preferred/5 cm fail, 1° aim and 2° phone roll. Integer encoder conversion is replayed at every shot dispatch before acceptance. `planning/curve.py` preserves exact cubic coefficients; analytic extrema cover continuous range, velocity, acceleration and piecewise jerk. Prepared revisions use `planning/envelope.py` for conservative whole-robot swept nominal clearance, explicit attachments/set/actor bounds, static support margin and assumed gravity demand. These do not establish measured motor capacity, physical optical alignment or dynamic tipping stability.

The default nine-second shot has nonzero arm boundary velocities. `prepare --transition-seconds` creates explicit quintic approach/departure in a new artifact, optionally from ten measured initial model angles. The original shot remains unchanged between the transitions. Browser import, display, export and physical joint evaluation use that revision. The corrected model reaches 1.980 cm phone and 3.900 cm light maximum error; both pass the declared fail corridors while remaining above their preferred thresholds. Physical alignment, loaded response and timing remain incomplete. See [the correction record](mobile-ik-correction-2026-09-12.md).

## Patterns used and why

| Pattern | Concrete use |
|---|---|
| Immutable value objects | `ShotSettings`, `ArmSpec`, `ToolTarget`, `TrackingMotion`, `IKResult` |
| Strategy | `TargetStrategy` supports actor tracking and an explicit fixed world target |
| Composition | Sweep, lift and subject pointing combine into one target program |
| Application service / pipeline | `compile_shot()` coordinates stages and serializes the result |
| Dependency injection | Solver owns a supplied model; trajectory takes explicit strategies; executor takes adapters and clock |
| Ports and adapters | Cart/arm protocols separate real transports from deterministic test doubles |
| State machine | Explicit readiness, common-epoch motion, settling, retained hold, fault and supported release |

There is no plugin-discovery framework, service locator, event bus or chain of alternate implementations. Add a strategy only for a real new motion requirement. Add a hardware adapter only for a real device. A missing required input produces a clear error.

## Efficiency and quality

The expensive solve is performed once per arm/keyframe, seeded from its predecessor. Geometry is indexed once per evaluation. A single provenance snapshot is captured per compile and reused for plan identity. Source hashes now cover the product modules as well as configuration, models and calibration, so changing a target strategy changes the plan identity.

The first before/after measurement on this machine was 0.97 s versus 0.94 s; that difference is too small to claim a speed improvement. That historical refactor left the default joint/cart arrays unchanged. The current execution curve is checked independently against SciPy at knots, midpoints, dispatch instants and the endpoint. Reproduce the checks with `scripts/TakeOne.ps1 -Command test`; this also runs the pinned Ruff lint and formatting checks. Tests include independent arm changes, strict invalid inputs, failed solver status, between-keyframe aim errors, geometry/odometry regressions and real-wire behavior through mock transports.

## Adding a movement

1. Specify frame, units, position/aim behavior and endpoint meaning. Distinguish a camera result from a joint command.
2. Implement a pure `TargetStrategy`. Require explicit targets; do not silently substitute one strategy for another.
3. Pass one strategy for each named arm to `solve_trajectory`. Use the same wheel-derived cart timeline.
4. Test the target geometry analytically, then verify solved FK residuals and motion/clearance checks, including between keyframes.
5. Add an intentional request field/preset only once its meaning and bounds are documented. Update both browser controls and serialized outline.
6. Keep physical qualification separate: original calibration, signs/zeros, tool transforms, cable/load limits and start/stop execution must be supported by hardware evidence.
