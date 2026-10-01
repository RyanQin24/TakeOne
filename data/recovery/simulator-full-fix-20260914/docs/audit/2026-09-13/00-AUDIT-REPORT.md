# TakeOne read-only audit — 2026-09-13 (consolidated report)

Status of this document: **written while the audit was still in progress**, at the user's request, so that
what exists is delivered rather than lost. Every claim below carries its evidence path or is labelled a
hypothesis. Sections whose analyses did not finish say so explicitly (see §13 "What was not completed").
No source, config, calibration or run data was modified. All generated artefacts live under
`docs/audit/2026-09-13/evidence/`; scratch compiles were done in an external copy at
`C:\TakeOne-audit-20260913\` (Python 3.13.5 venv, mujoco 3.13.0, numpy 2.3.5, scipy 1.17.0 — `evidence/machine-spec.txt`).

Vocabulary preserved: checks are `pass` / `fail` / `unknown` / `conditional`; provenance is
`estimated` / `authored` / `verified` / `default` / `unresolved`.

---

## 0 · Executive findings (the ten that matter)

**Which simulator is which.** "The simulator" the user means is **Tree B**, `C:\TakeOne\TakeOne-main`
(`server.py` port 8767, `dist/app.js`, `takeone/planner.py`). Tree A's `apps/rehearsal` (port 8766) is a
separate, older rehearsal/motor-test app whose default page is a direct encoder-count test. The two are
confused throughout the docs. Tree B is **tracked in git** (its `tests/` were moved to root `tests/` in the
working tree — `git status` shows `D TakeOne-main/tests/*` and `?? tests/browser.mjs` etc.; blobs identical,
`evidence/treeB-tests-relocation.txt`), which broke Tree B's own `test_takeone.py` import of `fixtures`
(`evidence/treeB-unittest-test_takeone.txt`) and shadowed Tree A's `tests.fixtures` package
(`ModuleNotFoundError: 'tests.fixtures' is not a package`, `evidence/treeA-unittest-tests.txt`).

| # | Finding | Severity | Blocks demo? | Evidence |
|---|---|---|---|---|
| 1 | **Tree B has no knowledge of the arms' calibration.** Its joint limits are `rig_tall.xml` ranges; the robot's are encoder ranges in `calibration/originals/*.json` with 2° margins, plus axis signs and zero offsets. `servo_to_urdf_transform_verified` is `false` for both arms; wrist-roll `[0, 4095]` was **assigned, not observed**. Per-joint gap quantified in §2 (B5): XML is mostly *narrower* than calibrated, except `elbow_flex` (exceeds margin by ≤ 2°). | high | **yes** (mapping unverified) | `evidence/analysis-01-encoder-counts.md` §A; `configs/reference/previs_rig.json`; `calibration/derived/*.json` |
| 2 | **C2 consequence refuted on this plan, confirmed as a risk.** Converting all 650 take samples + transition samples of the reference export to counts under the *nominal* mapping (midpoint, signs, zero offsets from `calibration/derived`): **0 samples outside the calibrated ranges, 0 outside the 2° margin.** The XML ranges (±100° lift, ±95° wrist) are *narrower* than the calibrated spans (±103–107°) except `elbow_flex`, where XML ±96.8° exceeds the margin-reduced range by 1.3–2.0° on both arms. `shoulder_lift` is solved to ±99.4° — 1.8° inside the margin. The live danger is therefore the **unverified mapping** (sign/offset/transform), not the range widths: the 2° margin exists because a reviewed shot drove light `shoulder_lift` to its stop at 773 counts and the arm dropped (`calibration/derived/phone.json`). | high | yes (until the mapping is verified) | `evidence/analysis-01-encoder-counts.md` §A, §B "ALL" table |
| 3 | **The reference plan is not a passing plan.** Recompiled locally: 6 of 9 takes `fail`, 3 `unknown`; 7 of 8 repositions `fail` (durations, some saturating the 120 s search). Overall status `fail`. Every headline number in the Tree B README is taken from a failing plan. | high | yes (as a demo claim) | `evidence/analysis-tb-compile-run1.txt`; `evidence/analysis-04b-reference-vs-recompile.txt` |
| 4 | **Rehearsal is 21.5× the filmed source (393.7 s for 18.27 s) and ~4.4× of that is the governor's global bound, not the robot.** Same paths, same velocity+acceleration limits under time-optimal parameterisation: 89 s (ratio 4.41); with one jerk ramp per acceleration reversal added conservatively: 193 s (ratio 2.04). In-place rotations are 7–10× over-timed. | high | yes (usability) | `evidence/analysis-02-governor-vs-topp.md` |
| 5 | **Torque: the 0.800 N·m allowance has no source, and the light arm exceeds its *rated* torque on gravity alone.** STS3215 spec (not measured): 12 V variant rated 0.98 / stall 2.94 N·m; 7.4 V variant at 6 V rated 0.39 / stall 1.62 N·m. Commissioning log: phone bus 11.9–12.6 V, light bus **4.9–5.8 V on a 5 V supply**. Light-arm gravity demand 0.73–0.85 N·m > 0.39 N·m rated on every take. Build/supply finding, not a planning one. | high | yes (hardware) | `evidence/analysis-06-07-envelopes.md` §C6; `docs/robot-commissioning.md` L68 |
| 6 | **The simulator is not this robot.** Mount 1.20 m (Tree B) vs 1.23 m measured; arm mount yaw 0 vs +90°; track 0.34 vs 0.58 m; wheelbase 0.32 vs 0.59 m; footprint, mass, casters assumed; wheels have `contype=0` (**cannot collide with anything**). | high | partially | §2 table; `TakeOne-main/rig_tall.xml`; `TakeOne-main/takeone/scene.py`; `configs/rig.json` |
| 7 | **The perception/scene branch of the product does not exist.** Director WPs 03, 04, 06, 07 are `planned`; `SceneSpec` is a flat studio (floor z=0, boxes, one actor cylinder); "the step is 17 cm" cannot be expressed. Scenario→scene→shot is the unbuilt function. | high | yes for the scene set piece | `docs/ai-director/work-packages.json`; `TakeOne-main/takeone/scene.py` |
| 8 | **The cart cannot follow a walker, let alone a runner.** Qualified envelope: command ≤ 0.05 for ≤ 4 s, equal commands only (straight line), ≈ 0.17 m/s provisional, ≈ 0.69 m net displacement. A 3 m/s jog is 21.8× the only measured sample, 12× the simulator's assumed 0.25 m/s. Response tables empty; drift reported. | high | yes for the tracking set piece as imagined | `evidence/analysis-06-07-envelopes.md` §7; `configs/cart-*.json` |
| 9 | **Tracking a runner is possible only by pan from a standing cart at ≥ 1.25·v metres.** Velocity binds at every speed: 3 m/s → 3.75 m; 5 m/s → 6.25 m, outside the 6.0 m clamp. Vertical (stairs) is easy; stride bob must not be tracked. | medium | design rule | `evidence/analysis-06-07-envelopes.md` §6 |
| 10 | **Nothing needs training for the edit.** `timeline.py` already is an EDL (segments with `take/reposition/excluded/unresolved`, coverage invariant). Editor = media binding + deterministic assembly + FFmpeg + optional LLM ranking. **The fallback edit costs nothing and always exists.** | positive | no | `TakeOne-main/takeone/timeline.py`; §7 |

Also material: plan artefacts are **numerically deterministic** across processes but **not byte-identical**
because `compile_seconds` (wall clock) is stored inside the plan (`evidence/analysis-04-determinism.md`);
across machines the recompile differs by ≤ 0.0024° in q and 0.01 s in one take (Linux → Windows,
`evidence/analysis-04b-reference-vs-recompile.txt`). Exports embed an absolute Linux path
(`/home/claude/work/rehearsal-mvp/rig_tall.xml`) so they do **not** recompile elsewhere without an override.

---

## 1 · Source-of-truth map (A1–A6)

### A1 · Subsystem ownership

| Subsystem | Tree A (`packages/takeone`) | Tree B (`TakeOne-main/takeone`) | Authoritative today | Recommend | Cost of duplication |
|---|---|---|---|---|---|
| Robot kinematic model | `simulation/model.py` builds MuJoCo from `configs/rig.json` (mount 1.23, yaw 90); `simulation/robot.py:29–37` **overwrites `jnt_range`/`ctrlrange` with `ArmMapping.safe_ranges_rad`** (overrides applied to a deep copy of hash-gated originals, 2° margin per side, mapping pinned to `rig_5dof.xml` sha); IK adds a 0.5° inset (`kinematics.py:96–106`); `motion/limits.py:85–92` re-encodes every sample; `play.py:62–72` clamps to full calibration at dispatch and counts clamps | `robot.py` loads `rig_tall.xml` (mount 1.20, yaw 0, XML limits − 0.6°) | **Tree A for geometry and limits**; Tree B for nothing physical | Tree B must load a `RigSpec` derived from `configs/rig.json` + `calibration/` | Two robots; every Tree B pose is on the wrong machine (§2) |
| Scene model | `configs/scene.json` (actor 1.72 m, envelope 0.36 m) — consumed by Tree A previs only | `scene.py` `SceneSpec` (studio, boxes, actor cylinder 0.32 m), render/collision unified | Tree B (only real scene object) | Extend Tree B's `SceneSpec` → v2 (§5) | Two actor envelopes (0.32 vs 0.36 m) |
| Collision checking | `planning/envelope.py` (envelope-level) | `collision.py` swept clearance + `_structural` | Tree B | Keep Tree B; add wheels (`contype`), calibrated limits | — |
| Trajectory timing | `planning/trajectory.py`, `curve.py` | `timing.py` PhaseGovernor + JS port `dist/governor.js` (agreement test) | Tree B (has the tested governor) | Keep governor for playback; replace **duration bound** with per-axis TOPP (§3 C7) | — |
| IK | `planning/kinematics.py` (bounded, calibrated ranges + 0.5° inset) | `planner.ArmSolver` (hierarchical LSQ, XML limits − 0.6°) | Tree A for limits; Tree B for solver quality | Tree B solver over Tree A limit model | Two answers for the same goal (C13, not completed) |
| Cart drive model | `cart/plan.py`, `cart/runtime.py` (20 ms dispatch, watchdog), `simulation/drive.py` | `drive.py` (4 topologies, assumed limits) | Tree A (has the real transport, `wire_polarity`, measured 0.1375 m/s sample) | Tree B `DriveModel` must be built from `configs/rig.json` + `cart-runtime.json` | 0.34 vs 0.58 m track etc. |
| Shot / timeline | `planning/settings.py` `ShotSettings` (single shot) | `timeline.py` + `intent.py` (EDL with coverage invariant) | **Tree B** | Adopt Tree B as the product timeline | — |
| Video analysis | — | `video/`, `estimate.py` | Tree B only | Keep | — |
| Web UI | `apps/rehearsal/dist` (authored, must not be deleted) | `dist/app.js`, `governor.js` | Tree B for the studio; Tree A dist retained as motor-test tool | Keep both; label clearly | Two servers (8766/8767) |
| Device execution | `motion/*`, `execution.py`, `adapters/*`, `cart/runtime.py` | none (`hardwareReady=false` always) | **Tree A only** | Tree B exports → Tree A executes | — |
| Director session/state | `director/*` (SQLite repo, provider, skills) | none | Tree A only | Keep | — |
| Voice | `voice/*` | none | Tree A only | Keep | — |

**Decision:** Tree B is authoritative for *rehearsal* (scene, timeline, collision, governor, UI); Tree A is
authoritative for *what the robot is* (rig geometry, calibration, limits, transport, execution). The
migration direction is: Tree B consumes a `RigSpec`/`JointLimitModel` produced from Tree A's configs and
calibration; Tree A's `planning/*` single-shot compiler is **superseded** by Tree B's planner once it runs on
Tree A's limits. What is dropped: Tree B's `rig_tall.xml` constants, `DriveModel.for_topology` defaults,
`engine.py` (already self-declared SUPERSEDED), and Tree A's `configs/reference/previs_rig.json` (demoted to
historical).

### A2 · `TakeOne-main` placement
Tracked in git at the repository root (violates `AGENTS.md`: product code belongs in `packages/takeone`).
Its `tests/` were moved to root `tests/` in the working tree, breaking both suites (above). Recommended
target: `packages/takeone/rehearsal/` (Python) + `apps/studio/` (server + dist) with a before/after mapping;
breaks: `server.py` `ROOT`-relative paths, `robot.py` `DEFAULT_MODEL = ROOT / "rig_tall.xml"`,
`scene.py` scratch file `.scene_compiled.xml` written next to the model, `tests/browser.mjs` (`python3`,
Linux paths), README launch instructions, `runtime/reference-export.json` absolute path. Cost ≈ 1 day plus
a full re-run of 78 + 12 + 27 checks.

### A3 · Absolute paths
`configs/**`, `scripts/*`, `packages/**` contain **no** absolute paths (roots derive from `__file__` /
`$PSScriptRoot` / `TAKEONE_ROOT`) — portable. **Stale** (`C:\Users\nonst\…\TakeOne`): `README.md:19`;
`calibration/registry.json:24,41,87,98` (`observed_maximum_revisions.evidence`); `calibration/derived/phone.json:39`,
`light.json:42` (`endpoint_learning.report`); `docs/robot-motion-execution.md:47`, `robot-commissioning.md:10,40`,
`arm-commissioning.md:30,75,109`, `cart-live-testing.md:56`. **Provenance** (keep): `/home/takeone/.cache/…`
`remote_path`s, `\\wsl.localhost\…` `recovered_from`, `calibration/evidence/calibration_audit.json` (byte-compared
by `check_integrity.py:76–78`, never edit). Tree B export `robot_model_path=/home/claude/work/rehearsal-mvp/rig_tall.xml`
breaks recompilation (confirmed; overridden in `evidence/analysis-tb-compile.py`).
**Does the hash-checked chain resolve them?** No code dereferences the stale strings: `ArmMapping.load`,
`measured_limits` and `preflight` resolve only workspace-relative, hash-gated paths (`calibration.py:75–80`,
`motion/limits.py:141–143, 221–223`), and the referenced `data/commissioning/…-maxima-*/` folders exist under
`C:\TakeOne`. But the strings are hashed into plan identity by `config.py:81–93` `provenance()`, so correcting
them **invalidates every prepared plan**; and a future `observed_maxima` run appends correct-root paths, leaving
mixed-root history. `check_integrity.py` passed (1086 files) and does not cover these fields.

### A4 · Data hygiene (`evidence/analysis-05-archives-and-data.md`)
**Archive duplication confirmed by hash:** `archive/imports/TakeOne-main.zip` and
`archive/restore-verification/TakeOne-main.zip` are both 18,051,572 bytes, sha256
`4c7bc50a…9dc4d`; `lerobot-upload.tar.gz` twice at 6,537,938 bytes, sha256 `e1a02b3d…f637b71`.
`TakeOne-main/` is tracked (79 files, commits `f928842`, `6036010`), not in `.gitignore`, and its content is
also expanded a third time under `archive/restore-verification/TakeOne-main/`.
**`data/` = 303.4 MB in 945 files:** `runs/` 109.3 MB (361 files; seven ~4.5 MB `plan.json` from the same
night), `verification/` 47.2 MB (of which `photo-export-payloads.json` 39.7 MB), `commissioning/` 44.3 MB
(ten near-identical 2.55–2.56 MB `plan-before.json`), `checked-plans/` 39.3 MB (54 files), `recovery/` 20.5 MB
(three ~4.8 MB GLBs duplicated from `apps/rehearsal/dist/models`). The four `cart-plan-4s-*.json` are 35,822
bytes each with **different** hashes (real variants, not copies). Genuine evidence under the provenance rules:
one `plan-before` per commissioning session, the hardware `report.json`s, the photo evidence. Repeated
exports: the sibling `plan.json`s and the recovery GLBs. Recommendation independent of the totals: keep
`calibration/originals` byte-for-byte; keep one hashed `checked-plan` per plan revision and one
`real-robot-review` per hardware session; treat `cart-plan-4s-*` variants and
`photo-export-payloads.json` (41.6 MB) as regenerable exports to be listed in a retention manifest, not
deleted by this audit.

### A5 · Test-claim audit (what ran)
- Tree A `tests/`: **307 tests, 4 failures, 3 errors** (`evidence/treeA-unittest-tests.txt`). Errors:
  `test_motion_contract_v2`, `test_robot_motion` (import shadowing by Tree B's relocated `fixtures.py`);
  `evaluate_plan() missing 'mappings' and 'dispatch_period_s'` (test stale vs code — real drift). Failures in
  `test_planning` (`34 != 162` solves; `1200 != 120`) show the planner changed under its tests.
- Tree A `tests/simulation`: **29 tests, 5 failures, 1 error** — `shoulder_lift: outside configured operating
  range`, camera height off by 0.0203 m vs 0.02 tolerance, drive quaternion `-4.28 != 0`
  (`evidence/treeA-unittest-simulation.txt`). The simulation regression suite does not pass at HEAD.
- Tree B: **78 tests, 1 failure** (`test_zoom_direction_is_recovered_and_flagged_ambiguous`, ffmpeg
  `moov atom not found` — fixture/codec environment), **12/12 JS**, **27/27 browser** (only after
  restoring `tests/fixtures.py` and shimming `python3` in an external copy).
- Claims with tests: FK 1e-9, Jacobian 5e-6, governor Py/JS 1e-9 over the recorded trace (independent
  expectation: MuJoCo FK vs closed form; finite differences; a stored trace — the trace is generated by the
  Python code, so JS-vs-Python agreement is independent but Python-vs-physics is not).
- **Claims no test establishes:** that any pose is reachable by *the calibrated* arm; that repositions are
  drivable by *this* cart; that torque verdicts relate to *this* motor at *this* voltage; that the wheels clear
  anything; that the camera-height clamp is visible to the operator; that exports recompile on another machine.

### A6 · Director reality
`docs/ai-director/work-packages.json`: 01 complete; 02, 05 blocked/in progress; **03, 04, 06, 07 `planned`**.
Code confirms: `director/` has the session state machine + SQLite (`service.py`, `repository.py`), creative
planner and Responses provider (`gpt-5.6-terra` pinned, `enabled: false` by default, live acceptance
unverified — `implementation/02-creative-planning.md:62`), and a partial offline voice slice. Ordinary sessions
reject every action except `revise_brief`/`cancel` with "not connected" (`service.py:198–201`); the full
brief→record→review→edit machine is traversable only in `DEMONSTRATION` mode with fixtures stamped
`real_media_verified: false` (`service.py:349`). `capabilities.py:62–65` hardcodes actor tracking/voice and
robot execution as `not_integrated`. Grep of `packages/` for `perception|detector|allocation|base_yaw|
SceneSpec|cv2|mediapipe|ffmpeg|fcpxml|EDL`: **zero matches**. The arm-first / deadband / no-chase-jitter tracking
policy exists only as text (`docs/requests/ASTRA-AI-DIRECTOR-PROMPT.md:85, 95`; `ai-director-build-plan:96,135`).
`lerobot/HackTheNorth_AI_Director_Final_Documentation.md` describes `MotionAllocator`, `FeasibilityResult`,
`inspect_scene/plan_shot/execute_shot` in the present tense — none exist. The perception and scene branch of
the product does not exist.

---

## 2 · Parameter reconciliation (B)

| Quantity | `configs/rig.json` | `configs/reference/previs_rig.json` | Tree B (`rig_tall.xml` / code) | `configs/scene.json` | Provenance | Verdict |
|---|---|---|---|---|---|---|
| Arm mount height | **1.23 m** | 1.00 m (`base_xyz_m` z) | 1.20 m | — | rig.json: user measured 2026-09-12 | 1.23 m is real; previs 1.00 historical; Tree B wrong by 30 mm |
| Arm lateral offset | ±0.23 m | ±0.24 m | from XML | — | rig.json user measured | 0.23 |
| Arm mount yaw | +90° | 0 rad | 0 | — | photo correction 2026-09-12 | +90°; Tree B and previs wrong |
| Max extended height | 1.80 m | — | 1.697 m | — | user measured | measured 1.80 |
| Horizontal extension | 0.34 m | — | 0.535 bound / 0.517 sampled | — | user measured at one pose vs sampled envelope | different quantities; Tree B workspace is larger than any *measured* reach — every reachability verdict is `conditional`, not `pass` |
| Cart track | 0.58 m ("estimate") | — | 0.34 m default | — | estimate vs assumed | neither measured; 1.71× ratio (B3) |
| Wheelbase | axle −0.27 / caster +0.32 ⇒ 0.59 m | null | 0.32 m | — | estimated | Tree B wrong |
| Drive topology | powered front wheels, rear casters | unmeasured | UNKNOWN→DIFFERENTIAL | — | user confirmed | differential-with-casters |
| Footprint | — | 0.65×0.68×0.8 | 0.46×0.38 | — | assumed | unresolved |
| Cart mass | — | — | 5.806 kg | — | assumed | unresolved |
| Actor envelope radius | — | — | 0.32 m | 0.36 m at 1.72 m | authored | pick one (0.36 conservative) |
| Actor height | — | — | 1.72 | 1.72 (env 1.76) | default | ok |
| Joint torque allowance | — | — | 0.800 N·m | — | **no source** | replace with spec figures per arm and voltage (§3 C6) |
| Arm velocity / accel | — | — | 0.80 / 1.80 | `arm-execution.json` 0.80 / 1.80 | policy | agree |
| **Arm jerk** | — | — | **12.0** | **20.0** (`arm-execution.json`) | policy | disagree ×1.67; pick one, label policy |
| Cart speed | 0.1375 m/s at cmd 0.04 (provisional) | — | 0.25 m/s assumed | — | one observation | see §6 |
| Cart command cap | 0.15; supervised 0.05 ≤ 4 s | — | — | — | policy | — |
| Yaw ceiling | — | — | 0.6 rad/s assumed | — | assumed | drives 7–10× over-timed rotations |

**B1.** 1.23 m is real (measured). Correcting Tree B raises every optical pose by 30 mm, moves the
camera-height band from [0.84, 1.56] to [0.87, 1.59] m at `reach_fraction` 0.70, and changes
gravity torque negligibly; it changes structural clearance (C5) not at all unless the riser is modelled.
**B2.** 0.34 m is a measured horizontal extension at one (unrecorded) pose; 0.517 m is the sampled reach of the
XML model over its joint ranges. Different quantities; they cannot be reconciled without a recorded pose for
the 0.34 m. On joint *ranges* the XML model is mostly narrower than the calibrated arm (B5), so the joint-limit
argument does **not** show a larger simulated workspace; link lengths in `rig_tall.xml` are nominal SO-101 and
unverified against this build. Reachability verdicts are therefore `conditional`, not `pass` and not void.
**B3.** Track 0.58 vs 0.34: yaw rate per wheel-speed difference is 1.71× lower on the real cart. Rotation
phase *durations* are set by the yaw ceiling, so unchanged; wheel-speed screens are computed on the wrong
geometry; the tipping screen uses the assumed footprint, not the track (`evidence/analysis-06-07-envelopes.md` B3).
**B4.** Confirmed in code: `reverse_enabled` → `simulation/drive.py:21` `DIRECTION_SIGN`, which flips the
planned reference path, orbit angle, yaw rate, arm tracking programs (`planning/compiler.py:51`), the
commissioning envelope (`cart/runtime.py:115–126`) and wire signs together. `wire_polarity` is applied once at
packet formatting (`adapters/uart.py:62–70`, negative zero collapsed). **Latent defect:** `wire_polarity` is
passed only by the `Run-Robot.ps1 → motion/play.py` route (`play.py:370, 411–417`); `cart/cli.py:44`,
`motion/devices.py:21–26` (the `execution.py` `DeviceFactory`) and `motion/direct.py:163–168` construct
`MotorUART` with default polarity `+1`, so the same cart receives **opposite‑signed packets** on two of three
live entry points. Rename `reverse_enabled` → `path_reversed`; thread `wire_polarity` through `DeviceFactory`.
`drive_forward_sign` (−1) is a frame convention only (`config.py:48–54`).

**B5 — XML limits vs calibrated limits (degrees, model frame; `evidence/analysis-01-encoder-counts.md` §A).**
`servo_to_urdf_transform_verified` is `false` in both arms. The wrist-roll range `[0, 4095]` was
**assigned, not observed** as unobstructed rotation. Raw ranges: phone `[759,3482] [813,3161] [883,3085→3092] [862,3175] [0,4095]`;
light `[758,3481] [773,3198] [882,3096] [875,3199→3204] [0,4095]`; mapping `q = (raw − mid)·360/4095`, axis signs and
zero offsets from `calibration/derived/*.json`, 2.0° margin each end. Per-joint (degrees, model frame, from
`evidence/analysis-01-encoder-counts.md` §A): `shoulder_pan` XML ±110 vs calibrated ±119.7 (XML narrower by
9.7°); `shoulder_lift` XML ±100 vs cam ±103.2 / light ±106.6 (narrower by 3.2 / 6.6°; only 1.2 / 4.6° inside
the margin); `elbow_flex` XML ±96.83 vs cam [−96.84, 97.36] / light [−97.32, 97.49] — **XML exceeds the 2° margin
by 1.99/1.47° (cam) and 1.51/1.34° (light)**; `wrist_flex` XML ±95 vs ±101.7 / ±102.4 (narrower); `wrist_roll`
XML [−157.2, 162.8] vs assigned ±180 (narrower, but the ±180 was never observed). So on range *widths* the
simulator is mostly conservative; what it does not understand is *where zero is and which way is positive* —
`servo_to_urdf_transform_verified: false` — which is exactly what put light `shoulder_lift` on its stop before.

---

## 3 · Simulator correctness (C1–C14)

| Item | Verdict | Evidence / reproduction | Smallest correct fix |
|---|---|---|---|
| C1 not this robot | **confirmed** | §2 table; `rig_tall.xml`; `drive.py` defaults | Load `RigSpec` from `configs/rig.json`; fail compile if any constant is `default` |
| C2 URDF limits | **mechanism confirmed, consequence refuted on this plan**: 0 of 650 take samples (and 0 transition samples) outside calibrated counts or the 2° margin under the nominal mapping; XML exceeds the margin only on `elbow_flex` (≤ 2.0°), which no reference sample reaches. Verdict is `conditional` because the mapping itself is unverified | run `evidence/analysis-01-encoder-counts.py` → §B "ALL" | `robot.joint_limits` ← `ArmMapping.safe_ranges_rad` (Tree A `calibration.py`) with the 2° margin; while `servo_to_urdf_transform_verified` is false every arm check is `conditional`, never `pass` |
| C3 roll | **confirmed** by code reading: `intent.CAMERA_MOVES` includes `ROLL`; `camera_track` writes `roll`; 5-DOF solver treats roll as lowest-priority residual; achieved roll not per-frame in UI | `intent.py`, `planner.ArmSolver` | Show requested vs achieved roll per frame; mark shot `conditional`; or remove `ROLL` |
| C4 self-collision | **untestable without instrumentation**: restarts are deterministic (seeded from goal; determinism proven in analysis 4) but fraction spent escaping penetration needs a counter in `ArmSolver.solve` | `evidence/analysis-04-determinism.md` | Add restart-reason counters to the solver report (experiment, not run) |
| C5 mounts vs deck | confirmed in Tree B README and `collision._structural`; `dist/app.js` renders `structural` — surfaced | `TakeOne-main/README.md`; `app.js` | Model the real 1.23 m platform; riser ≥ 4 mm clears 16.2→20 mm at neutral (hypothesis: geometry-dependent) |
| C6 torque | **confirmed and worse**: 0.800 unsourced; light arm gravity > 6 V rated (0.39 N·m); 3/9 takes change verdict vs rated, 4/9 vs stall; Shot 6 pan 15.3 N·m, Shot 4 tilt 4.9 N·m = joints pinned at stops | `evidence/analysis-06-07-envelopes.md` §C6 | Per-arm allowance from spec at measured bus voltage, labelled `spec, not measured`; light supply is a build blocker |
| C7 21.5× slow | **confirmed**: governor 393.7 s vs TOPP(v+a) 89.2 s (×4.41), TOPP+jerk ramps 192.8 s (×2.04); rotations 7–10× over-timed | `evidence/analysis-02-governor-vs-topp.md` | Replace `minimum_duration`'s global bound with per-axis TOPP (or TOPP-RA) feeding the same PhaseGovernor |
| C8 cart placement geometric | **confirmed** by reading `cart_from_goals`; wheels `contype=0` in `scene.py`/XML → **wheels cannot collide with anything** | `planner.py` `cart_from_goals`; `scene.py` | Add `drivable_region` test in `cart_from_goals`; give wheels collision geoms |
| C9 height band | **confirmed**: at 0.70 from 1.20 m → [0.83, 1.57]; UI offers to 2.0 m; measured 1.80 m; 0.70 is a **choice**, not a workspace fact; clamp note is in `take.cart.notes` which `app.js` does **not** render | `evidence/analysis-06-07-envelopes.md` §C9; `app.js` renders `s.notes` only | Render `take.cart.notes`; make `reach_fraction` a visible `RigSpec` field |
| C10 double clamp | **confirmed** (`intent.camera_track` and `planner.sample_goals` both clamp) | code | One clamp at intent parse recording requested vs applied |
| C11 actor | **confirmed**: 3 DOF cylinder, no gait/eyeline/support/collision; `LOOK_UP/DOWN` parsed, `models_head_pitch=False` | `scene.py`, `intent.py` | Gait model + walkable graph (§5) |
| C12 time inversion | phase trace monotone by construction; fallback to uniform grid exists in `plan_reposition` (L1101–1102) and `compile_take`; frequency **not measured** (needs a counter) | `planner.py` L1100–1102 | Log fallback events into the plan |
| C13 two planners | **not completed** (see §13) | — | — |
| C14 determinism | **numerically deterministic** across 3 processes; plan bytes differ only by `compile_seconds`; cross-machine drift ≤ 0.0024°, 0.01 s | `evidence/analysis-04-determinism.md`, `04b` | Move `compile_seconds` out of the hashed artefact |

---

## 4 · Telemetry contract (D)

**D1 hard-coded constants (file → value → provenance):** `planner.PlanOptions` `reach_fraction 0.70`,
`parked_path_length_m 0.15`, `samples_per_second 5.0`, `collision_samples 48`, `rehearsal_camera_hfov_deg 49.6`;
`planner` `POSITION_TOLERANCE_M 0.015`, `ORIENTATION_TOLERANCE_RAD 1.5°`, `JOINT_LIMIT_MARGIN_RAD 0.6°`;
`drive.DriveModel.for_topology` `wheelbase 0.32`, `track 0.34`; `DriveLimits.max_speed_mps 0.25`
(`ASSUMED_placeholder`); `timing.MotionLimits` (0.8/1.8/12, 0.25/0.35/1.5, 0.6/1.2/6), `GovernorLimits`,
`MIN_TRAVERSE_S 0.25`; `dynamics.LoadModel` 0.80 N·m, 0.30 kg; `intent.DEFAULT_AMOUNT`; clamps ±0.85,
[0.6, 6.0] m, [0.4, 2.2] m; `timeline.MIN_SEGMENT_S 0.10`; `rig_tall.xml` every dimension. All `default`.
Recommend one versioned `RigSpec`/`SceneSpec`/`ShotSpec` load path, hashed by extending `project.settings_hash`,
with a recompile diff report.

**D2 per-frame schema (table form; JSON Schema to be emitted from this table):**

| Group | Fields | Computable today |
|---|---|---|
| clocks | `t_source_s`, `t_rehearsal_s`, `block_index`, `block_kind` ∈ {take, reposition, excluded, unresolved}, `s`, `s_dot`, `s_ddot`, `s_dddot`, `governor_state` | yes (governor) |
| joints[10] | `name`, `q_rad`, `q_deg`, `count` (documented mapping), `count_rate`, `pct_of_calibrated_range`, `dist_to_lo_deg`, `dist_to_hi_deg`, `dist_to_margin_deg`, `vel/acc/jerk` + ceilings, `torque_nm`, `torque_gravity_nm`, `torque_allowance` + provenance | yes once calibration is loaded (C2) |
| arms[2] | tool pose W, optical pose, `reach_used/reach_bound`, singularity margin (min σ of J), self-collision slack, cross-arm slack, IK residual, `roll_requested/roll_achieved` | mostly yes |
| cart | `x,y,yaw`, `v`, `omega`, drive-reference pose, centre pose, two-decimal wheel commands (UART), per-wheel speed, `watchdog_margin_s` vs 0.06, nonholonomic residual | yes except commands (needs `cart/plan.py` response map, which is empty → `unknown`) |
| camera | optical pose, intrinsics/FOV, horizon roll, subject `(u,v)`, distance, headroom, lead room, `subject_in_frame` | yes |
| light | optical pose, key angle, distance, policy achieved vs intended (note ≤ 12° at 2 m, < 5° at 3.75 m; 35° key needs a stand) | yes |
| human | `x,y,facing`, height, radii, speed, `support_surface` + height, beat expected vs simulated, visibility, occlusion, distances, `unmodelled: [head_pitch, gaze, limbs, gait]` | partial; support/occlusion need §5 |
| checks[] | `name`, `status`, `value`, `limit`, `limit_provenance`, `missing_parameter` when `unknown` | yes |
| **`binding_constraint`** | which single limit determines motion now (joint velocity/jerk, yaw rate, clearance, reach, none) | yes — the governor already computes the per-axis ratios |

Delivery: data panel in `dist/`, scrubber reading every field at any `t`, JSON + CSV export; provenance and
status travel with every number per `CONVENTIONS.md`.

---

## 5 · Scene grounding decision (E)

Gap stated exactly: scenario → metric, gravity-aligned, semantically labelled scene + blocking plan + shot plan
does not exist. `SceneSpec` cannot hold a surface at z ≠ 0. What survives: the subject-relative shot grammar.

Tiers: **Tier 1 authored parametric templates** (`street`, `steps`, `doorway` with typed dimensions;
provenance `authored`→`verified`) — data-model change + template library + UI form; **the only tier whose risk
is boundable this week: ~3 days.** Tier 2 measured capture (RoomPlan/ARKit if the phone has LiDAR — **not
verified which phone is on the cart**; otherwise multi-view + ArUco anchor via `cv2.aruco`) — 5+ days, device
dependent. Tier 3 generated (twirl OpenSCAD — parametric, maps onto Tier 1; vibe-draw glTF — **AGPL-3.0**,
metrically empty, look-dev only). Rule: a plan against `generated` geometry is `conditional`, never `pass`.

`SceneSpec` v2: `ground` (support surfaces with height/normal/friction `unknown`), `elements` (provenance,
uncertainty, anchor), `anchors`, `semantics` (`floor/step/kerb/wall/prop/hazard/standable/drivable/not_drivable`),
`drivable_region` (from 0.19 m wheels, 0.047 m casters; climbability rule *assumed*: no step > 0.02 m for
casters — **a cart on these wheels cannot follow an actor down steps**), `walkable_graph`. Invariant: rendered
world == collision world (extend `scene.py`).

Blocking solver (E4): actor path on the walkable graph with a parametric gait; cart stations inside the drivable
region; timing; output feasible or **named refusal** in `planner._revisions` form.

**Recommendation: Tier 1 for the demo, twirl-as-template-source as the stretch, Tier 2 post-demo.**

---

## 6 · Tracking envelope (F) — numbers

Algebra verified numerically (peak ω = v/d; peak ω̇ = 0.6495 v²/d²; peak ω̈ = 2v³/d³;
`evidence/analysis-06-07-envelopes.md`). With ω_max 0.80, α_max 1.80 (policy, not measured):

| v (m/s) | d_vel | d_acc | d_jerk (J=12 / 20) | binding | required standoff | 6.0 m clamp |
|---|---|---|---|---|---|---|
| 1 | 1.25 | 0.60 | 0.55 / 0.46 | velocity | **1.25 m** | inside |
| 2 | 2.50 | 1.20 | 1.10 / 0.93 | velocity | **2.50 m** | inside |
| 3 | 3.75 | 1.80 | 1.65 / 1.39 | velocity | **3.75 m** | inside |
| 5 | 6.25 | 3.00 | 2.75 / 2.32 | velocity | **6.25 m** | **exceeds** |

Design rule the simulator should emit: **stand off ≥ v / ω_max = 1.25·v.** Vertical: descending 0.17 m
steps at 2/s is 0.34 m/s → 0.11–0.19 rad/s tilt, well inside ceilings; stride bob (±0.05 m at 2.7 Hz) would
demand 40–135 rad/s³ of tilt jerk — it must be *filtered*, not tracked (headroom + deadband). Cart: qualified
envelope ≈ 0.17 m/s for ≤ 4 s straight (≈ 0.69 m); 3 m/s is 21.8× the measured sample, 5.8× the unevidenced
0.52 m/s extrapolation, 12× the assumed 0.25. **A cart limited to equal commands in a straight line for a few
seconds cannot follow a running human, and no software changes that.** Supported walking speed inside the
qualified envelope: 0.17 m/s — slower than any walk.

Ranking for the demo: (1) subject runs **past a standing cart**, pan only, at ≥ 1.25·v — feasible; (2) short
rehearsed path ≤ 0.69 m net — feasible; (3) toward/away from lens — easiest; (4) follow a walker — **not inside
the qualified envelope**; (5) follow a runner — not available. Light: key angle < 12° at 2 m, < 5° at 3.75 m,
irradiance 28 % at 3.75 m vs 2 m — on-axis and weak; staging finding.

Simulator must gain: `TrackingShot` intent, pre-shot feasibility curve, actuator allocation (prefer arm,
penalise base yaw, deadbands — specified in `docs/requests/ASTRA-AI-DIRECTOR-PROMPT.md`, **nothing implements
it**), tracking telemetry fields, simultaneous two-arm check, named refusal ("at 3.0 m/s this shot needs 3.75 m;
1.8 m cannot hold framing").

---

## 7 · Edit architecture (G)

**Nothing needs to be trained.** Runway Aleph 2.0 and Seedance 2.0 synthesise pixels; OpenChatCut and
autoclip use pretrained LLMs to *decide* and FFmpeg to *cut*; none trains anything. TakeOne is stronger than
all four: `TakeOne-main/takeone/timeline.py` **already is an EDL** — segments with `t0_s`/`t1_s`, kind
`take/reposition/excluded/unresolved`, `included`, per-key provenance, a coverage invariant enforced on every
operation, `schedule()`/`source_to_rehearsal()`; `ShotIntent` records purpose; `configs/reference/recording.json`
names the phone `frame_of_record`, eight synchronised streams and a take-start marker. No shot-boundary
detection, no saliency model, no transcription for structure, no training.

Contract `EditDecisionList`: ordered entries with media identity, in/out **as presentation timestamps** (VFR
warning in `docs/ai-director/timeline-example.md` must be obeyed and tested), track, transition, audio, captions,
decision provenance (`authored/selected_by_operator/selected_by_director/default`); immutable, versioned,
hashed; renders identically twice. Binding: unresolved media → `fail`, never a dropped shot. Selection: the one
LLM boundary, proposal-only against the typed EDL, discarded if the EDL revision moved. Render: FFmpeg;
export EDL JSON + FCPXML (stdlib XML). Generative tier off the critical path, provenance `generated`, labelled
in UI and export. Licences: OpenChatCut/autoclip/twirl — check before vendoring (not verified here);
vibe-draw AGPL-3.0. Adopt OpenChatCut's *pattern* (immutable timeline, command layer, one tool surface), not
its code. Location: `packages/takeone/edit/`. **Degrade ladder: the fallback edit costs nothing and always
exists** — build deterministic assembly first (analysis 8 was specified but not run; see §13).

---

## 8 · Target architecture (H)
The diagram, folder structure (`rig/`, `world/`, `blocking/`, `tracking/`, `edit/`, `telemetry/` under
`packages/takeone`) and technology table in the audit prompt (`docs/requests/FABLE-AUDIT-PROMPT-2026-09-13.md`
§11) are **adopted as the recommendation** with these audit-driven amendments: `rig/limits.py` is Tree A's
`calibration.ArmMapping` promoted, not new code; `timing.py`'s duration bound is replaced by per-axis TOPP
(evaluate TOPP-RA vs the 200-line in-house pass used in analysis 2) while `PhaseGovernor` and `governor.js`
stay as the playback law; `DriveModel` is constructed from `configs/rig.json` + `cart-runtime.json` +
`cart-response.json` and returns `unknown` for every screen that needs the empty response tables. Ruled out:
humanoid body models, learned motion, physics-stepped actor, trained editing/shot-boundary/saliency models, ROS,
GPU, microservices.

---

## 9 · Demo risk register and degrade ladder (I)

| Rank | Risk (probability × cost) | Task | Hours | Gate |
|---|---|---|---|---|
| 1 | Simulator plans in an unverified joint mapping (C2/B5): a sign or offset error puts a joint on its stop, as already happened once | Load calibrated limits + mapping into Tree B; show counts per joint per frame; human-supervised verification of sign/offset per joint at tiny amplitude (hardware task, not this audit) | 6 + human | `analysis-01` stays at 0 out-of-range; `servo_to_urdf_transform_verified` flips to true only from a recorded measurement; until then arm checks `conditional` |
| 2 | Light arm under-powered (C6, 5 V supply) | Hardware: confirm variant, supply; until then arm holds `conditional` | 2 + human | measured voltage ≥ spec minimum for the variant |
| 3 | Rehearsal 21× too slow to demo (C7) | Per-axis TOPP bound | 8 | ratio ≤ 2.5× source on reference timeline; governor test still 1e-9 |
| 4 | Scene set piece has no scene (E) | Tier 1 templates + `SceneSpec` v2 | 24 | `steps` template compiles; refusal when cart must descend |
| 5 | Tracking shot planned too close (F) | Envelope curve + refusal | 6 | 1.8 m at 3 m/s refused with "needs 3.75 m" |
| 6 | Wrong rig constants (B) | `RigSpec` from `configs/rig.json` | 4 | no physical constant defined twice (test) |
| 7 | Cart drift / no response tables | keep static-base rungs ready | 0 | decision written |
| 8 | Test suites red at HEAD (A5) | fix `tests.fixtures` shadowing, stale `evaluate_plan` test | 3 | both suites green in one command |
| 9 | Non-hashable plan (`compile_seconds`) | move field out | 0.5 | two processes → identical sha256 |
| 10 | Export not portable (absolute path) | relative `robot_model_path` | 0.5 | export recompiles on a second machine |

**Minimal intervention set:** 1, 3, 6, 9, 10 (~19 h) make the simulator *honest about this robot*;
4 and 5 make the two set pieces *real*. Deliberately left broken this week: wheel collision geometry, actor gait,
two-planner reconciliation (Tree A planner is superseded), Tier 2/3 capture.

**Degrade ladder (decided now):** scene import fails → compile against the studio scene (grammar is
subject-relative, free); arms will not hold → arms `conditional`, show simulated-vs-measured on screen, no
motion claims; cart drifts → static base by hour four, no debate; envelope empty at available standoff →
refuse on screen with the standoff it needs, film the "run past" variant; provider unavailable → deterministic
edit (free); phone will not stream → simulated telemetry only, labelled; selection fails → the timeline *is*
the cut.

**Honesty line:** measured = rig.json user measurements, 0.1375 m/s sample, bus voltages; assumed = every
Tree B limit, mass, footprint, 0.800 N·m; simulated = every pose and check; previs = anything against
`generated` geometry, labelled on screen. A refused tracking shot is shown refused, with its number.

**Three set pieces:** scene-grounded shot — real today only against the studio; one change (Tier 1) from real;
rung: studio scene. Tracking — real today as pan-from-standing-cart at ≥ 1.25·v; one change (envelope +
refusal) from being *shown* honestly; follow-the-runner not available. Automatic edit — real today as the
deterministic timeline; one module (`edit/assemble`) from a rendered cut; rung: the timeline itself.

---

## 10 · Implementation brief (ordered, gated; `work-packages.json` vocabulary)

| WP | Title | Depends | Done when |
|---|---|---|---|
| 10-01 | `rig/limits.py`: promote `calibration.ArmMapping` to a `JointLimitModel` (counts↔rad, signs, offsets, 2° margin, provenance); Tree B `robot.joint_limits` reads it | — | `tests/rig/test_limits_roundtrip.py`; `analysis-01` reports 0 out-of-range samples; arm checks `conditional` while `servo_to_urdf_transform_verified=false` |
| 10-02 | `rig/rigspec.py` from `configs/rig.json`; Tree B model built from it (1.23 m, +90°, 0.58 m track, 0.59 m wheelbase); `previs_rig.json` marked historical | — | `test_rigspec_single_source.py`: no constant defined twice |
| 10-03 | Plan artefact hygiene: `compile_seconds` out of the hashed plan; relative `robot_model_path`; fallback-grid events logged | — | two processes → identical sha256; export recompiles on machine 2 |
| 10-04 | Duration bound: per-axis TOPP replacing the global bound in `timing.minimum_duration`; governor unchanged | 10-01 | reference ≤ 2.5× source; governor Py/JS test still passes |
| 10-05 | Telemetry recorder + `binding_constraint`; data panel + scrubber + JSON/CSV export in `dist/` | 10-01 | `telemetry/test_schema.py`: every field has provenance and status |
| 10-06 | Surface everything clipped: render `take.cart.notes`; single clamp with requested-vs-applied; achieved roll per frame | — | UI shows requested vs applied for every channel |
| 10-07 | Torque allowance per arm from spec at measured voltage, `spec, not measured`; light-supply blocker recorded | — | screen reports per-arm limit + provenance; `unknown` when voltage unknown |
| 10-08 | `world/` `SceneSpec` v2 + `importers/templates.py` (`street`, `steps`, `doorway`) + drivable/walkable + render/collision parity | 10-02 | `test_drivable.py`: a 0.17 m step is not drivable; parity test |
| 10-09 | `blocking/` solve + named refusals | 10-08 | `test_refusal.py`: every refusal names a parameter and an alternative |
| 10-10 | `tracking/envelope.py` + `TrackingShot` + refusal | 10-01 | `test_envelope.py` matches closed form; `test_running_shot.py` refuses at 1.8 m, passes at 3.75 m for 3 m/s |
| 10-11 | `edit/assemble.py` deterministic EDL from `timeline.py`; `bind.py`; `render.py`; `export.py` FCPXML | — | `test_assemble_determinism.py`; `test_binding.py` unresolved → `fail`; `test_fallback.py` |
| 10-12 | `edit/select.py` LLM ranking as proposals | 10-11 | proposal against stale revision discarded |
| 10-13 | Repository: move `TakeOne-main` per A2 with before/after map; restore test discovery for both trees | 10-03 | both suites green in `scripts/TakeOne.ps1 -Command test` |

---

## 11 · Where the existing decisions are right
`CONVENTIONS.md`, `scene.py` render/collision unification, the Python/JS governor agreement test, `_structural`
separation, `unknown`-not-`pass`, subject-relative shot grammar, `timeline.py` coverage invariant, `wire_polarity`
at the transport. Extend these; do not replace them.

## 12 · Where this audit contradicts repository documents
- `TakeOne-main/README.md` headline numbers describe a plan that is `fail` overall (finding 3).
- Tree B's "joint limits" are not the robot's (finding 1) — contradicts any reachability statement in that README.
- `docs/architecture-review-2026-09-12.md` calls Tree A's planner the compiler of record; this audit recommends it be superseded by Tree B's planner over Tree A's limit model.

## 13 · What was not completed (honest gaps)
- Analysis 3 (same shot through both planners, field-by-field) — **not run**; C13 unresolved.
- Analysis 8 (deterministic EDL compiled twice) — **not run**; the argument in §7 rests on code reading of `timeline.py`.
- `scripts/TakeOne.ps1 -Command test/diagnose/dry-run` and `scripts/verify.py --output-dir` were not captured as transcripts (the repo `.venv` is absent on this machine; suites were run directly from an external venv — `evidence/treeA-*.txt`).
- Separate files 01–10 were not split out; this document is the deliverable. Per-item JSON Schema for §4 was not emitted.
- Licences of OpenChatCut, autoclip, twirl not verified; phone model/LiDAR not verified.
