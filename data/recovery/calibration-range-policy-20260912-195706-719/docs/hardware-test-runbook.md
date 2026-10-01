# Supervised physical measurement workflow

The real cart/phone/light implementation is available. A complete physical shot remains unverified. Start with the existing calibration and hold evidence, then collect the specific missing measurements; do not redo calibration recovery or count an offline check as motor movement. The [current inventory](calibration-inventory.md) records all values, sources and remaining uncertainty.

## Present state and next physical setup

At 22:30 UTC, and again through the actual production adapter at 22:54 UTC on 12 September 2026, all ten motors replied, original calibration matched, and every torque-enable register was zero. Phone elbow read 3086 against saved maximum 3085; light wrist flex read 3204 against saved maximum 3199. With cart parked and both arms fully supported, the next operator step is to place those joints inside their saved ranges and arrange a compact clear starting pose, then obtain a fresh read-only inspection. Do not change the saved calibration or clip the readings to bypass this check. Being inside the encoder range alone does not establish a loaded cable-safe range.

The historical manual phone/light holds ended on supported release and closed their ports. The user reported the light was holding before supporting and releasing it. These are real tests at the recorded poses. They do not supply loaded speed/acceleration/jerk limits, a moving-cart stability proof, or a continuous full-robot hold session.

## Prepare the result before motion

1. Run `scripts/TakeOne.ps1 -Command test` and the offline `check`/`preflight` commands in [robot motion execution](robot-motion-execution.md). Recovered originals must still match their hashes; current motor identity/calibration must also match in actual inspection.
2. Review full phone/light position and pointing residuals. The current default misses full positions by about 10.8/9.6 cm, so it cannot qualify as the requested shot. Revise settings/targets and review the resulting candidate without weakening the position thresholds.
3. Use a new artifact with explicit approach/departure. Bind measured starting model angles if an approach from the actual pose is needed. Review the whole transition and retain the same cart timing; the runner never positions automatically.
4. Generate measurement templates. Declare acceptable cart endpoint/heading, initial placement, tool position/orientation, physical skew, stopping time/distance and observation-gap tolerances **before** measurements. Unknown values remain null.

All of those software steps are non-actuating. A successful compile or digest establishes a mathematical/content contract only. The current inspectable file is `data/real-robot-review-v2.json`, not a runnable approval.

## Qualify only the required capability

For each arm, retain the original encoder calibration and nominal model mapping. Record small supported direction checks and multiple measured poses, cable-safe ranges, actual tool transforms, installed load/COM, voltage/temperature and operating limits. Use the real motor interface and record raw feedback; do not infer capacity from mechanically supported zero drift. Full movement needs velocity, acceleration, jerk, step and tracking envelopes plus loaded hold/fault-stop behavior. A limited read-only inspection does not need all those measurements.

For the cart, USB `0001` on COM5 was observed by host enumeration; physical channel polarity and controller firmware still need verification. Measure track width and signed axle offset, then independent left/right response under the intended floor/load/caster conditions. The provisional 0.55 m in four seconds mixes transients and is not an independently measured steady response table. Explicit 0.05 command experiments now leave travel prediction unavailable when supporting measurements are absent. Do not infer reverse or additional speeds from that one observation.

The narrow cart commissioning command remains limited to equal 0.04 for at most four seconds or 0.05 for at most two seconds, currently positive commands toward the powered front wheels. It sends no arm commands. Both arms must be stationary and mechanically supported for that separate test, unless held by a separately reviewed continuous owner. Historical trial authorization does not authorize another trial. See [cart live testing](cart-live-testing.md).

Verify startup, stopping corridor and the reported 60 ms watchdog's valid-packet reset, zero/brake/latch and restart behavior using a separately reviewed supervised procedure. Measure stop time and distance; a successful zero write does not show the cart stopped. Never deliberately starve the watchdog as part of an ordinary live shot. Do not change firmware, PID, supply, torque limits or homing to make a trial pass.

Survey the shared scene and actor exclusion area, cables and loaded ground contacts/COM with uncertainty. The software's nominal swept bound and static contact polygon are useful screens; dynamic tipping, base acceleration, payload inertia and cable forces need the corresponding measurements/review.

Measure the complete three-device workload. Cart deadline policy remains 20+10+5 < 40 < 60 ms; arm complete read/write work must fit 25 ms within the 40 ms period with 12 ms dispatch allowance. Record acquisition intervals, gaps, delays and observed physical lag/skew. An injected test and a common host epoch cannot establish physical simultaneity.

`configs/motion-evidence.json` lists the five exact qualification categories and references structured measurement files with source hashes. `configs/arm-execution.json` contains evidence-bound operating limits. Missing data is a specific remaining measurement, not a reason to turn a generic boolean on.

## One authorized finite trial

When the plan and required capabilities pass, prepare and review the final artifact again. Place the cart's marked origin in the declared world frame and record fresh measured x/y/yaw, uncertainty, floor/load, operator and physical support/abort arrangement in its setup file. Both actual arm poses must match the reviewed first pose. Leave a defined stopping corridor and a catch/support arrangement appropriate to the qualified test. Use the physical abort if behavior is unexpected; a UI pause or process exit is not a mechanical stop.

The operator must be present and authorize that exact motion. The live command shown in the execution guide checks the complete identity/setup and opens one owner per bus. Both arms capture fixed goals and activate with Goal → Torque Enable → same Goal, remain active through cart motion, settle, and retain the terminal pose. During the session `abort` cancels travel while applying the bounded stop/hold policy. Support both arms fully before `release`, which requests and verifies torque-off on all ten motors. There is no automatic loaded-arm release, reconnect, re-enable or resume.

A readiness, feedback or timing failure prevents continuing the full run. Cart zero and arm hold attempts are recorded; failed communication leaves physical state uncertain. Never report a killed process, closed port or sent packet as stopping evidence. Do not repeat or broaden a physical trial automatically.

## Record and assess the actual result

The operator's available method is tape-measured travel and final heading. Measure forward travel **and lateral displacement** of the marked cart origin and final yaw relative to the same world reference; record instrument uncertainty, method/time and source evidence. This supports endpoint error and drift. It does not measure the time history, physical response skew or stopping time. Obtain additional time-aligned cart/tool observations for those claims, or leave them unavailable.

Keep the generated plan, setup, actual device traces, source/config/calibration hashes, payload/floor and independent observations. `motion.cli assess` accepts actual run records and those observations without opening ports. It reports command completeness, actual sampled arm tracking/settling, independent cart/tool results, stopping and coordination separately. Missing measurements cannot be replaced with predicted odometry. One passing trial does not establish repeatability; any later repeat requires its own operator-authorized setup and report.
