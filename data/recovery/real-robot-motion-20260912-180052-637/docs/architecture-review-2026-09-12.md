# Architecture review and decision

## Verdict

For TakeOne's intended filming product, the earlier coordinated-motion design is the stronger system blueprint. The current implementation is a cleaner, tested foundation but covers a narrower preset rehearsal. Retain the current package layout and reuse its model/planner; implement the earlier production contracts incrementally. The new Director prompt improves ownership but does not replace missing perception, choreography and execution work.

Reviewed sources: [current architecture](architecture.md), [arm movement design](arm-movement-design.md), [earlier coordinated design](../archive/imports/TakeOne-main/TakeOne-main/TAKE-ONE-Coordinated-Motion-Architecture.md), [original Director design](../lerobot/HackTheNorth_AI_Director_Final_Documentation.md), [latest Director prompt](requests/ASTRA-AI-DIRECTOR-PROMPT.md) and the active Python/JavaScript implementation.

| Criterion | Assessment |
|---|---|
| Complete production workflow | Earlier design: actor beats, dual-camera observations, shared progress, recording, review and generated derivatives |
| Existing code organization | Current implementation: product package, thin app, direct imports, explicit arm roles, independent environments |
| Director ownership | Latest prompt: one accountable runtime for session decisions, cancellation and completion |
| Hardware readiness | Neither is a demonstrated complete physical filming system |

## Current gaps, grounded in code

1. **Preset rather than general scene.** `planning/targets.py::actor_target` derives one actor target from height, turn and phase. There is no general multi-actor, object, dialogue-beat or edited-shot contract. More sliders cannot substitute for that contract.
2. **Incomplete path acceptance.** IK uses weighted position/pointing/horizon objectives. The validator checks aiming and camera height but does not gate the full tool-position residual for each arm. A default-shot check found maximum position differences of 0.18739 m for the phone and 0.14899 m for the light while `playable` was true and `requiresRevision` false. These are numerical differences from preferred positions, not physical tracking errors or direct sweep-distance errors. Explicit tolerances and accepted revisions are required. Evidence: `data/verification/architecture-review-position-residuals.json` at the workspace root.
3. **Preview availability is not feasibility.** `playable` excludes the assumed payload-margin and camera-height screens. Preserve inspectable failed previews, but separate renderability, achieved shot fidelity, and physical execution qualification clearly.
4. **Partial execution contract.** The combined `MotionFrame` has sequence and timestamp but no plan identity/revision/phase. Recent commands are not necessarily commands from the accepted shot. The present executor also requires its owner to call `poll`; it cannot protect against a blocked process by itself.
5. **Offline planning, not live control.** The roughly one-second compile prepares a whole trajectory. It cannot serve as a video-rate feedback controller. A bounded incremental correction path and synchronized observation-driven progress remain work to do.
6. **Testing scope.** The previously passing 62 tests supported regression, protocol and isolation claims. They did not establish full cinematic path fidelity, complete sensing-to-actuation integration or hardware qualification. The earlier completion description should have made this distinction clearer.

## Earlier design weaknesses

The "implementation-ready" label overstates integration readiness. Camera transport, original calibration, loaded dynamics and several physical interfaces are unresolved. The proposed native phone app, localization, coordinated optimization, voice and review stack is too broad for one initial milestone. The documented numerical experiments include separate perception/localization/controller tests and are not evidence of one complete physical feedback loop. Old steering alternatives must yield to the user's actual differential-drive cart.

## Product workflow retained from the video discussion

Story and intended effects → typed actor/camera/light choreography → feasibility checks → simple 3D rehearsal with effect placeholders → actual robot filming → review originals → Seedance enhancement → check preserved framing/performance/timing.

An optional generated demo is a communication artifact. The accepted plan remains the source for robot execution. For final enhancement, the actual take supplies the real performance. Planned empty space, eyelines, pauses and placeholders matter when a creature/object is to be added later. Intended occlusion or exit must not be mistaken for detector failure. Outside video references can be analyzed into the same shot format without becoming raw motor commands.

## Next implementation order

Keep the folder layout. Add a versioned scene/shot/actor-beat contract; full tool-position acceptance; plan-bound execution and shared phase; then demonstrate one complete shot with simulated/replayed observations before qualified physical execution. The Director and Seedance integration consume those contracts.

## New cart evidence and immediate cart-only work

The user subsequently supplied a 60 ms firmware watchdog: if motor commands stop arriving, failsafe runaway brakes activate. This replaces "unknown timeout" as the reported specification, not as independently measured stopping performance. `configs/cart-runtime.json` records its source and pending physical verification. The cart-only commissioning path is documented in [cart live testing](cart-live-testing.md). It does not address the arm residual problem or authorize combined replay.
