# Arm language and geometry — 19 September 2026

## Update: general vector programs and full-path rehearsal

The active Live tool is now **`prepare_arm_motion`**, superseding the action
enumeration described in the historical sections below. The prior
`prepare_arm_adjustment` local endpoint remains compatible, but is not advertised
to the model. No phrase lookup, training run or prerecorded servo pose was added.

The model returns arbitrary signed translation and axis-angle rotation vectors,
an explicit frame, optional duration, and ordered segments. Simultaneous changes
share a segment. `planning/arm_program.py` resolves each segment against its
starting frame, reuses bounded IK, refines small-pose residuals, creates rest-to-rest
quintic joint curves, checks continuous joint derivatives/ranges, and replays
integer encoder conversion through FK at command instants and their midpoints.
The cart and nonselected arm remain fixed. A failed segment rejects the whole
program; an incomplete prefix is never executable. The starting pose is never
advanced merely because a preview succeeded.

Unspecified duration is proposed from the existing commissioning derivative
policy. An explicitly too-fast duration is rejected, not silently changed.
Numerical scope is finite (16 segments, 120 s total, vectors <=2 m / pi radians
per segment); those are planner-domain bounds, not measured safe travel.
Five joints cannot in general meet six exact pose constraints. The compiler
does not silently relax requested position/orientation or move another device.
Its sampled task-space checks are not a continuous collision proof.

The page at port 8769 now includes:

- A typed NLP test over real GPT-Live WebRTC, with no microphone. It explicitly
  uses a synthetic start. Ordinary voice still requires **Start conversation**.
- A path chart and time scrubber showing encoded FK positions and joint angles.
  This is an X-Z projection, not a live camera view or a 3D clearance proof.
- Explicit selection of a simulated start, or **Read arm encoders — no movement**.
  The latter runs the existing read-only inspection in the robot runtime under
  the shared device lock. It reads both arms, validates identity/calibration/mode,
  preserves torque/goals and stores a snapshot for offline planning. No automatic
  hardware read is available to NLP. A failed read has no simulated fallback.
- Session-bound pose/preview state. New intent invalidates the previous preview;
  close/expiry invalidates the context. A snapshot is not a feedback stream.

The generated `ArmProgramPlan` implements the existing `ArmRunner` contract.
An injected, lagging simulated arm successfully replays the exact curve through
that feedback controller, and an injected Stop interrupts it without automatic
torque release. **A physical arm execution owner/approval route is not connected
to this page.** No arm Run control was added. No physical arm was activated or
read during this development verification, and calibration flags are unchanged.
The selected-person camera source, measured image-to-arm relationship, clearance
review and supervised real-arm commissioning remain unfinished.

### New verification evidence

`data/arm-program-eval-20260919-02.json` records **20/20 real-model NLP cases**
using `gpt-5.6-terra`: numeric units, pan/tilt/roll signs, diagonal vectors,
simultaneous/sequential requests, correction, missing viewpoint, vague magnitude,
selected-person labels, Stop and arm-versus-cart routing. This is not a claim
that all language or movements work. Of these cases, ten produced accepted
sampled rehearsals, four numerical pose requests failed the geometric corridor,
three needed clarification, and three exercised non-arm routing. Both successful
and rejected paths are recorded. The first eval attempt (`...-01.json`) is an
incomplete artifact, not a passing report: it exposed a duplicate endpoint-time
bug. The program dispatch adapter now removes duplicate/near-duplicate endpoint
ticks; 299 floating-duration boundary cases cover the fix.

The real browser/WebRTC test for “Lower the camera arm two centimetres over two
seconds” produced a two-second trajectory with maximum sampled error **0.796 mm**,
aim **0.221 degrees**, and no hardware commands. Scrubbing showed predicted tool
height change from 1.4909 m to 1.4713 m. Those are model values, not measurements.
The voice session was explicitly ended after the test.

Focused verification: **80 Python tests passed**, including vector/path tests,
the legacy semantic tests, Live bridge, cart commissioning, visual servo and
embodied voice tests and read-only snapshot validation. Thirteen focused
JavaScript tests and the complete **383-test JavaScript suite** passed. Scoped
Ruff lint/format passed for all ten changed/new Python files.

The complete PowerShell repository launcher was attempted twice. The first was
stopped to fix the duplicate endpoint-time bug; the second was stopped after
concurrent edits to shared motion modules invalidated its provenance snapshot.
A focused run that overlapped those edits also failed the stale-source guard;
it is not counted as a pass. The final fresh-process focused run passed all 80
tests. **No full Python-suite pass is claimed.** This task's verification
workers were stopped; another task's independently running tests were left
untouched. The idle port-8769 bridge was restarted on the latest shared source.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_arm_program tests.test_arm_intent tests.test_live_robot tests.test_cart_nudge tests.test_visual_servo tests.test_embodied_voice_tools -q
.\.venv\Scripts\python.exe scripts/eval_arm_program.py --live --output data/arm-program-new.json
.\scripts\TakeOne.ps1 -Command test -VerificationOutputDirectory data/verification-arm-program-new
```

### Additional before/after mapping

- `voice/arm_program.py`: general vector schema/validation and Live instructions.
- `planning/arm_program.py`: explicit pose -> ordered timed joint paths -> sampled
  encoded FK; `ArmProgramPlan` adapts the existing feedback-controller contract.
- `voice/arm_rehearsal.py`: session-local pose selection and offline compilation.
- `motion/arm_snapshot.py`: explicit read-only encoder worker; existing inspection
  and shared ownership are reused, not replaced.
- `voice/live_robot.py`: advertises the vector tool while preserving the v1 endpoint.
- `scripts/gpt_live_director_test.py`: local origin/token-checked pose/review routes.
- `gpt-live-arm.js` and acceptance HTML/JS: rehearsal controls/chart; no arm actuation.
- `scripts/eval_arm_program.py`: current NLP/path evaluation; `eval_arm_language.py`
  explicitly preserves the historical v1 schema/instructions for reproducibility.
- `scripts/TakeOne.ps1`: optional verification-output directory, preserving the
  existing default while avoiding overwriting unrelated verification evidence.

## Historical first-stage implementation (superseded where noted above)

## What is implemented, and what is not

The GPT-Live acceptance page now has a `prepare_arm_adjustment` function and a
**Check arm language (no mic or movement)** button. Language is translated to
validated semantic operations, not joint counts. The local compiler supports
phone and light roles, six translations, pan/tilt/roll in both directions,
named-target aiming, and ordered compounds. It preserves explicit SI quantities;
unspecified amounts remain null in model output and become labelled *proposals*
of 2 cm or 5 degrees locally. Missing role, viewpoint or tilt direction requires
clarification. The preview envelope is 10 cm / 15 degrees per increment and
10 cm / 30 degrees total; these are software bounds, not measured safe ranges.

This is **not yet live arm control**. The page has no fresh arm feedback owner,
selected-person camera connection, trajectory approval, or arm Run route.
No arm port, torque, goal register, calibration or firmware was changed. The
existing cart-only Run button does not run arm intent; an arm request cancels
any pending cart review. It does not silently stop an already-running cart test.

The operator reported that the previous 0.5-second cart test moved forward.
Its report is `data/runs/voice-cart-fb496882bf498baa73c17050/report.json`: 38
completed writes, no controller fault, and physical observations still separate.
That one observation is not evidence for reverse, arbitrary travel or arm motion.

## Mathematical boundary

The local pipeline is:

```text
speech → GPT-Live delegation → typed semantic operations
       → explicit coordinate frames and selected subject
       → desired tool pose → existing bounded IK → integer encoder replay
       → [still required: trajectory, clearance, fresh feedback, operator approval]
       → [still required: supervised arm controller with stop/retained hold]
```

For a world-vertical lowering, `p* = p + [0, 0, -d]` and the optical orientation
is retained. A tilt changes orientation about the optical right axis without
requesting translation. Pan rotates about optical up, roll about optical forward.
The implementation uses Rodrigues rotations (`Rotation.from_rotvec`), not Euler
angle addition or an assumption that one camera operation equals one servo.
Optical coordinates are right +X, down +Y, forward +Z. Chassis forward is -X,
right +Y and up +Z. Horizontal directions without a viewpoint are ambiguous.

The existing five-joint `ArmSolver` minimizes weighted position and pointing
residuals under calibrated joint bounds, then improves roll and continuity.
An optional explicit right axis extends `ToolTarget`; existing targets without
it retain their original world-horizon preference. That enables optical-roll
requests and preserving the current roll when translating. A 5-DOF arm cannot
generally meet all six arbitrary pose constraints. Solver termination does not
mean the request is feasible.

`planning/arm_adjustment.py` takes an explicit caller-supplied model pose and
uses the existing FK, IK and calibration mapping. It never invents the actual
starting pose. It replays exact integer encoder conversion and checks the
achieved endpoint (position <= min(3 mm, 25% of requested nonzero translation),
aim <= 1 degree, roll <= 2 degrees). The cart and other arm remain fixed.
Intermediate geometric endpoints of a compound are retained, but intermediate
joint solutions, collision clearance and a continuous path are **not** validated.
This preview is never executable, even when its endpoint is feasible.

## “Face us”: selected person, not guessed coordinates

The operator chose selection in a live camera view. `voice/selected_aim.py`
accepts local typed perception and the locally selected transient track ID.
It reuses `VisualServoController` with range action fixed to hold. Its output
is the image error `e = [u_person - 0.5, v_person - 0.5]`, not servo angles or
3D distance. It rejects unselected/lost tracks, frame or track age above 250 ms,
future timestamps, confidence below 0.7 and an unrelated camera frame. It never
chooses another visible person after losing the selected one.

The cart-mounted webcam and the phone optical view are different coordinate
systems. A phone-arm aiming loop must use the phone's own view, or a measured
camera-to-robot transform with the required depth/geometry. A 2D box from the
cart webcam is not enough to infer camera-arm joint commands. The next integration
must connect local detection/selection and a measured image-to-joint control
relationship, with loss-of-target hold, to the supervised arm owner. Do not
send camera images to OpenAI merely to bypass this local geometry requirement.

## Verification and reproducibility

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_arm_intent tests.test_planning tests.test_live_robot tests.test_cart_nudge tests.test_visual_servo tests.test_embodied_voice_tools -q
.\.venv\Scripts\python.exe scripts/verify_arm_adjustments.py --output data/arm-sweep-new.json
# Paid text-only model evaluation; never dispatches any returned hardware tool:
.\.venv\Scripts\python.exe scripts/eval_arm_language.py --live --output data/arm-language-new.json
node --test apps/rehearsal/tests/*.test.mjs
```

The real gpt-5.6-terra evaluation passed 20/20 cases, including all translation/
rotation actions, compound requests, units, negation, correction, ambiguous
viewpoint, selected-person wording and arm-versus-cart routing. Exact model
calls/results and the instruction hash are in `data/arm-language-eval-20260919-01.json`.
This is one text evaluation, not a guarantee of every paraphrase or noisy audio.

The offline sweep exercised 72 endpoints: 12 actions × 2 arms × 3 synthetic
starting poses. It found 33 feasible and 39 infeasible endpoints, with no unhandled
failures. See `data/arm-geometry-sweep-20260919-01.json`. Rejection is expected
where requested task constraints cannot be met; it must not be converted to
success by silently moving the cart, changing the other arm or clipping a target.
All physical-movement and collision-qualification flags remain false.

The real GPT-Live WebRTC arm check also returned lower + tilt_unspecified +
face_target(us), disclosed the 2-cm proposal and asked “up or down, and by how much?”
It explicitly said nothing moved. No microphone or camera input was used; the
session was ended without physical execution.

All 374 JavaScript tests pass, including two new review-cancellation tests that
cover revoking a cart approval without dropping an active heartbeat owner.
Against settled source, 67 focused Python tests pass: `test_arm_intent`,
`test_planning.MotionIntentTests`, `test_live_robot`, `test_cart_nudge`,
`test_visual_servo` and `test_embodied_voice_tools`. Scoped Ruff lint/format and
both changed JavaScript modules' syntax checks pass.

An earlier Python run while source edits were still happening correctly failed
stale-source guards; it is not counted as a pass. The required full PowerShell
launcher was attempted but cancelled after the source changed under it. A later
run including the expensive complete default-shot PipelineTests was also
cancelled before completion. No full-suite/default-shot regression pass is
claimed. No verification or hardware worker was left running at handoff.

## Before/after mapping

- `voice/arm_intent.py`: new schema, semantic compiler and delegation instructions.
- `voice/live_robot.py`: adds only arm semantic preparation, not an arm execution tool.
- `planning/targets.py` / `kinematics.py`: optional explicit roll reference; default
  target behavior unchanged.
- `planning/arm_adjustment.py`: offline endpoint compiler; reuses the existing solver.
- `voice/selected_aim.py`: pure selected-person image objective above motor control.
- `gpt-live-test.html` / `.js`: non-actuating language check and explicit scope notice.
- `cart/nudge.py` / `gpt-live-nudge.js`: discard unrelated pending cart review on
  an arm request; retain the existing cart scheduler, heartbeat and execution gates.

The delegation design follows [OpenAI's GPT-Live tool documentation](https://developers.openai.com/api/docs/guides/live-delegation):
the application executes tools and enforces approvals; model output does not grant authority.
