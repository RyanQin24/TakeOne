# Cart-only software verification — 2026-09-12

The cart planner, timed runner and operator commands are implemented. The real cart and arms were not connected or actuated during this verification. This evidence supports software behavior and one host scheduling observation, not physical path accuracy or a worst-case real-time guarantee.

## Automated checks

The required `scripts/TakeOne.ps1 -Command test` was invoked by absolute path from `C:\` and completed successfully:

| Check | Result |
|---|---|
| Product tests | 52 passed, including 21 cart planning/runtime tests |
| Simulation regressions | 22 passed |
| JavaScript coordination / model tests | 9 passed |
| JavaScript syntax | Passed |
| Ruff lint and formatting | Passed |
| Existing LeRobot preservation check | 1,092 files checked; no failures |

The cart tests cover matching an actual simulator export, rejecting stale or changed schedules, exact four-second predicted travel, uncommandable path rejection, and separating general movement calculation from the first live-test limits. Scheduler tests cover nonuniform command boundaries, early wakeups, slow/partial writes, clock regression, cancellation, USB identity checks and shutdown failures. An injected 80 ms host stall faults the run and permits only subsequent zero requests; it never catches up or resumes nonzero commands. These are injected software conditions, not deliberately triggered hardware faults.

Machine-readable check results and logs are in [the verification summary](../data/verification/summary.json); the preserved cart-specific result is [cart-runtime-results.json](../data/verification/cart-runtime-results.json).

## Prepared plan and execution evidence

[The four-second candidate](../data/cart-plan-4s.json) uses the same drive calculator as the simulator. Its predicted equal wheel travel is 0.55 m with zero yaw, conditional on the current provisional speed map. Its plan ID is `f55fbfda8fbbf9a958dd58da1de89f57063c358ff8899b6cfa5ee6159fe274ef`. Current code/configuration hashes are bound into the plan; a later source change invalidates it and requires re-preparation.

Both runs completed 213 in-memory writes, including 200 nonzero commands and the explicit zero windows. Neither opened a serial port.

| Run | Largest host write gap | Largest lateness | Transport |
|---|---:|---:|---|
| Virtual-time replay | 20.000 ms | 0.000 ms | Simulated |
| Real-clock timing check | 21.256 ms | 1.420 ms | Simulated |

The longest real-clock transport call was 0.202 ms; this measures an in-memory call, not a USB write. The run remained inside the configured 40 ms host-gap threshold and 10 ms lateness threshold. This single short run cannot establish a worst-case bound under future CPU, USB or operating-system load.

Full event records: [virtual replay](../data/runs/20260912T140545Z-cart-ec6da0bb/report.json) and [real-clock timing](../data/runs/20260912T140546Z-cart-b0eec3bb/report.json). Requested packets, host write completion and unverified physical behavior are labeled separately.

## What this does not prove

- Firmware receipt timing or the reported watchdog's physical brake/release behavior.
- Actual distance, turning radius, acceleration, stopping distance, friction or slip.
- Correct cart identity/polarity on the day of the test.
- Any arm actuation, loaded arm capability or combined-shot feasibility.

Follow [the cart testing guide](cart-live-testing.md) for the first explicit supervised measurement. The [change and recovery manifest](cart-runtime-change-manifest.json) records the source changes and verified original copies in the pre-change recovery archive.
