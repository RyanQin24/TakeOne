# Real robot implementation — 12 September 2026

Current planning update: [the arm mounting and coordinated mobile-IK correction](mobile-ik-correction-2026-09-12.md) supersedes this record's failing-shot calculation. The new 13-second artifact passes the declared software corridors but still fails physical preflight. This document remains the execution, hardware-evidence and recovery history.

The operator supplied a 1.23 m arm-platform height, 1.80 m maximum extended height and 0.34 m horizontal extension for each arm. The operator also authorized phone elbow maximum 3086 and light wrist-flex maximum 3204. The active mappings and real firmware agree on those values, while the hash-checked originals remain unchanged. See [the clarification](robot-motion-clarifications-2026-09-12.md).

The working code connects one reviewed finite plan to the real cart, phone and light interfaces. Original calibrations are recovered, unchanged, and matched against actual motors. Production fake composition and fake completion paths have been removed. **The complete physical shot has not been run or accepted.** Loaded operating measurements, model/tool alignment, cart response and host timing still prevent live execution.

## What was delivered

- One immutable v2 artifact with all ten joints, both wheel channels, frames/units, exact polynomial coefficients/dispatch times/wire values, revision and source/config/model/calibration hashes. Canonical reconstruction rejects rehashed edits; numeric identity survives browser JSON round trips.
- Existing IK/FK preserved, with full phone/light position acceptance. Explicit quintic approach/departure makes boundary behavior reviewable. The browser displays the same evaluated joint reference and wheel-derived cart prediction, including the endpoint, and exports the imported revision unchanged in numeric meaning.
- One owner per real arm bus from fixed-goal activation through motion and terminal hold. Goal → Torque Enable → same Goal is shared with the successful manual-hold procedure. Individual writes are acknowledged; no synthetic feedback, no sag-following targets and no automatic loaded-arm release/reconnect.
- Actual 31-byte per-motor RAM feedback, raw conversion, health/device-error checks, acquisition intervals, complete-cycle deadlines, tracking/settling metrics, fault propagation and explicit supported release. Cart keeps its bounded real UART sender and separate worker.
- Continuous curve and actual encoded-stream limits, shared-scene swept nominal clearance, assumed gravity/static support screens, capability-specific evidence, a run-local cart origin, and independent physical observation assessment. The timed cart schedule starts wherever the cart is placed; absolute initial x/y/yaw is not an execution input.

## Verification and actual hardware evidence

| Evidence | Result | What it establishes |
|---|---|---|
| Required `scripts/TakeOne.ps1 -Command test` at 2026-09-12T22:51:53.351367+00:00 | All 7 checks passed: 210 product + 28 simulation + 13 browser tests; JS syntax, Ruff and preservation checks passed | Software contracts, independent polynomial/encoder arithmetic and scoped injected transport/fault handling; no automatic actuation |
| Independent source preservation | 1086 LeRobot files checked, 6 generated metadata entries excluded, no integrity failures | Preserved imported working source; original nested Git history is not compared by this check |
| Actual browser review/export | 11 s artifact imported; start/midpoint/endpoint wires 0/0, .04/.04, 0/0; exact endpoint 11 s; downloaded JSON validates and matches canonical content | Real UI/file workflow and reference display; not physical movement |
| Host USB enumeration, 22:19 UTC | COM9/5B14111456, COM8/5A7A058801, COM5/0001 | Host adapter identity; no port opened by enumeration |
| Real read-only arm inspection, 22:30 UTC | All ten replied, originals matched, position mode and torque-off state observed | Current physical device correspondence |
| Real production RAM-read path, 22:54 UTC | All ten returned 31 bytes with comm=0/device_error=0; all torque=0; no non-read packets attempted; ports closed | Actual transport/decoder and range-rejection path. One five-motor read ~4.06 ms phone/~4.04 ms light; not a workload latency qualification |
| Authorized endpoint revision, 20:17 EDT | COM9 elbow 3085→3086 and COM8 wrist flex 3199→3204 acknowledged and read back; locks restored; all torque remained 0; ports closed | Real firmware now matches the configured revision; no goal or torque command was sent |
| Post-revision inspection, 20:17 EDT | All ten replied and configured calibrations matched; torque 0; phone shoulder lift 3176 exceeds unchanged maximum 3161 | Endpoint revision verified; current phone pose still blocks activation |
| Earlier phone hold | 30.911 s; 531 samples; 20 individual acknowledged goal/on/same-goal/off writes; torque-off confirmed | Real stationary command/feedback sequence at that pose |
| Earlier light hold | 50.650 s; 898 samples; same acknowledged sequence; operator reported holding before supported release | Real observed holding at that pose, with recorded encoder deviations |
| New full cart/phone/light movement | Not performed | Tracking, full loaded hold/stop, tool accuracy, physical synchronization and repeatability remain unverified |

Software logs: [final verification](../data/verification/real-robot-final-verification.txt), [summary](../data/verification/summary.json), [canonical plan check](../data/verification/real-robot-canonical-check.json). Browser file evidence: [review record](../data/verification/real-robot-browser-review.json). Hardware evidence: [individual register inspection](../data/verification/real-robot-arm-inspection.json), [actual adapter RAM reads](../data/verification/real-adapter-ram-inspection.json), [USB inventory](../data/verification/real-robot-usb-inventory.json). The previous hold reports are described in [arm commissioning](arm-commissioning.md); they remain unchanged.

An intermediate verification run rejected code changing while its planner process was running and found one formatting issue. Those were corrected and a fresh frozen-source full run passed. Browser import exposed a real numeric hashing bug (`1.0` versus JavaScript `1`); it was fixed and checked through both JavaScript and the actual downloaded file. The browser download event listener timed out, but the actual file existed in Downloads and was independently loaded/compared. These intermediate failures were retained in their earlier logs.

## Historical failing artifact and limitations at that revision

Historical artifact: [`data/real-robot-review-geometry-calibration-final.json`](../data/real-robot-review-geometry-calibration-final.json), plan identity:

`f920c212f41afaa419dd77c06d66bea99f8dab86a8b05368340fed097ff2fe66`

It has a one-second explicit approach, the original nine-second shot unchanged, and a one-second departure. It begins at the reviewed original first joint pose, **not** the current measured arm pose. A different supported initial pose requires a separately reviewed approach revision. Earlier generated `real-robot-review-plan.json` and `real-robot-review-final.json` are superseded/stale; do not execute them.

| Current calculation | Value | Meaning |
|---|---:|---|
| Phone full-position residual | 10.822 cm maximum | Fails the existing 2 cm fidelity screen |
| Light full-position residual | 10.232 cm maximum | Fails the existing 2 cm fidelity screen |
| Optical aim / horizon preference | 0.024° / 0.766° maximum | Model orientation screens; no measured lens calibration |
| Revised reference speed / acceleration / piecewise jerk | 0.234958 rad/s / 0.419296 rad/s² / 4.994357 rad/s³ | Continuous numerical reference; mechanical response unmeasured |
| Complete-FK display step | ≤40 ms | Midpoint sampled differences: 2.950 mm maximum body position, 0.004698 rad joint; not a continuous/physical tracking bound |
| Conservative nominal swept clearance | 18.911 mm lower bound | Sampled bound 26.197 mm, ≤20 ms geometry sampling, relative speed bound 0.728611 m/s; conditional on modeled geometry |
| Assumed static support margin | 0.228 m | Static COM/contact screen only; cannot establish dynamic tipping or slip |
| Assumed peak phone/light elbow gravity demand | 0.913 / 0.901 N·m | Model masses; installed payload/voltage/thermal capacity unqualified |
| Sampled payload-demand screen | 1.004 N·m versus assumed 0.800 | Unresolved assumed load margin; slowing the trajectory does not eliminate gravity |
| Cart predicted travel | 1.2375 m for the original nine seconds | Provisional equal-wheel model only; known real drift, no independent speed/stop table |

[`real-robot-review-geometry-calibration-final-preflight.json`](../data/verification/real-robot-review-geometry-calibration-final-preflight.json) lists exact blockers. `plan_valid:true` means numerical motion screens pass. `shot_fidelity_passed:false`, `live_execution_allowed:false` and physical movement unverified remain explicit. No thresholds were relaxed and no missing measurement was set true.

The two revised endpoint poses are accepted by the configured calibration. The current raw phone shoulder-lift position 3176 still blocks activation because its unchanged maximum is 3161. The adapter rejects it; it does not clamp or invent another revision. Support the phone arm with the cart parked, move that joint inside its configured range while torque is off, and re-read before any activation.

The operator has tape-measured travel and final-heading measurement available. The implementation accepts independent x/y/yaw endpoint data with uncertainty; tape data alone cannot establish full path, timing/skew or stop time. Full pose observation series and stopping evidence must support those claims. Acceptance tolerances are deliberately undeclared in the generated templates until chosen before a trial.

## Source ownership and recovery

Before this implementation, unique source/tests/docs/configuration were copied to `data/recovery/real-robot-motion-20260912-180052-637/` with matching relative paths. The retired cart audit script also has a specifically saved copy at that snapshot's root `verify_cart_audit.py`. No reset, stash, commit, recursive cleanup or overwrite of unrelated user work was performed. The earlier shared-hold recovery is `data/recovery/hardware-hold-20260912-174723-533/`.

| Before | Current owner / behavior |
|---|---|
| Product `adapters/simulated.py`, fake composition in `motion/devices.py` and `service.py` | No production fake branch; isolated doubles in `tests/support/devices.py` for narrow software faults |
| Root dry-run and robot/cart replay/timing simulated completion | Offline canonical plan checks only; historical harmless names stay non-actuating |
| Product permissive `simulated_limits` | Removed; deliberately unmeasured values only in test support |
| Fake whole-robot/“real feedback” completion tests and cart-audit fake benchmark | Replaced/retired; independent arithmetic and scoped injected tests retained, real physical evidence separately recorded |
| Different spline, linear runtime and interpolated world-mesh paths | `planning/curve.py` plus existing `simulation.robot.pose_frame`; preview/dispatch share evaluation |
| No explicit rest transitions, incomplete full-position acceptance | New prepared revision with quintic boundaries and independent phone/light full-position screens |
| Separate commissioning hold exits before live bus ownership | Shared `adapters/fixed_pose.py`; one live owner keeps activation, motion and terminal hold |
| Per-call IO checks and incomplete feedback provenance | `motion/arm.py` complete-cycle policy and `adapters/lerobot_arm.py` raw intervals/status/acknowledgments |
| Provisional speed invented for additional cart command experiments | Exact requested UART retained; unsupported travel prediction stays null |
| Stale generic blockers and transport-only acceptance | Capability evidence, measured setup and `motion/measurements.py` independent assessment |
| Repeated scene proxy definitions | Shared `configs/scene.json` for rendering and nominal geometry screens |

[Source change manifest](../data/verification/real-robot-source-changes.json) compares saved files with this implementation, rather than attributing the entire pre-existing dirty Git tree to this task. The [parameter inventory](calibration-inventory.md) includes original calibration hashes and remaining physical data. Dated earlier audits carry current-status notices; their historical observations were preserved.

## Operator continuation

The complete commands are in [robot motion execution](robot-motion-execution.md), and the physical sequence is in [the runbook](hardware-test-runbook.md). The smallest next physical action is a supported compact in-range setup and fresh inspection. Then complete measured operating/response/stop data and predeclared tolerances, revise the failing shot request, review the exact final plan, and authorize one bounded full-robot trial. No fresh actuation or automatic repeat was inferred from the earlier hold authorizations.
