# TakeOne

One cart, an independent phone arm, and an independent light arm. This workspace now separates shot planning, the simulator, device adapters, calibration evidence and run records.

**Cart audit after the reverse-direction pull:** the front powered-wheel geometry is preserved. Equal commands are an open-loop test, not proof of straight physical travel; real drift has been reported. Independent wheel-response tables and a non-actuating `analyze-drift` command are now part of the planning system. The timed sender yields instead of busy-spinning, with the same watchdog limits. See [the audit and measurement workflow](docs/cart-audit-2026-09-12.md). No measured motor correction has been invented or activated.

**Implemented:** local simulation, offline diagnostics, coordinated cart/phone/light playback, read-only LeRobot arm inspection, nominal SO101 midpoint mapping, and an explicit supported current-position hold test. The original arm files are restored, and read-only inspection confirmed both connected arms' firmware calibrations match. The operator also confirmed the nominal model pose matches the observed joint positions. Tool transforms, loaded limits, directional checks and combined movement remain to be qualified. See [robot motion execution](docs/robot-motion-execution.md) and [arm commissioning](docs/arm-commissioning.md).

**Arm holding correction:** the operator supplied a working Feetech script that sets current-position goals, enables torque and waits for Enter. The earlier TakeOne observation released torque at 1 degree of drift, which explains its premature shutdowns. Use `takeone.motion.hold --until-enter` for the corresponding supervised stationary hold: acknowledged per-motor writes through LeRobot, fixed current targets, drift reporting and operator release. The old `--observe` command remains a timed drift test. The manual mode still releases on health/communication faults and requires support/catch and cart motor power off. See [the working-script comparison](docs/arm-commissioning.md#hold-until-enter-following-the-working-script).

**Director parts 01–02:** open `/director.html` for saved briefs, editable scripts, dialogue choices and shot proposals. The interface includes three clearly labelled editorial samples and a manual writing workflow. A bounded OpenAI Responses adapter is implemented for live planning; `OPENAI_API_KEY` and explicit enablement in `configs/director-planning.json` are required. Live model quality/access remain unverified. Full synchronized previs, camera capture, voice and Director-controlled robot movement are later packages. See the [creative planning implementation record](docs/ai-director/implementation/02-creative-planning.md) and [engineering prompt](docs/requests/ASTRA-ENGINEERING-PROMPT.md).

## Start here

Run these commands in PowerShell from `C:\TakeOne`. Scripts also work when invoked by absolute path from another directory.

```powershell
# Install/reconcile the lightweight environment and existing web dependency.
.\scripts\Setup.ps1

# Start the simulator; open http://127.0.0.1:8766/ . Ctrl+C stops it.
.\scripts\TakeOne.ps1 -Command simulator

# Use another port if an existing simulator is running.
.\scripts\TakeOne.ps1 -Command simulator -Port 8768

# Inspect saved device identities, evidence hashes and readiness blockers; no ports open.
.\scripts\TakeOne.ps1 -Command diagnose

# Compile and execute the complete default shot against fake adapters; no ports open.
.\scripts\TakeOne.ps1 -Command dry-run

# Product contracts, original simulation regressions and web/GLB checks.
.\scripts\TakeOne.ps1 -Command test
```

Setup requires Python 3.13, uv and Node/npm. It leaves the separate LeRobot Python 3.12 environment alone. The simulator lock file pins the previously working versions; the root package installs editable. The root environment was freshly built and checked on this machine. A clean machine and the Linux robot host have not been tested. Linux paths in the device profile are recorded identities, not evidence of a successful connection.

The separate [cart-only commissioning workflow](docs/cart-live-testing.md) provides calculated plans, offline replay, a host timing test and an explicit supervised `live-test` command. Install the `uart` extra only in the intended hardware environment. The root dry-run remains fake; the simulator never opens a motor port. Do not run LeRobot's normal `connect()` expecting a read-only diagnostic: it configures motors. Follow the test runbook before hardware work.

The simulator's **Prepare robot motion** control exports the same solved joint angles and cart commands for the complete robot. `python -m takeone.motion.cli` provides `prepare`, `preflight`, `replay`, `timing` and explicit supervised `live` commands. There is one playback service; offline runs select simulated devices explicitly and never serve as a fallback for failed hardware.

## Tomorrow's test

Read [the hardware-test runbook](docs/hardware-test-runbook.md), [device/calibration inventory](docs/calibration-inventory.md), and [the recovery instructions](docs/migration-and-recovery.md). Start with parked-cart, individually supervised checks. The simulator's 9-second move is a continuous preview segment and is not an approved start-to-stop hardware trajectory. Its estimated payload margin also fails the current assumed threshold.

The corrected layout has large powered front wheels and small passive rear swivel casters; upper mounts and arm geometry are unchanged. The user clarified that the large wheels should lead, so `cart.reverse_enabled` is now false. New default plans use equal `+0.04,+0.04` logical/UART commands and predict travel toward the powered front, with passive casters trailing. Physical wiring polarity remains to be confirmed. The requested camera sweep is 16 cm with 4 cm lift. Its editable `dollyOffset` locates the cart-center path at world Y = 0.40 m at mid-shot. Restart an existing simulator after this setting changes and export a new plan.

The cart's reported firmware watchdog activates failsafe runaway brakes after 60 ms without commands. The cart runner targets 20 ms command intervals, detects late writes, and records host timing separately from physical response. Its live-test envelope permits only equal commands in the globally configured direction: `0.04` for at most four seconds, or the operator-requested `0.05` for at most two seconds, with supported stationary arms. `python -m takeone.cart.cli prepare --command 0.05 --duration 2 --output NEW.json` prepares the explicit command experiment without changing the speed calibration or the default simulator shot. The [architecture review](docs/architecture-review-2026-09-12.md) records what the current implementation does and where it falls short of the earlier product design, including unresolved tool-position residuals.

## Where things live

| Path | Owns |
|---|---|
| `apps/rehearsal/` | Local API, authored Three.js UI, static GLBs and existing simulation verification |
| `packages/takeone/` | Shared contracts, configuration, protocol, planner, simulation, execution and adapters |
| `configs/` | Active rig, shot and device profiles; historical imports marked separately |
| `calibration/` | Byte-preserved audit and restored originals; nominal midpoint mappings with static-pose evidence and pending full qualification |
| `assets/robots/` | Active geometry and intact original validation/upstream assets with licenses |
| `scripts/`, `tests/` | Operator commands, migration/recovery tooling and product contract tests |
| `data/` | Saved diagnostics, run manifests/events, measurements and verification logs |
| `docs/` | Architecture, roadmap, runbook, templates and migration record |
| `lerobot/` | Complete LeRobot source and local modifications, included in this repository |
| `archive/` | Verified recovery snapshot and original distributions/historical enclosing material |

[Architecture and future milestones](docs/architecture.md) define package responsibilities and extension points. LeRobot's working files are now versioned directly in this repository, so a normal clone includes the arm drivers and project-specific changes. The original local `lerobot/.git` repository and environment remain intact; a fresh clone receives the source without a nested Git database. Saved project data and archives are included. Installed environments, caches and credentials remain excluded. See [repository contents and cloning](docs/repository-contents.md) for Git LFS, provenance and byte-preserving checkout instructions.

## Development

The simulator imports the installed TakeOne package directly. Compatibility shims and the sys.path bootstrap have been removed from the active app. Its `dist/` is authored source, not disposable build output. After changing models, run `.venv/Scripts/python.exe -m takeone.simulation.model`, followed by `node apps/rehearsal/export_models.mjs` and the tests. Root commands use `.venv`; there is no supported relocated environment in the app folder.

[Arm movement design](docs/arm-movement-design.md) is the code-reading guide for settings, target strategies, IK, trajectory generation and validation. Camera and light sweep/lift controls are independent. The test command includes the pinned Ruff lint and formatting checks; run setup once after updating to install the development extra. Simulation regression tests now live in `tests/simulation/` and the preserved upper-frame fixture is in `tests/fixtures/`.

Run manifests include configuration/calibration/model hashes, requested commands, transmitted packets and observation source labels. The cart UART has no measured-speed feedback. A fake observation and a successful serial write must never be presented as a measured physical movement. `TAKEONE_ROOT` can select a different complete configuration/assets checkout; it must contain the same layout. Windows/Linux device overrides belong in the versioned profiles, not hardcoded imports.
