> Historical record: subsequent source, calibration and ownership changes are documented in [the current real robot implementation](real-robot-implementation-2026-09-12.md). Fake replay/timing results below remain historical software evidence and do not establish physical movement.

# Coordinated robot motion verification — 2026-09-12

**Software result:** the complete default nine-second shot completed through the cart, phone and light workers. Both simulated arms passed final settling. No serial port was opened and no physical movement was tested.

`scripts/TakeOne.ps1 -Command test` passed all seven check commands: **87 product Python tests, 26 simulation tests, 12 browser/model unit tests**, web syntax checks, Ruff checks and the integrity audit of **1,092 LeRobot files**. The test results are in `data/verification/summary.json` and `check-0.txt` through `check-6.txt`.

The new tests verify preservation of every preview joint sample and cart command, rejection of altered/stale plans, initial-pose gating, stale/future/repeated feedback rejection, joint motion limits, stalled encoder detection, final settling, role-specific motor IDs, refusal to rewrite mismatched calibration/mode, shared start time, and cancellation when an arm blocks. A 400 ms blocked-arm read causes coordinated cancellation and cart zero packets, without resuming nonzero motion.

## Nine-second host scheduling measurement

Source run: `data/runs/20260912T165950Z-robot-b90ca365/`. The artifact and report share plan ID `d5ed395a27ea4b31d48bd19c44bafa775a2fe32471908f6193bf6a89b6a4e0ca`.

| Measurement | Observed in this run |
|---|---:|
| Longest cart host write-start gap, including startup/shutdown | 21.194 ms |
| Largest cart dispatch lateness | 1.402 ms |
| Spread between the three first dispatches | 0.0484 ms |
| First dispatch after the shared epoch | 0.733–0.781 ms |
| Maximum phone joint tracking error in the lagging simulated plant | 0.803° |
| Maximum light joint tracking error in the lagging simulated plant | 0.376° |
| Both arm endpoints settled | Yes |
| Real arm/cart accuracy or braking proven | No |

These are one run's **host/simulated-device measurements**, not worst-case guarantees or measurements of the real motors. Read `data/verification/robot-motion-evidence.json` for the machine-readable summary, and the source run's `phone.json`, `light.json` and `cart.json` for timestamped traces.

The virtual-time default-shot replay also passes. The updated UI serves the 3D scene and its **Prepare robot motion** action returns a complete plan while displaying unresolved physical qualification. The local server used for UI verification is `http://127.0.0.1:8769/`.

An additional check ran in the existing LeRobot environment against its actual Feetech SDK. Using explicitly synthetic calibration, both arm ID layouts and the degree/encoder round trip passed within one encoder step. Port-open and packet-write attempts were blocked and counted: both counts remained zero. `data/verification/lerobot-api-check.json` records the result; `data/verification/check_lerobot_api.py` reproduces it. This validates the software interface, not the real calibration or motors.

Original calibration remains absent locally, both alignment templates remain unverified, and measured loaded joint envelopes, cart identity/stopping and combined-start/stop evidence remain required. Existing torque, calibration, firmware and LeRobot changes were preserved. See [the execution guide](robot-motion-execution.md) for the supervised hardware workflow and recovery mapping.
