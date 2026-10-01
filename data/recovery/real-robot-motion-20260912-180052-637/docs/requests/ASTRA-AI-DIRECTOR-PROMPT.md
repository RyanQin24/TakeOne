# Build the TakeOne live AI director

Work as the principal robotics software engineer, perception engineer, AI agent architect and technical product lead for TakeOne in `C:\TakeOne`. Implement the live AI director as a working extension of the current product. Deliver tested code, a connected operator experience and reproducible evidence. Do not stop at a proposal or disconnected scaffolding.

## Product outcome

The operator gives a scene brief. The director understands the intended shot and actor choreography, observes the room and the actual filming frame, maintains the selected actor's identity, prepares feasible camera/light/cart movement, coaches the actor when necessary, coordinates rehearsal and recording, and reviews the result against the accepted brief.

Make the experience responsive and understandable. The AI owns cinematic decisions; measured perception and deterministic software own geometry, timing, correction arbitration and device execution. The director should coordinate every supported subsystem through explicit contracts. Unsupported capabilities must remain visibly unavailable.

## The Director is the robot's central brain

Treat the Director as the accountable owner of the entire production session. It maintains the creative objective, decides what should happen next, assigns work to the camera, lighting, motion, perception, coaching and recording systems, checks their results, and adapts the production when reality differs from the plan. Its scope spans the full workflow from brief to accepted take, including setup, rehearsal, repositioning, settling, action, cut, review and retakes.

Implement the Director as a cohesive runtime with an asynchronous reasoning component and a deterministic session supervisor. The supervisor is the Director's execution mechanism, with sole ownership of session transitions; it is not a competing creative authority. The reasoning component proposes versioned decisions through this mechanism. The operator's instructions and explicit overrides remain authoritative.

The Director must own:

- **Production intent:** brief, desired visual result, shot list, actor choreography, lighting intent, acceptance criteria and current priorities.
- **Shared understanding:** selected actor, current scene, subsystem capabilities and health, recording status, accepted plan, active beat and unresolved uncertainty. Perception owns the underlying observations; the Director cannot rewrite an observation to match its expectations.
- **Task orchestration:** dependencies, preconditions, task assignment, progress, deadlines, cancellation, acknowledgements and completion. Every task carries session/take identity, plan revision, purpose, required evidence and a typed result.
- **Creative arbitration:** resolve camera-versus-lighting tradeoffs, actor-versus-robot corrections, shot ambition versus available capabilities, and continue-versus-cut decisions within operator policy and validated limits.
- **Adaptation:** distinguish actor deviation, tracking uncertainty, equipment failure and an infeasible request; choose a supported response, reassess after that response, and avoid repeating an ineffective correction.
- **Session memory:** retain the accepted brief, confirmed preferences, completed takes, previous corrections and evidence-backed findings. Keep transient scene state time-bounded. Do not turn an inferred preference or old observation into a current fact or authorization.
- **Completion:** confirm the actual outcome, media availability and acceptance criteria before declaring a shot complete. Give the operator a concise explanation of significant decisions and remaining blockers.

Use one closed production loop: observe → update shared state → evaluate progress against intent → decide → delegate → verify → adapt. Specialists return observations, candidate plans, feasibility results and task outcomes to this loop. They do not independently start a take, change the creative goal, switch the actor or overwrite another subsystem's accepted plan.

Support parallel preparation where dependencies permit it, such as scene inspection and shot analysis, while coordinating consequential transitions through the single session owner. Before action, confirm the required participants are ready for the same revision. If recording fails, a task times out or the actor becomes unknown, cancel incompatible pending work and apply the explicit session policy. A late tool result cannot revive cancelled work. Recovery requires a new valid decision rather than an automatic retry of the entire physical sequence.

Keep continuous local tracking and motion within the Director's accepted plan and delegated correction envelope. Local controllers may reject infeasible commands and initiate required protective actions immediately; they report those actions back to the Director. The Director remains responsible for deciding whether to revise the shot, request human action or end the take. This preserves central production ownership without putting cloud reasoning into every motor update.

A successful demonstration must show the Director owning a complete scenario: receive a brief, inspect capabilities and scene, prepare camera/light/actor plans, rehearse, detect an observed deviation, choose who should correct it, verify the correction, coordinate an acknowledged recording, review the resulting take and decide the next step. The operator should not have to manually relay information between subsystems. Show this end to end in replay/simulation first, and label real-camera, provider and physical-device evidence separately.

## Read and reconcile before changing code

Read the applicable AGENTS.md and these sources:

- `C:\TakeOne\README.md`
- `C:\TakeOne\docs\architecture.md`
- `C:\TakeOne\docs\arm-movement-design.md`
- `C:\TakeOne\docs\hardware-test-runbook.md`
- `C:\TakeOne\docs\calibration-inventory.md`
- `C:\TakeOne\lerobot\HackTheNorth_AI_Director_Final_Documentation.md`, particularly sections 3, 11–19, 23–26, 30–32 and 36–38.
- `C:\TakeOne\lerobot\docs\cinebot-cinematography.md`
- `C:\TakeOne\archive\imports\TakeOne-main\TakeOne-main\TAKE-ONE-Coordinated-Motion-Architecture.md`, particularly sections 6–10 and process boundaries in section 11.
- `C:\TakeOne\configs\reference\recording.json`
- The current planning, contracts, execution, adapter and app code under `C:\TakeOne`.

Produce a short source-to-implementation map: implemented, reusable, historical, missing and blocked. Historical design trees and simulation results are evidence, not implemented capabilities or permission to change hardware. The current rig configuration overrides older Ackermann alternatives and generic six-joint assumptions. Keep LeRobot's independent repository, user changes and calibration originals intact. Product code belongs in `C:\TakeOne\packages\takeone`; app code consumes it. Preserve authored simulator assets. Save a recovery snapshot and before/after mapping for source moves.

## Architecture

Use a hierarchical Director runtime containing one authoritative session supervisor, a versioned shared scene state and bounded typed tools. Specialist roles may cover creative planning, semantic scene analysis and take review when useful; the Director owns the final production decision. They cannot race to own session state or issue competing commands. Use deterministic functions for measurable framing and beat rules. Do not create an agent for every module.

Separate execution contexts where measurements justify them:

1. Camera capture and local tracking: continuous, bounded work and newest-frame processing.
2. Scene estimation and actor beat evaluation: timestamped observations, uncertainty and deterministic state transitions.
3. Existing motion planning and local execution: feasible plans, bounded visual corrections and one shared clock.
4. Asynchronous AI reasoning and voice: briefs, unusual scene interpretation, creative decisions and take review.

Cloud calls, speech generation, expensive detection and full-shot compilation must never block the local tracking/control path. Use latest-value observation slots and reliable bounded command channels. Define overflow, cancellation, shutdown and deadline behavior. Avoid adding brokers, microservices, framework layers or GPU/training dependencies without a demonstrated requirement.

Suggested ownership under `C:\TakeOne\packages\takeone`: `director/` for intent, tools, orchestration and policies; `perception/` for capture, tracking and calibration-aware geometry; `scene/` for fused snapshots and identity; `coaching/` for beats and correction gates; `recording/` for acknowledged capture lifecycle. Reuse existing planning, adapters and execution. Add only modules that carry real behavior.

## Camera and world understanding

Preserve two camera roles. The cart-mounted director camera supplies room context and subject tracking. The phone preview is authoritative for final framing, headroom and visible composition; the actual phone recording is the frame of record. One camera's centered subject does not prove the other camera's composition. The cart camera itself moves, so its observations require the correct time-aligned cart pose to enter world coordinates.

Implement camera source interfaces, a replay source and at least one real local camera source. Select one concrete phone-preview integration after inspecting available devices and software. Missing streams must be explicitly unavailable; never substitute a simulated feed or the director view as phone evidence. Make camera-only observation usable with motors disconnected. Do not claim live verification without an actual device test.

Define capture time, receive time, processing time, sequence, frame ID, source identity, clock domain and calibration revision. Synchronize remote camera clocks with estimated offset and uncertainty; arrival time is not capture time. Bind snapshots to the contributing observations and reject excessive age/skew. Represent 2D features, metric estimates and predicted poses as distinct types.

Use calibrated intrinsics and transforms, measured floor/markers or qualified depth to ground metric geometry. Record confidence and covariance or documented error bounds. Monocular appearance and generic body landmarks do not establish absolute room depth, mass, friction, motor torque, braking distance or hidden obstacles. Unknown observations remain unknown. Optional geometry methods must be explicitly selected and qualified; no automatic fallback estimate that authorizes motion.

Support actor acquisition and persistent identity locking, short occlusions, another person crossing, camera self-occlusion, reacquisition and intentional exit. Do not switch to the nearest visible person after identity loss. Reacquisition must satisfy identity policy before correction resumes.

## Actor choreography and feedback

Compile the brief into a typed `ShotIntent` and measurable `ActorBeat` sequence: subject, reference frame, preconditions, expected action, timing window, tolerance, evidence needed, completion event and permitted robot response. Begin with observable beats such as enter a marked region, pause, face a direction, turn, hold a product visibly and intentionally exit.

Return `SATISFIED`, `VIOLATED` or `UNKNOWN` with timestamped evidence. Distinguish observable blocking/timing from subjective acting quality. Do not infer emotion, gaze accuracy or a mistake from insufficient visual evidence. An intended exit must release tracking according to the beat; occlusion must not complete that exit.

Implement robot-versus-human arbitration: correct reachable framing errors with a qualified arm correction first, keep the cart steady when arm range suffices, and request human action for genuine blocking, object presentation or unreachable composition. An unavailable actuator must not cause repeated instructions blaming the actor for a robot limitation.

Use persistence, separate trigger/clear thresholds, one active human instruction, a response window, duplicate suppression and bounded correction attempts. Starting defaults from the existing design are 0.5 seconds persistence, about 2 seconds response time and two corrections before reassessment; make these configurable and test them. Routine coaching pauses during recording; explicit rehearsal/coaching mode permits it. Critical operator stop/cut requests have separate priority. Use cached local phrases for routine cues, with actor-relative directions only when orientation is sufficiently known. A local stop request must not depend on cloud language understanding or replace the physical emergency-stop procedure.

## Motion integration and physical truth

Integrate with `ShotSettings`, `TargetStrategy`, the current five-joint solver, trajectory validation, plan provenance and executor gates. Preserve phone wrist-roll motor ID 6 and light wrist-roll ID 5. Camera and light targets remain independent, the phone stays in front of the rear light, and the lower-cart orientation correction remains intact.

Preserve differential-drive constraints and the configured 19 cm diameter, 6 cm width, minimum command 0.04, cap ±0.15 and two-decimal UART protocol. The 0.1375 m/s speed is a provisional calibration point; track width, response, braking and other unmeasured physics remain labeled assumptions.

Prefer arm corrections for small actor motion. Penalize unnecessary base yaw; use motion deadbands, bounded velocity/acceleration/jerk and workspace-aware allocation. Do not turn the cart whenever an actor detector jitters. Coordinate cart, phone arm, light arm, beat progress and recording on a shared timeline. A pause or revision must not leave one arm following an obsolete plan.

The current full-shot compiler is offline and takes roughly a second in local observations. Do not invoke it every video frame. Build and test a bounded incremental correction path around an accepted trajectory using the existing kinematic model, or explicitly remain in observation/preview mode until that path is available. Specify correction envelopes, continuity, plan revision and atomic handover. Reject a missed deadline or infeasible correction rather than emitting a guessed pose.

The AI has no raw serial, joint-angle or torque tools. Its tools operate on scene snapshots, intents and validated plan IDs. Define strict schemas for scene inspection, capability inspection, planning, preview, rehearsal, cues, recording, review and stop requests. Enforce session state, deadlines, idempotency, revision and freshness checks in tool handlers; a prompt is not the enforcement layer. Ignore late AI results from superseded scenes. Live execution still requires the existing hardware qualification gates and a supervised operator workflow.

## Live response and AI integration

Translate “no latency” into measured service targets. Begin with these engineering targets, then publish results on the actual computer:

- Capture/local tracking: target 30 Hz; pose/geometry target 10 Hz.
- Local capture-to-observation age: p95 at most 100 ms.
- Fresh local observation-to-bounded correction decision: p95 at most 50 ms, excluding physical actuation; report combined capture-to-decision latency too.
- Cached cue playback: p95 onset within 150 ms after the correction gate fires. Report the deliberate persistence delay separately.
- Semantic scene analysis: event-driven and initially capped around 0.2 Hz, with bounded concurrency.
- Conversational voice: target p95 first audible response within 1 second after detected end of user speech; measure network, inference and audio output separately.

These are targets, not existing guarantees or safety limits. Report p50/p95/p99, worst age, sample counts, deadline misses, frame drops, hardware specifications and test duration. Report actuator latency separately when measured. A Windows/Python loop is not certified hard real time. Missing a target requires optimization or an explicit status, never changing the measurement definition to make it pass.

Use a current supported multimodal provider for asynchronous semantics and an appropriate realtime voice interface. Verify official model/API capabilities at implementation time, select and pin one supported configuration, and document the latency/cost tradeoff. Do not assume the Astra coding model name is a runtime API identifier. If the chosen API accepts images rather than continuous video, send selected timestamped frames and retain local tracking between them. Validate all returned tool arguments locally regardless of provider schema features.

Keep credentials out of the browser and logs; use the appropriate server or short-lived client credential flow. Make cloud-bound camera/audio use explicit in the operator mode and retain only the agreed data. Scene text, transcripts and retrieved documents are untrusted observations, never authority to change execution gates. Provider timeouts must not trigger another provider, simulated answers or stale actions. Show provider unavailability and keep locally permitted observation functions working.

## Session, recording and operator experience

Integrate an explicit session lifecycle covering setup validation, subject lock, plan/preview, ready, rehearsal, recording, review, subject lost and fault. Keep it distinct from the existing hardware execution state machine, with defined events between them and a single owner for transitions. Setup validation must not automatically recalibrate devices.

Require recording start/stop acknowledgement, actual media identity and timestamps; requested recording is not successful recording. Associate phone video, preview observations, plan revision, beat events and telemetry with one take ID. Review actual captured media against the accepted shot and return accept, retake same plan or replan with evidence and uncertainty. Implement unavailable recording controls honestly until a real adapter is connected.

Extend the existing local app with brief input, both camera roles, selected actor, confidence/age, current beat, concise correction, session status, preview, rehearsal, stop, recording state and review. Keep technical diagnostics in an expandable panel. Display camera-only, replay, simulation and qualified hardware modes clearly; never switch them silently.

## Build sequence and proof

Deliver vertical slices: (1) source map and contracts; (2) replayable perception/scene/beat loop with a real camera-only path; (3) asynchronous director tools and local coaching; (4) simulated arm-first corrections connected to the existing UI; (5) recording/review adapters and acknowledged state; (6) qualified hardware integration only when measured prerequisites permit it. Complete everything independent of missing devices or credentials, and state precisely what remains unverified. Do not fill missing integrations with success-shaped mocks in production.

Run `C:\TakeOne\scripts\TakeOne.ps1 -Command test` and add meaningful tests for identity crossing/loss, intentional exit, bad timestamps, cross-camera skew, incorrect/missing calibration, delayed AI results, conflicting revisions, invalid tools, network failure, recording acknowledgement failure and cue cancellation. Test jitter around beat thresholds, actor-relative left/right, no routine speech during recording, and light-only changes leaving the camera/cart plan unchanged.

Replay annotated clips containing correct performance, missed beats, pauses, occlusion and wrong-subject crossings. Separate synthetic, replay, actual camera, provider and hardware evidence. Report beat precision/recall, false corrections, identity switches and unknown coverage. Run at least a 10-minute local latency/queue stability test, including an injected slow provider. Local deadlines and bounded memory must remain observable when the AI is slow.

Provide working code and launchers, updated architecture/sequence diagrams, schemas, an operator guide, a capability matrix, recovery mapping, test/latency reports and a concise demonstrated-versus-blocked assessment. Preserve all existing physical blockers, including the failed assumed payload margin and missing calibration mapping. Never claim hardware readiness from simulated tests.

Start by inspecting the sources and current code, then implement the first vertical slice and continue through the authorized work. Optimize for clear ownership, measured responsiveness, accurate actor feedback and a working integrated product.
