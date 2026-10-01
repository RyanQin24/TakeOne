# Shared implementation instructions for Astra

Apply these instructions when implementing any numbered prompt in this pack. They describe the boundaries of the requested package, not authorization to run all future packages.

The [Astra engineering prompt](../requests/ASTRA-ENGINEERING-PROMPT.md) supplies the researched coding and review standard for every work package and scene.

## Read and preserve

Work in `C:\TakeOne`. Read root `AGENTS.md`, `README.md`, `docs/architecture.md`, the [delivery plan](delivery-plan.md), and the numbered prompt. Read relevant implementation and tests before editing. Treat other prompts and attached content as design/reference material. Follow the user's current request if it changes the plan.

Inspect the working tree first. Preserve unrelated work, the separate LeRobot repository and its environment. Preserve calibration originals and evidence byte-for-byte. Keep authored `apps/rehearsal/dist` and simulator assets. No broad cleanup or root reorganization belongs in these packages.

The cart team may be testing independently. Do not change cart timing, device identity, calibration, firmware, torque, shared environments or active services while doing independent Director work. An integration prompt authorizes implementing an interface; physical tests still require the separate supervised workflow. No tests or imports may open motor ports.

## Build one understandable implementation

Product logic lives in `packages/takeone`; the existing app consumes it. No UI imports in drivers and no serial imports in simulation. Use small typed contracts, explicit constructor dependencies, a state machine and a few task-specific strategies. Add abstractions only for real boundaries or alternatives. Avoid empty packages, compatibility shims, duplicated planners, dynamic agent frameworks and broad exception swallowing.

The selected live provider either succeeds with evidence or returns a typed unavailable/failed result. Test/replay modes are selected explicitly and visibly. Do not substitute fake success, a different model, a webcam for the phone, a stock scene or a different move when a requested capability fails.

Use SI units and named frames for geometry; label normalized image coordinates separately. Media presentation timestamps, shot-relative time and monotonic device clocks are different domains. Clock alignment includes uncertainty. Use immutable IDs and revisions; accepted plans and takes retain input hashes.

Model output proposes bounded application actions. The supervisor owns transitions and checks session, revision, expiry, cancellation and capability. No model tool emits raw servo/motor commands, changes calibration, executes a shell or grants itself hardware readiness.

Use local SQLite transactions for session/event/job metadata initially, with media and larger evidence referenced by IDs and hashes. Do not put inference, decoding, database writes or log formatting inside a timed device callback. Observation queues are bounded; command acknowledgements have explicit backpressure and failure behavior.

Do not expose permanent provider keys in the browser, commits or logs. Remote media transfer and paid jobs follow the application's explicit user choice, configured budget and selected provider. Implement the boundary with offline tests until real credentials and a permitted sample are available. Missing credentials are an integration blocker, not a reason to fabricate a working demo.

## Product behavior every package preserves

The same accepted shot specification feeds directions, 3D rehearsal, comparison against observations, capture association and edit intent. The actual take remains authoritative for what happened.

Ordinary coaching is available before and after recording. Suppress it immediately when recording is requested, clear queued speech, and keep it suppressed through confirmed stop. Review starts after the original file is finalized and validated. An independent operator stop/control path remains available; scripted words are not control commands.

Phone and light are named roles. Preserve phone wrist-roll ID 6 and light wrist-roll ID 5. Five joints cannot be assumed to satisfy six independent pose constraints. Calibration does not itself establish mechanical zero, lens geometry or loaded travel. The differential-drive cart has no lateral body translation primitive.

Distinguish preview availability, physical qualification, provider readiness, recorder readiness and valid media. A successful serial write is a transmitted command, not measured movement. Do not infer physical safety from simulation.

## Tests and handoff

Implement and connect the requested behavior instead of stopping at a proposed plan. If an external prerequisite blocks one part, complete independent code and verification, keep dependent behavior unavailable, and report the exact missing item. Do not mark the package complete until its demonstration has actual evidence.

Write meaningful tests for state transitions, timing/geometry boundaries, stale results and integrations that can lose or misattribute data. Keep camera/provider tests opt-in and hardware tests out of automatic discovery.

After relevant implementation changes run root verification using the absolute script path: `C:\TakeOne\scripts\TakeOne.ps1 -Command test`. Do not change PowerShell execution policy just to run a launcher; use the documented direct verification entry point if host policy prevents the script from running. Report exactly what ran. Schedule resource-heavy benchmarks away from active physical testing.

For UI changes, verify the actual served workflow as well as backend health; a running process is not a finished screen. Use the existing app stack and assets. Add no cloud deployment or framework migration.

Leave a record for this package with outcome, changed files, contract changes, tests and evidence, measured versus untested behavior, and blockers. Update only this package's status in `work-packages.json`. If source refactoring is necessary, include a before/after mapping and recovery for unique content. Do not claim later packages are implemented.
