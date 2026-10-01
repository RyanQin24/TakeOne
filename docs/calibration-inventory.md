# Calibration, geometry and remaining measurements

## Current light-arm replacement calibration, 17 September 2026

The upgraded light arm uses the operator-supplied min/max pairs for IDs 1-5:
`619..3313`, `1684..4085`, `1308..3511`, `547..2879`, and `1398..4090`.
They are active in `calibration/derived/light.json`. The original files and phone
mapping are preserved. The operator's explicit Shot Studio starting goals are
`1880, 2900, 2472, 1669, 2629`. They are separate from the angle-normalization
midpoints. Following the operator's encoder realignment, the read-only inspection
at 06:50:52 UTC found counts `2972, 1685, 3509, 2599, 2630`. All five are inside
these latest operator-supplied limits; shoulder lift and wrist flex were outside
the limits active during that inspection. Firmware calibration still differs
from the saved original. No fresh reading or hardware-setting write was performed
for this range update. See [the update record](light-arm-calibration-2026-09-17.md).

## Historical calibration and measurements before the upgrade

The original calibration files are present, hash checked and reusable. The operator-authorized phone elbow maximum 3086 and light wrist-flex maximum 3204 are now active in the derived mappings and real controllers. The two original files remain byte-for-byte unchanged. A post-revision inspection received replies from all ten motors, matched the configured calibrations, read torque off throughout, sent no motion command and closed both ports. Evidence: [phone revision](../data/phone-calibration-max-revision-20260912.json), [light revision](../data/light-calibration-max-revision-20260912.json), and [post-revision inspection](../data/arm-inspection-after-max-revision-20260912.json).

The earlier COM9 no-reply result at 21:47 UTC is preserved as history; it does not describe the later successful inspection.

| Parameter | Value and units/frame | Source and evidence date | Uncertainty / qualification | Enables |
|---|---|---|---|---|
| Phone adapter/joints | COM9, USB `5B14111456`, IDs 1,2,3,4,6 | Host inventory and actual replies, 2026-09-12 | Observed identity; rechecked at connection | Correct real bus and role |
| Light adapter/joints | COM8, USB `5A7A058801`, IDs 1,2,3,4,5 | Host inventory and actual replies, 2026-09-12 | Observed identity; rechecked at connection | Correct real bus and role |
| Cart adapter | COM5, 115200 baud, USB `0001` (CP210x) | Host USB inventory, 2026-09-12 | Host enumeration only; firmware/polarity unverified | Profile identity populated; live matching still required |
| Phone original | `originals/arm_5B14111456.json` | Recovered 2026-09-12 19:51 UTC; firmware match at 22:30 UTC | Byte identity, not loaded limits | Encoder/degree arithmetic |
| Light original | `originals/arm_5A7A058801.json` | Same recovery and fresh match | Byte identity, not loaded limits | Encoder/degree arithmetic |
| Nominal mapping, both arms | signs `[1,1,1,1,1]`, additional offsets `[0,0,0,0,0]` degrees | Standard model convention; operator visual pose correspondence, 2026-09-12 20:29 UTC | Directional/spatial uncertainty unmeasured; `verified:false` | Nominal model calculations |
| Raw angular scale | 4096 positions; degree formula uses 4095; `int` truncation | Installed LeRobot/SDK STS3215 model/table inspected 2026-09-12 | < one encoder count conversion error; backlash separate | One explicit raw writer/conversion boundary |
| Firmware calibration | All drive/homing/ranges match the configured revision; phone elbow max 3086, light wrist-flex max 3204 | Acknowledged writes and full readback, 2026-09-12 20:17 EDT | Original files retain 3085/3199; two explicit overrides are active | Reject incompatible configuration |
| Firmware mode/torque | Position mode 0, Phase 12, Torque_Enable 0 for all ten | Same actual inspection | Momentary register state, not mechanical support | Valid diagnostic baseline |
| Joint position limits | `range_source: calibration` for both arms; bounds derive from original data plus two recorded overrides | Operator instruction and applied revision, 2026-09-12 | Ideal cables and mechanical stops are stated assumptions; no second range table required | Defines movement target bounds |
| Loaded motion limits | Velocity, acceleration, jerk, step and tracking limits unavailable | `arm-execution.json`, 2026-09-12 | Missing actual payload/cable/thermal evidence | Required for dynamic execution |
| Phone stationary hold | 30.911 s, 531 samples; fixed goal/on/same goal/off acknowledgments | `phone-live-hold-20260912-175308-157.json` | Raw feedback; loaded capacity not established | Verified real hold-command sequence |
| Light stationary hold | 50.650 s, 898 samples; operator said “Holding; arm supported now—release torque” | `light-live-hold-20260912-175631-493.json` and operator sidecar | Holding observed at that pose; not all-range qualification | Real hold evidence for tested configuration |
| Wheel radius/width | 0.095 / 0.060 m | User dimensions in rig config; provenance date not recorded | Loaded rolling radius uncertainty unavailable | Nominal kinematics |
| Powered track/axle offset | 0.58 m track; axle at cart X=-0.27 m | Model estimates; topology confirmed 2026-09-12 | Must measure on loaded cart | Axle/chassis transform and yaw calculation |
| Rear casters | X=+0.32 m, track 0.4524 m, radius 0.047 m, trail 0.025 m | Current model estimates, reviewed 2026-09-12 | Swivel/drag/contact unmeasured | Nominal rendering and conservative static contact bound |
| Upper mounts | phone `[0,+0.23,1.23]`, light `[0,-0.23,1.23]` m in cart | User-measured arm platform height, 2026-09-12 | Arm chain remains unscaled; extrinsic uncertainty not measured | Nominal world-to-tool chain |
| Maximum extended height | 1.80 m above floor | User measurement, 2026-09-12 | Physical envelope; not substituted for a lens-site FK measurement | Height-envelope display and setup review |
| Horizontal arm extension | 0.34 m outward for each arm | User measurement, 2026-09-12 | Physical envelope; not used to rescale the original SO101 links | Reach-envelope display and setup review |
| Tool references/payload | Existing model lens/light transform, masses/inertias | Model/source provenance | Actual extrinsics, mass/COM/cables and torque margin unmeasured | Numerical prediction only |
| World/cart/drive/optical frames | World origin at actor/turn center, Z-up; cart +Y is phone-facing; drive +X=cart -X toward powered wheels; optical Z forward/X right/Y down; quaternion xyzw | Rig/model contract, 2026-09-12 | Current shot stages powered-wheel front 90° from actor-facing cart +Y | Consistent FK, cart integration and measurements |
| UART values | `left,right\n`, two decimals, ±0.15 cap; reported moving magnitude ≥0.04 | Supplied protocol/user evidence | Dimensionless; not speed or torque | Exact wire schedule |
| Active direction | `reverse_enabled:false`, positive commands request powered wheels leading | User clarification, 2026-09-12 | Wiring polarity not independently measured | Current requested direction |
| Shared cart response | Roughly 0.55 m / 4 s at 0.04, provisional 0.1375 m/s | Prior user observation; exact observation date/uncertainty unavailable | Startup/brake mixture, known real drift; independent wheel tables empty | Offline hypothesis only |
| Startup / brake times | 0 / 0 s | Default shot assumptions | Ideal instantaneous response, not measurement | Offline model only |
| Firmware watchdog | User reports 60 ms | Recorded 2026-09-12; firmware not obtained | Reset/brake/latch timing and physical stop unmeasured | Host policy constraint, not a stopping proof |
| Cart timing policy | 20 ms period, 10 ms lateness, 5 ms write, <40 ms host gap | `cart-runtime.json`, 2026-09-12 | Host budget; controller receipt unmeasured | Bounded sender |
| Arm timing policy | 40 ms period, 12 ms lateness, 25 ms whole read/write cycle, 50 ms sample age | `arm-execution.json`, 2026-09-12 | Full real three-device workload unqualified | Deadline/freshness checks |
| Scene/actor geometry | Shared nominal boxes and actor bound | `scene.json`, 2026-09-12 | Physical survey/cables/uncertainty missing | Conditional nominal swept-clearance screen |
| Independent cart observation | Tape-measured travel and final heading available | Operator answer, 2026-09-12 | Numeric measurements/uncertainty not yet supplied | Endpoint assessment; not full timed path/skew |
| Acceptance tolerances | Null in generated templates | 2026-09-12 | Must be declared before trial | Honest pass/fail criteria |

Joint order throughout is `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`. Neither ID 6 nor ID 5 denotes a gripper here.

| Joint | Phone configured range / midpoint, counts | Light configured range / midpoint, counts |
|---|---|---|
| shoulder_pan | 759..3482 / 2120.5 | 758..3481 / 2119.5 |
| shoulder_lift | 813..3161 / 1987 | 773..3198 / 1985.5 |
| elbow_flex | 883..3086 / 1984.5 | 882..3096 / 1989 |
| wrist_flex | 862..3175 / 2018.5 | 875..3204 / 2039.5 |
| wrist_roll | 0..4095 / 2047.5 | 0..4095 / 2047.5 |

Post-revision positions were phone `[2170,3176,1217,2108,3133]` and light `[1962,1994,898,3204,978]`. The two revised endpoints are now accepted. Phone shoulder lift is 3176, 15 counts above its unchanged configured maximum 3161, so the current phone pose still cannot be used for fixed-goal activation. Support the phone arm and move that joint inside its configured range before re-reading. Do not infer another endpoint change from this one observation. See [the detailed clarification](robot-motion-clarifications-2026-09-12.md).

Original SHA-256 values:

- Phone: `47a0e1711da1a0c81e9fb5c4df074282578b2015786063bc8998e41da509ec90`
- Light: `95c2b588d78964cb5ce535f74487760e126681361b126a46d37c86528022a5df`

Firmware homing already applies to Present_Position and Goal_Position. Conversion uses each configured range midpoint, applies the nominal/measured sign and additional offset once, then integer truncation. The encoded round trip must also remain inside the configured operating range. Never add firmware homing twice or replace the range midpoint with 2047.

`ArmMapping.load(require_motion=False)` supports nominal arithmetic with the recovered originals plus the recorded endpoint overrides. Motion retains a separate model-alignment check. With `range_source: calibration`, `safe_ranges_rad:null` means there is no additional range table, not that position limits are missing. Claims of lens/light spatial accuracy additionally require independent tool evidence. Root diagnosis is offline; a zero exit status establishes readable consistent files, not readiness. Exact-plan preflight is documented in [robot motion execution](robot-motion-execution.md).
