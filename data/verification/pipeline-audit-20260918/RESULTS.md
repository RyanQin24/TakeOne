# Whole-pipeline audit — measured 2026-09-18

Executed against `tests/fixtures/director_arrival.json` with the real product code **in the
local working copy at `C:\TakeOne`** (mounted read/write; no GitHub checkout was used, and
the remote branch is behind this tree). Runtime: Python 3.10 + `StrEnum`/`UTC` shim, `mujoco==3.13.0`, `scipy==1.15.3`, `numpy==2.2.6`.
**Off-pin:** the product pins `scipy==1.17.0`, `numpy==2.3.5`, Python >=3.12. Solver output
can move; re-measure on the host before quoting these numbers.

The full findings and the follow-up work are in
`docs/ai-director/implementation/17-pipeline-audit-engineering-prompt.md`.

## Stages exercised

| Stage | Entry point | Result |
|---|---|---|
| script -> shots | `tests/fixtures/director_arrival.json` | 5 scenes, 5 shots, 5 spaces, 30 000 ms covered, no gaps |
| shots -> settings | `takeone.director.studio.shot_settings` | 5/5 resolved |
| settings -> preview | `takeone.previs.cache.compile_preview` | 5/5 compiled, 125-170 frames each |
| reviews | shot / motion / screen / travel / clearance | all ran, 64 samples per shot |
| plan | `planning.compile_shot` -> `motion.prepare_shot` | 661 frames |
| preflight | `motion.limits.preflight` | refused, 11 named blockers |
| filming | `BehaviorManager.observe` -> `RecordingService` | take reached `ready`, `source=phone` |

## Edit-duration contract

| shot | template | edit s | total s | setup s | filmed s | delta |
|---|---|---|---|---|---|---|
| arrival-1 | static | 5.0 | 9.88 | 4.88 | 5.00 | 0.00 |
| arrival-2 | tilt_up | 5.0 | 9.88 | 4.88 | 5.00 | 0.00 |
| arrival-3 | side_track | 8.0 | 13.48 | 4.88 | 8.60 | +0.60 |
| arrival-4 | track_lead | 6.0 | 12.40 | 6.00 | 6.40 | +0.40 |
| arrival-5 | static | 6.0 | 10.88 | 4.88 | 6.00 | 0.00 |

`duration_s` reaches the simulator only for templates that list it as a parameter. `static`
and `tilt_up` do; `side_track` and `track_lead` do not, so their filmed window is derived
from travel and pace. Undocumented and untested — see prompt 17 package B.

## Open finding

`shot_review` reports `promised_region_cropped` on **arrival-2**, the sign reveal:
43 of 64 filmed samples have the promised region out of frame over `[0.0, 3.36] s`,
`minimum_screen_margin: -1.0193`, `severity: "manual"`. Arm rotation excursion 0.2608 rad
against an authored `angle_rad` of 0.2618 rad, so the tilt executes as written.

Either the canonical fixture's shot is badly authored or `tilt_up` cannot hold a reveal
target legible from the start of the beat. Prompt 17 package C decides which.

## Gates confirmed shut

    physical_path_verified : false
    live_execution_allowed : false
    serial_ports_opened    : false
    software_plan_valid    : true
    shot_fidelity_passed   : true

`observe()` reached RECORDING with `armed=False`, `motion_authority="observe"`,
`physical_motion=False`. Losing the subject returned the behavior to HOLDING with
`termination_reason="target_lost:person-0001"`.

## Not verified

No model provider (no `OPENAI_API_KEY`), no phone, no motor, no browser session. The take
lifecycle ran against a fake device; no frame of real footage exists. Cold
`compile_preview` cost 18.6-19.9 s per shot, about 95 s for the five-shot script.
