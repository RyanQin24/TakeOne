# Work package A — the end-to-end test that did not exist

Host: `C:\TakeOne` (the local working copy — not the GitHub branch, which is behind).
Measured 2026-09-19. Python 3.10 on the audit host; numpy 2.2.6, scipy 1.15.3, mujoco 3.13.0.

Artifact: `tests/test_pipeline_end_to_end.py`, 24 tests, all passing.

## What it asserts, stage by stage

| stage | class | tests |
|---|---|---|
| 1 script → shots | `PipelineTests` | 4 |
| 2 shots → simulator | `PipelineTests` | 2 |
| 3 edit contract | `PipelineTests` | 1 (work package B extends it) |
| 4 reviews | `PipelineTests` | 8 |
| 5 plan → preflight | `PlanAndPreflightTests` | 4 |
| 6 take | `TakeTests` | 2 |
| 7 the gate that stays shut | `ShutGateTests` | 2 |

## Three corrections to engineering prompt 17, made from measurement

**§1.4 — `promised_region_cropped` fires on 5 of 5 shots, not on arrival-2 alone.**

| shot | template | framing | samples | affected | min margin | severity |
|---|---|---|---|---|---|---|
| arrival-1 | static | wide | 64 | **64** | −0.4248 | manual |
| arrival-2 | tilt_up | wide | 64 | 43 | −1.0193 | manual |
| arrival-3 | side_track | medium | 109 | **109** | −0.4793 | manual |
| arrival-4 | track_lead | wide | 81 | **81** | −0.7665 | manual |
| arrival-5 | static | medium | 76 | **76** | −0.3619 | manual |

Cause is arithmetic: `projection` divides by `[18.0, 10.125]`, so `focal_mm = 35` at
`radius_m = 2.5` gives a 1.446 m vertical field; `REGIONS["wide"]` promises all 1.72 m of the
actor. `fit_opening` solves exactly this and is gated on `design.lens_policy == "fit_subject"`,
which no fixture in the repository sets. The same missing `design` key sets `severity="manual"`
at `shot_review.py:199`, and per D3 a manual finding must not fail a test.

**§1.4 — four of the five review functions contribute nothing on the canonical fixture.**
`review_motion` returns `None` (no boom template); `review_screen` returns `None` (no
`design.screen_targets`); `review_travel`'s issues and `sampled_scene_clearance` are both
gated at `shot_review.py:157` and `:160` on `shot["motion_requirements"]`, false on 5 of 5.

The three reviews that do return a result do not share a contract:

| review | status | timebase | sample field |
|---|---|---|---|
| `shot_review.review` | `reviewable` | `seconds of this shot's filmed source, excluding setup` | `samples_examined` |
| `review_travel` | `reviewable` | `edit-local seconds; source offsets retained; setup and unused source excluded` | none |
| `sampled_scene_clearance` | `sampled_clear` | none | `samples` (127/127/201/151/151) |

**§3 step 2 — `orbit_start_s + orbit_duration_s <= duration_s` is false on 5 of 5 shots.**
`preview["duration_s"]` is the whole prepared clock and `orbit_start_s` is setup excluded from
the edit (4.88 s on four shots, 6.0 s on arrival-4). The relation is equality. A test written
from the original text would have failed on a correct system.

**§1.5 — preflight emits 13 blockers, not 11.** The earlier count folded the two per-arm pairs
into single entries. `physical_tracking_verified: false` was also absent from the ledger in §1.5.

## Cost of the instrument

`compile_shot` 88.2 s (661 frames) · `prepare_shot` 94.0 s · `preflight` 0.1 s.
`planning/compiler.py:32` caches one canonical solve per process, so `PlanAndPreflightTests`
pays this once in `setUpClass`: 97.2 s for the class.

## Mutation evidence — each new assertion goes red when its subject changes

| mutation | assertion | result |
|---|---|---|
| `REGIONS` narrowed so nothing crops | `..._cropped_on_every_shot_at_manual_severity` | RED |
| `BOOM_DIRECTIONS` gains `static` | `..._motion_review_is_inert...` | RED |
| `preview["duration_s"]` shifted by 1 s | `..._partition_the_prepared_clock` | RED |
| `review_travel` grows `samples_examined` | `..._no_sample_count` | RED |

Blocker predicate, checked both ways: it rejects all nine mood strings tried
(`not ready`, `Failed`, `unavailable`, `system blocked`, `error`, `unknown`,
`needs attention`, `check the robot`, `the rig is not ready yet`) and accepts all thirteen
real blockers. A first draft of the predicate let `system blocked` through; the mutation run
caught it.

## Honesty ledger, asserted false rather than assumed

`physical_path_verified` · `live_execution_allowed` · `serial_ports_opened` ·
`physical_tracking_verified` · `real_media_verified` · `optical_framing_verified` ·
`physical_motion` · `media is None` · `zoom_mapping = estimated_between_operator_measured_points`.
`preflight` is additionally run under `patch.object(DeviceFactory, "open")` and asserted not to
have called it.

---

## Regression, by chunk (2026-09-19)

The suite cannot be run with one `unittest discover` on this audit host: several geometry
modules individually exceed the 180 s ceiling of a single shell call. Chunked results:

| chunk | tests | result |
|---|---|---|
| `test_pipeline_end_to_end` (new) | 24 | **OK**, 108.1 s |
| reviews / previs — `motion_review`, `film_review`, `performers`, `orbit_previs`, `attention_geometry`, `light_clearance`, `production_design` | 73 | **OK**, 59.1 s |
| recording / embodied — 9 modules | 102 | **OK**, 23.0 s |
| director / contracts — `director`, `director_http`, `director_script_bridge`, `contracts` | 43 | 1 error (below) |
| `test_movement_library`, `test_scene_aware_director`, `test_creative_planning` | — | exceed the per-call ceiling on this host; not run to completion |

## Two host artifacts, corrected or recorded — neither is a product defect

**1. sqlite3 result codes (corrected).** `recording/repository.py:118` distinguishes "another
process holds the finalization lease" (return False, retry) from a real error (raise) by
reading `error.sqlite_errorcode` against `sqlite3.SQLITE_BUSY` / `SQLITE_LOCKED`. Python 3.11
added all three; this audit host is 3.10, so `getattr(..., None)` returned `None`, the code
took the `raise` branch, and `test_replacement_runtime_waits_for_old_finalizer_admission`
errored with `AttributeError: module 'sqlite3' has no attribute 'SQLITE_BUSY'` — which reads
exactly like a lease bug and is not one. `C:\TakeOne` itself runs Python 3.13, where the path
is correct.

The audit host's `sitecustomize.py` now supplies the two constants and derives
`sqlite_errorcode` from the message as 3.11+ reports it. This makes the host **more** faithful
to the product's runtime, not less, and it cleared that error class: the recording/embodied
chunk went from 1 error to 102/102. The shim is archived beside this file as
`audit-host-sitecustomize.py` so the correction is inspectable rather than invisible.

**2. `test_robot_plan_endpoint_exports_both_arms_and_rejects_stale_preview` (recorded).**
Errors with `TimeoutError: timed out` after 98.4 s. The endpoint compiles a robot plan inside
the request, and `prepare_shot` measures 94.0 s on this host against a socket timeout sized
for the real target. The test is measuring the audit host's speed, not the product. It must be
run on `C:\TakeOne`'s own Python 3.13 (scipy 1.17.0, numpy 2.3.5, mujoco 3.13.0) to mean
anything. **This is the standing limitation of this audit host**: it mounts the local working
copy but runs its own slower Python 3.10 / scipy 1.15.3, so wall-clock-sensitive tests are not
decidable from here.
