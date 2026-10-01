# 17 — Whole-pipeline audit: script → shots → simulator → plan → filming

**Engineering prompt. Written 2026-09-18.**

> **Audit the local working copy at `C:\TakeOne`. Nothing else.**
> The GitHub branch is behind this tree and does not contain the work being audited. Do not
> clone, do not `git pull`, do not compare against a remote: read and run the files on disk
> at `C:\TakeOne`. A finding measured anywhere else is not a finding about this product.

Every `[VERIFIED]` number in §1 was produced by executing the real product code **in that
local working copy**, with `mujoco==3.13.0` and `scipy==1.15.3` installed, against
`tests/fixtures/director_arrival.json`. Re-run the commands in §1.8 before trusting any
figure: the audit ran on Python 3.10 with a `StrEnum`/`UTC` shim and off-pin
`scipy`/`numpy`, while `C:\TakeOne` runs Python 3.13 with the pinned versions.

You are auditing the one thing this repository exists to do: turn a filming brief into a
script, a script into shots, shots into a rehearsed simulator move, that move into a robot
plan, and that plan into real footage — without ever claiming something physical that was
not measured.

The pipeline **works end to end today**. This is not a repair prompt. It is an audit of a
working system, and its job is to find the places where the chain is real but unproven, the
places where a gate fires and nobody hears it, and the places where a skill tells the model
something the code cannot enforce.

Read this whole document. Then read `AGENTS.md`, `CLAUDE.md` and `docs/architecture.md`.
Every hard rule in `CLAUDE.md` still applies.

---

## 0. How to use this prompt

### 0.1 Confidence labels

- `[VERIFIED]` — produced by running the code during the 2026-09-18 audit. The command that
  produced it is in §1.8. File and line citations are real.
- `[DECIDED]` — a product decision. Do not re-open.
- `[UNVERIFIED]` — believed true, never executed against the real dependency. Everything
  touching a physical iPhone, a live OpenAI or Gemini endpoint, and a powered motor.

### 0.2 Non-negotiables

Unchanged from prompt 16, and this prompt never asks you to break one:

1. The simulator never opens a serial port. `[VERIFIED]` `preflight` reports
   `serial_ports_opened: false` on a fully compiled plan.
2. Never claim hardware readiness from simulated results.
3. Do not unblock the physical-motion path. `physical_path_verified` is `False` at
   `packages/takeone/motion/studio.py:69` `[VERIFIED]`.
4. Do not rewrite tests to make an audit pass. An audit that edits the evidence is not an
   audit.
5. `apps/rehearsal/dist/` is authored source.
6. Mesh JSON and frame arrays are byte-faithful.
7. On-demand rendering only.

**And one more, specific to this prompt: you may not add a test that passes by asserting
less than the system already does.** A test that asserts `compile_preview` returns a dict is
worse than no test, because it makes the next reader believe the chain is covered.

### 0.3 Sequencing

```
A. The end-to-end test that does not exist   ← do first; it is the audit's instrument
B. The edit-duration contract                ← the seam most likely to drift silently
C. Gate-to-human: do the reviews reach anyone?
D. The creative layer: skills and prompts
E. Performance: first preview in 95 seconds
F. The unverified seams, named and bounded
```

### 0.4 What "done" means

Every package has acceptance criteria in §8. A package is done when its criteria are
demonstrable **and** the numbers in §1 have been re-measured on the host and either
confirmed or corrected in `data/verification/`.

---

## 1. Ground truth: the pipeline as it actually runs

`[VERIFIED]` throughout unless marked. This section is the audit's findings; the work
packages act on it.

### 1.1 The chain, with its real seams

```
ProductionBrief + context + filming skill
   → takeone.director.provider (OpenAI Responses, strict schema)     [UNVERIFIED: no key]
   → document{title, logline, actors, marks, questions, scenes[]}
   → scene.shots[]{shot_id, start_ms, end_ms, actor_id, mark_id, framing,
                   movement{template_id, subject_motion, parameters[]},
                   camera_target{kind,target_id}, tracking{cart,phone,on_loss}}
   → takeone.director.studio.shot_settings(shot)          ← THE creative/physical seam
   → takeone.previs.cache.compile_preview(settings)       ← content-addressed, on disk
   → preview{frames[], duration_s, orbit_start_s, orbit_duration_s, summary{}, plan_id}
   → previs review layer (shot / motion / screen / travel / clearance)
   → takeone.planning.compiler.compile_shot(settings)     ← the older validated pipeline
   → takeone.motion.plan.prepare_shot(shot) → Plan
   → takeone.motion.limits.preflight(plan)                ← refuses; 11 named blockers
   → [live execution blocked]
   → takeone.embodied.BehaviorManager.observe()           ← recording without motion authority
   → VisualServoController.settled → settle_streak >= 3
   → BehaviorRecordingAdapter → RecordingService(source="phone") → PhoneTake  [UNVERIFIED: no device]
```

`director.studio.shot_settings` at `packages/takeone/director/studio.py:122` is the single
translator from an authored shot to simulator settings. Everything creative is upstream of
it; everything physical is downstream. **If you audit one function, audit that one.**

### 1.2 Script → shots `[VERIFIED]`

Against `tests/fixtures/director_arrival.json` (a real 30-second, five-scene arrival film):

| | |
|---|---|
| brief | 30 000 ms, 16:9 |
| scenes / shots | 5 / 5 |
| spaces | 5 distinct `space_id`s — the skill's "keep distinct places distinct" holds |
| actors / marks | 2 / 5 |
| edit coverage | 30 000 ms, ends at 30 000 ms, **no gaps, no overlaps** |
| camera targets | actor, **object**, actor, actor, actor |
| templates | `static`, `tilt_up`, `side_track`, `track_lead`, `static` |

### 1.3 Shots → simulator `[VERIFIED]`

All five shots resolve settings and compile. The measured relationship between the authored
edit and what the rig will actually rehearse:

| shot | template | edit | total rehearsal | setup | **filmed** | filmed − edit |
|---|---|---|---|---|---|---|
| arrival-1 | static | 5.0 s | 9.88 s | 4.88 s | 5.00 s | **0.00** |
| arrival-2 | tilt_up | 5.0 s | 9.88 s | 4.88 s | 5.00 s | **0.00** |
| arrival-3 | side_track | 8.0 s | 13.48 s | 4.88 s | 8.60 s | +0.60 |
| arrival-4 | track_lead | 6.0 s | 12.40 s | 6.00 s | 6.40 s | +0.40 |
| arrival-5 | static | 6.0 s | 10.88 s | 4.88 s | 6.00 s | **0.00** |

This is **correct**, and the reason is worth writing down because it looks like a bug: total
rehearsal is roughly double the edit, but the difference is the calibrated setup and aiming
phase, which `SKILL.md` explicitly excludes from the edit ("Calibrated setup and aiming are
additional time, excluded from the edit"). `preview.orbit_duration_s` is the filmed window
and it matches the authored beat exactly wherever the template accepts `duration_s`.

**The mechanism behind the two tracking rows, and the thing package B exists for:**
`shot_settings` injects the authored edit length into `duration_s` **only for templates that
list `duration_s` among their parameters**. `static` and `tilt_up` do; `side_track` and
`track_lead` do not — for those, duration is derived from actor travel and cart pace, so the
settings keep the catalog default of `10.0 s` and the filmed window comes out of geometry.

That is defensible and matches the skill ("Straight travel estimates distance/speed"). It is
also completely invisible: nothing in the document, the UI or the test suite states that for
two of the five templates the authored beat length is an *output*, not an *input*.

### 1.4 The review layer fires — on every shot, at a severity nobody has to read `[VERIFIED]`

*(Corrected 2026-09-18 against the host. The earlier draft of this section described arrival-2
as the single failing shot and quoted a uniform 64 samples. Both were wrong; the measured
behaviour below is worse and more interesting than the claim it replaces.)*

Five review functions exist. On the repository's canonical five-shot fixture
(`tests/fixtures/director_arrival.json`), **one of them contributes anything**:

| review | result on all five shots | why |
|---|---|---|
| `shot_review.review` | fires `promised_region_cropped` on **5 of 5** | see below |
| `motion_review.review_motion` | `None` | `motion_review.py:61` — `if template not in BOOM_DIRECTIONS: return None`. None of `static`, `tilt_up`, `side_track`, `track_lead` is a boom template. |
| `screen_review.review_screen` | `None` | `screen_review.py:102` — returns `None` when `shot["design"]["screen_targets"]` is empty. No fixture in the repository carries one. |
| `travel_review.review_travel` | returns a result, but its issues never reach the shot review | `shot_review.py:157` merges `travel["issues"]` only when `shot["motion_requirements"]` is truthy. It is false on 5 of 5. |
| `scene_checks.sampled_scene_clearance` | never called by the pipeline | same gate, `shot_review.py:160`. Reachable only by calling it directly, as this audit did. |

**The one that fires, fires on everything.** Measured, per shot:

| shot | template | framing | samples | affected | min screen margin | time range (s) | severity |
|---|---|---|---|---|---|---|---|
| arrival-1 | `static` | wide | 64 | **64** | −0.4248 | 0.0–5.0 | manual |
| arrival-2 | `tilt_up` | wide | 64 | 43 | −1.0193 | 0.0–3.36 | manual |
| arrival-3 | `side_track` | medium | 109 | **109** | −0.4793 | 0.0–8.6 | manual |
| arrival-4 | `track_lead` | wide | 81 | **81** | −0.7665 | 0.0–6.4 | manual |
| arrival-5 | `static` | medium | 76 | **76** | −0.3619 | 0.0–6.0 | manual |

Sample count is `len(coverage_frames)` and therefore varies with the filmed window; it is not
64. Four of the five shots are cropped at **100 % of examined samples**.

**The cause is arithmetic, not authorship.** `shot_review.projection` divides by
`[18.0, 10.125]`, a 36 × 20.25 mm frame. At the fixture's authored `focal_mm = 35` and
`radius_m = 2.5`, the vertical field is `2 × 2.5 × 10.125 / 35 = 1.446 m`. `REGIONS["wide"]`
is `(0, 1)` — the whole standing actor — and `subject_height_m` is `1.72`. **1.72 m cannot fit
in 1.446 m.** Every wide and medium shot in the canonical document is geometrically guaranteed
to fail this gate before anyone reads the blocking.

**And the fix exists, unreachable.** `shot_review.fit_opening` (`:100`) solves for the focal
length that holds the promised region — it is the answer to exactly this failure. It has one
caller, `director/studio.py:317`:

```python
if shot.get("design", {}).get("lens_policy") == "fit_subject":
    item["framing_adjustment"] = fit_opening(shot, settings, scene, mark)
```

No shot in any fixture in the repository has a `design` block at all. So `fit_opening` never
runs, and the same absence is what sets the severity: `shot_review.py:199` reads
`severity="revision" if design and visibility != "intentional_partial" else "manual"`. **No
`design` → no lens fit → crop on every shot → and the crop is labelled `manual`**, which per
D3 must not turn a test red. The product's own canonical example takes the legacy path end to
end, and the only gate that fires is the one nobody is obliged to act on.

On **arrival-2** the failure is also the one the director skill names. Its `camera_target` is
`{"kind": "object", "target_id": "event-sign"}` and its `camera_intent` reads *"Tilt from the
people toward the actual Hack the North sign proxy and hold it legibly. The target is the
sign, not the face."* The skill warns: *"A sign reveal must target the sign; filming someone
looking upward does not reveal it. Tilt-up begins below its target by angle_rad and ends aimed
at it."* Measured arm rotation excursion is 0.2608 rad against an authored `angle_rad` of
0.2618 rad — the tilt executes as written. The shot is aimed correctly at the *end* and
off-target for the first 3.36 s. That one is a real authoring hazard. The other four are the
lens arithmetic above, and conflating them was the error in the previous draft.

**The measured return contracts** — the reviews do not share a shape, and any test asserting a
uniform one is asserting a fiction:

| review | `status` | `timebase` | sample field |
|---|---|---|---|
| `shot_review.review` | `"reviewable"` | `"seconds of this shot's filmed source, excluding setup"` | `samples_examined`, `coverage_samples_examined` |
| `travel_review.review_travel` | `"reviewable"` | `"edit-local seconds; source offsets retained; setup and unused source excluded"` | **none** |
| `sampled_scene_clearance` | `"sampled_clear"` | **none** | `samples` (127 / 127 / 201 / 151 / 151) |
| `review_motion`, `review_screen` | — | — | return `None` |

Issue dicts, where present, carry exactly
`code`, `severity`, `time_range_s`, `observation`, `evidence`, `recommendation`.

### 1.5 Simulator → robot plan `[VERIFIED]`

`compile_shot(planning.settings.DEFAULTS)` → 661 frames → `prepare_shot` → `preflight`:

```
execution_mode        : qualified
software_plan_valid   : true
shot_fidelity_passed  : true
live_execution_allowed: false
serial_ports_opened   : false
geometry_warnings     : []
qualification_warnings: []
physical_tracking_verified: false
blockers              : 13
```

*(Corrected 2026-09-19: the count is **13**, not 11. The earlier draft folded the two
per-arm pairs into single entries. Verbatim, from the host:)*

```
 1  Assumed robot center of mass leaves the conservative static support polygon
 2  Arm path has nonzero start/end derivatives; prepare explicit approach and departure
 3  phone: verified model alignment is required
 4  light: verified model alignment is required
 5  Declare acceptance tolerances and measurement methods before the trial (--criteria)
 6  Independent loaded left/right wire-command response measurements are missing
 7  Measured cart startup, stopping corridor, watchdog/brake behavior and physical stop
    procedure are missing
 8  Loaded arm hold and fault-stop response at recorded voltage, payload and temperature
    need measurement
 9  Measured scene clearance, payload demand and loaded support/stability review are missing
10  Measured lens/light reference transforms and independent spatial residuals are missing
11  Actual read/write timing and response lag under all three device workloads need
    qualification
12  phone: loaded velocity, acceleration, jerk, step and tracking measurements are missing
13  light: loaded velocity, acceleration, jerk, step and tracking measurements are missing
```

Every one of the thirteen names a quantity someone can go and measure. Not one says "not
ready". That property is what §3 step 5 asserts, and it is the reason this section calls the
preflight the best-engineered part of the system.

**Cost, so nobody is surprised by the audit instrument.** Measured on the host:
`compile_shot` 88.2 s (661 frames), `prepare_shot` 94.0 s, `preflight` 0.1 s. The planning
compiler caches one canonical solve per process (`planning/compiler.py:32`), so the
end-to-end module pays this once in `setUpClass`, not per test — roughly three minutes for
the plan-and-preflight class. That is the honest price of running the real solver, and it is
why the module is `skipUnless(SIMULATION)` rather than mocked.

`RobotPlayback().status()` reports `physical_path_verified: false`, `runtime_available: false`.

**This is the best-engineered part of the system.** The software half is qualified and says
so; the physical half is blocked and names exactly which measurement is missing. Do not
weaken it, and do not let any package below add a code path that bypasses it.

### 1.6 Plan → filming `[VERIFIED]` (device fake, lifecycle real)

Driving `BehaviorManager` + `BehaviorRecordingAdapter` + `RecordingService` with a fake device:

```
prepare     behavior=1033e79b  state=HOLDING     physical_motion=False
observe     state=APPROACHING  authority=observe armed=False  physical_motion=False
frame 1     state=SETTLING     settle_streak=1   settled=True
frame 2     state=SETTLING     settle_streak=2   settled=True
frame 3     state=RECORDING    settle_streak=3   take=b4ec1d9c   <- the device was told to roll
frame 4     state=RECORDING    settle_streak=4
stop        state=ready  source=phone  real_media_verified=False  media=None
            media_location=phone_internal_storage
events      start_requested, start_acknowledged, stop_requested, stop_acknowledged,
            device_reported_stop
lost target state=HOLDING  termination_reason=target_lost:person-0001
arming      armed=False  actuator_available=False  motion_authority=none
```

The camera rolled itself on a genuine three-sample settle, the take landed with the honest
fields, the subject leaving frame stopped it with the track named in the reason, and arming
was never touched.

### 1.7 The creative layer `[VERIFIED]` structure, `[UNVERIFIED]` behaviour

- 8 `SKILL.md` files. `director/robot-film-director/SKILL.md` is 146 lines and is the spine:
  staging, targets and follow intent, rig limits, independent cinematic layers, take sharing,
  choreography, performance and the cut.
- `skills.load_skills()` returns 4 filming skills — `cinematic` 1 277, `dialogue` 1 124,
  `product` 1 114, `reaction` 1 095 characters.
- `voice/persona.build_persona(skill, *, filming_skill_text=None)` is called from
  `voice/live_tokens.py:101` and locked into the minted token.
- `voice/tools.declarations(template_ids)` locks the movement enum to the **live** catalog
  ids, so the model cannot name a template the simulator does not have.

**None of this has been executed against a live model in this audit.** There is no
`OPENAI_API_KEY` here, and the Gemini browser socket remains unverified.

### 1.8 How every number above was produced

```bash
pip install scipy mujoco                    # off-pin here; the host has the pinned versions
export PYTHONPATH=<shim>:$PWD/packages
python3 - <<'EOF'
from takeone.director.studio import shot_settings
from takeone.previs.cache import compile_preview
# ... walk tests/fixtures/director_arrival.json; see §3 for the permanent version
EOF
```

The ad-hoc script that produced §1.2–§1.6 was **not** kept. Package A's job is to make it a
test so the next person does not have to re-derive it.

### 1.9 Environment reality

"The host" everywhere in this document means the Windows machine that owns `C:\TakeOne`.

| | audit environment | `C:\TakeOne` |
|---|---|---|
| Python | 3.10 + `StrEnum`/`UTC` shim | 3.13 |
| scipy | 1.15.3 | 1.17.0 (pinned) |
| numpy | 2.2.6 | 2.3.5 (pinned) |
| mujoco | 3.13.0 | 3.13.0 (pinned) |
| ruff | absent | pinned 0.12.12 |

Solver output can move with scipy. **Every geometry number in §1 must be re-measured on the
host before it is quoted anywhere.**

---

## 2. Decisions already made — do not re-open

`[DECIDED]` 2026-09-18.

**D1. The audit's instrument is a test, not a script.** Everything §1 measured becomes
`tests/test_pipeline_end_to_end.py`. A markdown report rots in a week; a test fails the day
the chain breaks.

**D2. `director_arrival.json` is the canonical subject.** It is a real five-scene film with
object targets, walking actors, tracking templates and a held ending. Do not invent a
simpler fixture to make the test pass; a fixture chosen for convenience audits nothing. If
the fixture itself is wrong (see §5), fix the fixture and say so.

**D3. A `severity: "manual"` finding is not a failure.** `promised_region_cropped` on all
five shots must not turn the test red. The test asserts that the finding is **produced and
reachable**, and pins its count and severity; a human decides whether the shots are wrong.
Note the trap this rule sits next to: §5(c) found that `manual` is assigned *because* the
fixture has no `design` block, so "manual findings never fail" and "the canonical document
takes the legacy path" combine into a gate that can never fail on the only document the suite
exercises. D3 stays — tests do not adjudicate authorship — but it is not a reason to leave
§5(c) undecided.

**D4. The physical gate stays shut.** No package may add a path that reaches a motor. The
audit proves the refusal, it does not remove it.

**D5. Geometry numbers are ranges, not equalities.** `scipy` moves solver output. Assert
tolerances wide enough to survive a pinned-version bump and narrow enough to catch a real
regression; state the tolerance and why in a comment.

---

## 3. Work package A — the end-to-end test that does not exist

Today nothing in `tests/` walks brief → shots → preview → review → plan → preflight → take.
34 recording tests cover the lifecycle; `test_planning` covers the compiler; `test_shot_design`
covers the document. **Nothing covers the joins**, which is exactly where a pipeline breaks.

Create `tests/test_pipeline_end_to_end.py`. It must run with no network, no device and no
robot, and it must be honest about what it is not proving.

Structure:

```python
class PipelineTests(unittest.TestCase):
    """brief -> shots -> simulator -> review -> plan -> preflight -> take.

    Nothing here touches a model provider, a phone or a motor. It proves the
    joins between the stages hold; it proves nothing physical.
    """
```

1. **Script → shots.** Load the fixture. Assert 5 scenes, 5 distinct `space_id`s, the edit
   covering exactly `brief.duration_ms` with no gap and no overlap, and every `mark_id` and
   `actor_id` resolving. Assert at least one `camera_target.kind == "object"`, because object
   targeting is a distinct code path the person-tracking path does not exercise.
2. **Shots → simulator.** For every shot: `shot_settings(shot)` — which returns
   `(settings, defaulted_parameter_names)`, not a bare dict — then `compile_preview(settings)`.
   Assert frames are non-empty, `plan_id` is a 64-character lowercase digest, and
   `orbit_start_s + orbit_duration_s == preview["duration_s"]` **exactly**. Do not assert
   `<= duration_s`: `preview["duration_s"]` is the whole prepared clock including setup, and
   `orbit_start_s` alone is 4.88 s on four of the five shots. The earlier draft of this step
   asserted a relation that is false on 5 of 5 shots; a test written from it would have
   failed on a correct system, which is the worst kind of test.
3. **The edit contract** — package B owns the assertion; the test is its home.
4. **Reviews.** Run all five reviews on every shot, and assert **the contract each one
   actually has** (§1.4 table), not a uniform one:

   - `shot_review.review` → `status == "reviewable"`, `timebase ==
     "seconds of this shot's filmed source, excluding setup"`, `samples_examined > 0` and
     equal to `coverage_samples_examined`.
   - `travel_review.review_travel` → `status` and `timebase` present, `timebase` is the
     edit-local one, and **no** `samples_examined` key. Assert its absence, so that adding
     one later is a deliberate change and not a silent one.
   - `sampled_scene_clearance` → `status == "sampled_clear"`, `samples > 0`, and **no**
     `timebase`. Same reasoning.
   - `review_motion` and `review_screen` → `is None` on all five shots, each with the
     guard's file:line in the assertion message. **This is the assertion that documents the
     finding.** It is not "asserting less than the system does": the system does nothing
     here, and pinning that is what makes it visible the day a boom template or a
     `screen_targets` contract enters a fixture and the guard stops firing.

   Then, for every issue produced by any review, assert it carries all six of `code`,
   `severity`, `time_range_s`, `observation`, `evidence`, `recommendation` — a gate that
   fires without a recommendation cannot be acted on.

   Finally assert the §1.4 headline directly: `promised_region_cropped` on **5 of 5** shots,
   every one at `severity == "manual"`, and four of the five at
   `affected_samples == examined_samples`. When package C fixes the cause, this assertion is
   what fails, and it should — loudly, with the count in the message.
5. **Plan and preflight.** Compile one shot to a plan. Assert `software_plan_valid`,
   `serial_ports_opened is False`, `live_execution_allowed is False`, and that `blockers` is
   non-empty. **Assert the blockers name measurements, not statuses**: each string must
   mention a measurable quantity. A blocker that says "not ready" is not a blocker.
6. **Take.** Run the §1.6 sequence with a fake device. Assert the settle streak reaches
   `settle_samples` before any device call, `source == "phone"`,
   `real_media_verified is False`, `media is None`, and that losing the subject names the
   track in `termination_reason`.
7. **The gate that must stay shut.** Assert `RobotPlayback().status()["physical_path_verified"]
   is False` and that `BehaviorManager.observe()` leaves `armed` False.

Mark the whole module `@unittest.skipUnless(has_simulation(), ...)` on `mujoco`/`scipy` so a
stdlib-only checkout still runs the rest of the suite — and make the skip message name the
missing package, so a skipped audit is never mistaken for a passing one.

---

## 4. Work package B — the edit-duration contract

§1.3 found that for `side_track` and `track_lead` the authored beat length does not reach the
simulator: `duration_s` is not among those templates' parameters, so settings keep the catalog
default and the filmed window falls out of geometry.

This is probably right. It is certainly undocumented, untested and invisible.

Do three things:

1. **Name it in the catalog.** Every template entry gains
   `duration_source: "authored" | "derived_from_travel"`. `shot_settings` already knows which
   branch it took; make the catalog say so out loud so the model, the UI and the test read the
   same fact.
2. **Assert it.** In the package A test: for `duration_source == "authored"` templates,
   `orbit_duration_s` equals the authored beat within 50 ms. For `derived_from_travel`, assert
   only that the filmed window is **at least** the authored beat — the skill's rule that a
   short source cannot fill a long edit — and record the surplus.
3. **Surface it.** Shot Studio shows the filmed duration; it does not say whether that number
   was obeyed or computed. A beat whose length the rig derived rather than accepted should say
   so where a director reads it, in one short line, with the surplus in seconds.

Do **not** add `duration_s` to the tracking templates' parameters to make the numbers line up.
That would let a model author a duration the cart cannot physically achieve, and the compiler
would then have to silently override it — trading a visible asymmetry for an invisible lie.

---

## 5. Work package C — gate to human

The review layer produces excellent findings. The audit found one open question and one live
problem.

**The live problem, restated after measurement.** `promised_region_cropped` fires on **all
five** shots of the canonical fixture, four of them on 100 % of examined samples (§1.4). It is
two problems wearing one code:

*(a) The lens arithmetic — four shots.* `focal_mm = 35` at `radius_m = 2.5` gives a 1.446 m
vertical field; `REGIONS["wide"]` promises all 1.72 m of the actor. `fit_opening` exists to
solve precisely this and is gated behind `design.lens_policy == "fit_subject"`, which no
fixture sets. Decide, in this order:

1. Reproduce on the host and record the numbers in `data/verification/`. *(Done —
   `data/verification/pipeline-audit-20260918/`.)*
2. Decide whether `lens_policy` should default to `fit_subject` rather than to nothing. A
   default of "do not check whether the lens can hold what the framing promises" is not a
   neutral default. If it changes, `fit_opening`'s clamp to `[MIN_FOCAL_MM, MAX_FOCAL_MM]`
   becomes load-bearing — assert what happens when the required focal is outside it, because
   a silently clamped lens still crops and would now do so without an issue.
3. If the default stays, then the product's canonical example must carry a `design` block, and
   **fix the fixture** — the canonical example of the product should not fail its own gate.
   Whichever way it goes, it goes in the commit message.

*(b) The aim — arrival-2.* 43 of 64 samples, minimum margin −1.0193, first 3.36 s of a 5.0 s
beat, with the sign as an object target. This one survives any lens fix: the camera is aimed
at the wrong thing for two-thirds of the beat. Read `previs/shot_review.py:100 fit_opening`
and `:46 subject_points`, then decide whether `angle_rad = 0.2618` (15°) can hold a sign at
2.4 m in frame from the start of the beat. If `tilt_up` cannot honour a "reveal" from its
start, the skill's sentence *"Tilt-up begins below its target by angle_rad and ends aimed at
it"* is a promise the template cannot keep for a target that must stay legible. Change the
skill, not the review.

*(c) The severity — both.* `shot_review.py:199` assigns `manual` whenever `design` is absent,
and D3 says a `manual` finding must not turn a test red. So the only gate that fires on this
document is, by construction, the one no test may fail on. Decide whether "the promised region
is outside the frame for 100 % of samples" deserves `revision` regardless of whether the
author supplied a `design` block. Answer it in the code or answer it in writing; do not leave
it as an accident of a missing key.

**The reviews that never run.** Two of the five review functions return `None` on every shot
of the canonical fixture, and two more are unreachable through `shot_review` because
`shot["motion_requirements"]` is false on all five (§1.4 table). Before anything else in this
package, answer the question that matters: *does a gate that never fires protect anyone?* For
each of `review_motion`, `review_screen`, `review_travel`'s issue merge and
`sampled_scene_clearance`, state with file:line either (i) the fixture or document shape that
would make it fire, and add that fixture, or (ii) that nothing in the product can currently
reach it, and say what that means for the claim that the review layer covers the pipeline.

**The open question.** `promised_region_cropped` reaches `orbit.js` and `shot-direction.js`,
so Shot Studio shows it. Establish, by reading the code and then by looking at the running
pages:

- Does the **Director** page surface geometry issues for shots the AI just proposed, or only
  Shot Studio after a human opens the shot?
- Does the **voice** director know? `voice/tools.py` declares 14 tools; if a shot the model
  proposed fails its geometry review and the model is never told, it will defend a broken
  shot in conversation.
- Does a `severity: "manual"` finding block `mark_ready` in the session state machine
  (`director/service.py`), or can a production reach `request_record` with an unresolved
  cropped subject?

Whatever you find, write it down. If the answer is "the finding stops at Shot Studio", that
is a finding about the product, not a bug to paper over.

---

## 6. Work package D — the creative layer

`[UNVERIFIED]` — none of this ran against a live model during the audit. Do not report any of
it as working until it has.

1. **Exercise the provider once, with a real key.** One brief, one skill, one document.
   Record the request and the response in `data/verification/` with the key redacted. Assert
   the returned document validates against `director/contracts.py` **and** that every
   `movement.template_id` it chose exists in the live catalog.
2. **Measure the prompt.** Report the assembled size in characters and tokens: persona +
   `robot-film-director/SKILL.md` + the selected filming skill + `shot-design` +
   `rehearsal-review` + the strict schema. A 146-line skill plus four sub-skills plus a schema
   is a large instruction; if it is close to a context or cost limit, that is a finding.
3. **Test the skill's own hazards.** The director skill states rules a model can break in ways
   the schema cannot catch. Write one adversarial case per rule and check the *output*, not
   the prose:
   - a sign reveal that targets the actor instead of the sign;
   - a 6-second beat asking for a large orbit (the skill's "tens of seconds, not a short beat");
   - two consecutive beats sharing a `take_id` across different `space_id`s;
   - a product shot with `subject_motion: "none"` that still requests person following;
   - `camera_position_m` combined with `camera_height_m`, which the skill forbids.
   Each case either gets refused by validation, gets flagged by a review, or gets through. The
   third outcome is the finding.
4. **Check the enum lock end to end.** `voice/tools.declarations` locks the movement enum to
   live catalog ids. Assert that a template removed from the catalog disappears from the
   declarations, so a model can never be offered a move the rig no longer has.

---

## 7. Work package E — performance

`[VERIFIED]` A cold `compile_preview` costs **18.6–19.9 s per shot**. The five-shot fixture is
therefore about **95 seconds to a first full preview** on a cold cache. Warm, it is a disk
read.

This is the pipeline's dominant latency and it sits directly between a director asking for a
film and seeing one. Establish, on the host:

- cold and warm cost per template family (static / tilt / tracking / compound);
- how much of the 19 s is IK versus MuJoCo stepping versus serialization;
- whether `previs/prewarm.py` actually covers the templates the director skill favours — a
  pre-warm grid that misses the common shots buys nothing;
- the real hit rate of `data/previs-cache/` across a session (it holds 512 entries, bounded).

Then decide whether to act. Do **not** optimise by reducing sample counts or loosening solver
tolerances: the review layer's 64 samples and the compiler's dense validation grid are what
make the geometry claims true. If the answer is "95 seconds is the honest cost of solving five
shots", record that and move on — a measured cost is not a bug.

---

## 8. Acceptance criteria

### A — end-to-end test
- [ ] `tests/test_pipeline_end_to_end.py` walks all six stages and passes on the host.
- [ ] It skips, with a message naming the missing package, on a stdlib-only checkout.
- [ ] Deleting any one join (e.g. making `shot_settings` return default settings) turns it
      red. **Prove this by doing it and reverting.**
- [ ] It asserts no physical claim: no test in it can pass by opening a port.

### B — edit duration
- [ ] Every catalog template declares `duration_source`.
- [ ] Authored templates: filmed window within 50 ms of the beat. Derived templates: filmed
      window ≥ beat, surplus recorded.
- [ ] A director can see, in the UI, which of the two a shot got.

### C — gate to human
- [ ] The arrival-2 finding is reproduced on the host with its numbers in `data/verification/`.
- [ ] A decision is recorded: fixture wrong, or template over-promised.
- [ ] The three reachability questions in §5 are answered in writing, with file:line.

### D — creative layer
- [ ] One real provider round-trip captured, redacted, in `data/verification/`.
- [ ] Assembled prompt size reported in characters and tokens.
- [ ] Five adversarial skill cases written; each outcome classified refused / flagged / got
      through.
- [ ] The enum lock is asserted by a test.

### E — performance
- [ ] Cold and warm compile cost per template family, measured on the host.
- [ ] Pre-warm coverage compared against the templates the skill actually favours.

### Whole-tree gate
- [ ] Python: 0 assertion failures; error name set no worse than the recorded baseline.
- [ ] Node: no new failures beyond the two known `.venv` path ones.
- [ ] `scripts/check_integrity.py` exit 0.
- [ ] `ruff check` and `ruff format --check` clean, run on the host.
- [ ] `POST /api/live-director/arm` still returns 409 `physical_path_unverified`.

---

## 9. The honesty ledger for this audit

An audit is the easiest place in a project to manufacture false confidence. These are the
claims this work may **not** make:

| Claim | Status after this audit |
|---|---|
| "The pipeline works" | Only with a fake device, a fixture document, and no model provider. Say which. |
| "The robot can film this" | No. `live_execution_allowed: false`, 11 measurement blockers. |
| "The AI director produces valid shots" | Unproven until §6.1 runs with a real key. |
| "Geometry is correct" | Correct **on this solver version**. Re-measure on the pinned one. |
| "The take was recorded" | The lifecycle was. No frame of real footage exists. |
| "Reviews protect the director" | They fire. Whether anyone is told is §5, unanswered. |

Strings that must survive this work verbatim: `physical_path_verified`,
`live_execution_allowed`, `serial_ports_opened`, `real_media_verified`,
`optical_framing_verified`, `baked_pixels_verified`, `hardware_verified`,
`estimated_between_operator_measured_points`,
`identity_scope: "transient_visual_tracks_not_person_identity"`, and the eleven preflight
blockers. They may move; they may not be softened.

---

## 10. Working method

1. Work in `C:\TakeOne`. Confirm you are there before anything else — `git status` may show
   the branch behind its remote, and that is expected and correct; do not reconcile it.
2. Install the pinned `mujoco`, `scipy`, `numpy` and run the §1 measurements yourself before
   reading further. If a number differs from §1, the host is right and this document is
   wrong — correct it in place and note the date.
3. Write package A first. It is the instrument for everything else.
4. Work B → C → D → E. B and C are contract work; D needs a key; E needs a quiet machine.
5. Record evidence in `data/verification/pipeline-audit-<date>/`. Append, never rewrite.
6. Report per package: what changed, what you measured, which acceptance boxes are ticked,
   which are not and why, and every `[UNVERIFIED]` surface you touched.

If you had to make a decision this document did not cover, say so and say what you chose. If
you had to contradict it, say that louder.

### 10.1 Correction log

Per rule 2 above, every place this document was found wrong against the host.

| date | section | was | is |
|---|---|---|---|
| 2026-09-18 | §1.4 | `promised_region_cropped` fires on arrival-2 | fires on **5 of 5** shots, four at 100 % of samples |
| 2026-09-18 | §1.4 | "64 samples per shot" | 64 / 64 / 109 / 81 / 76 — it is `len(coverage_frames)` |
| 2026-09-18 | §1.4 | "all five reviews run" | one runs; two return `None`, two are unreachable through `shot_review` |
| 2026-09-18 | §3 step 2 | `orbit_start_s + orbit_duration_s <= duration_s` | equality against `preview["duration_s"]`; the old form is false on 5 of 5 |
| 2026-09-18 | §3 step 4 | one uniform review contract | three different contracts, two `None` returns |
| 2026-09-19 | §1.5 | 11 blockers | **13**, listed verbatim; `physical_tracking_verified` added to the ledger |

### 10.2 What this audit host cannot decide

The Linux VM that mounts `C:\TakeOne` runs **Python 3.10 with scipy 1.15.3**; the product's
own host runs **3.13 with the pinned scipy 1.17.0, numpy 2.3.5, mujoco 3.13.0**. Two
consequences, both recorded in
`data/verification/pipeline-audit-20260918/PACKAGE-A-RESULTS.md`:

- **Wall-clock-sensitive tests are not decidable from the VM.** `prepare_shot` takes 94 s
  there, so `test_robot_plan_endpoint_exports_both_arms_and_rejects_stale_preview` times out
  on its socket. That is the host's speed, not the product's behaviour. Several geometry
  modules likewise exceed a single shell call's ceiling, so the suite must be run in chunks
  from the VM and in full only on the Windows host.
- **Anything gated on a 3.11+ stdlib addition reads as a product bug on 3.10.** One was found
  and corrected in the host shim rather than in the product: `sqlite3.SQLITE_BUSY` and
  `error.sqlite_errorcode`, which `recording/repository.py:118` uses to tell a held lease from
  a real failure. Before touching product code over a failure on this VM, check whether the
  symptom disappears on 3.13.

---

## Appendix — the seven traps in this pipeline

1. **`duration_s` is an input for some templates and an output for others.** §1.3. The single
   most likely place for a silent creative/physical divergence.
2. **`preview.duration_s` is not the beat length.** It includes ~4.9 s of setup.
   `orbit_duration_s` is the filmed window. Reading the wrong one makes every shot look twice
   as long as it is.
3. **`compile_preview` is content-addressed over settings *and* provenance.** Change a config,
   a calibration file or the model, and every entry misses. A "slow" pipeline may simply be a
   correctly invalidated cache.
4. **Pre-warm and speculative compiles must call `previs.cache.compile_preview` directly**,
   never `/api/compile`, or they contend with `server.compile_lock`.
5. **`BehaviorManager.update_perception` returns early unless the behavior is already active.**
   Sending perception at a `HOLDING` behavior does nothing and looks like a broken detector.
6. **The quiet latch** makes almost every voice tool refuse while a take is outstanding. Test
   voice and recording together or chase a phantom.
7. **`review/vlm.GeminiFrameAnalyst` is never instantiated.** Every take verdict today is
   `local-pixel-statistics`. A "vision review" in this product has not seen a frame.
