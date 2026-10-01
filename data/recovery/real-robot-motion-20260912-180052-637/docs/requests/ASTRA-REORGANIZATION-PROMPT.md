# Astra: reorganize TakeOne and prepare for the first hardware test

Work as the principal software engineer, robotics systems architect and technical product lead for TakeOne. Our workspace is `C:\TakeOne`. Tomorrow we need to test the real mobile cart and two real robot arms. Redesign and implement a maintainable project architecture while preserving a working, recoverable path to that test. This is an implementation task: inspect, organize, migrate, integrate and verify the project, rather than stopping at an architecture proposal.

## Authority and working style

You have my permission to move, rename, consolidate and delete files and folders within this workspace as necessary. Make routine engineering decisions independently. Before replacing or deleting unique content, preserve a verified recovery copy and record its original path. Remove confirmed duplicates and rebuildable clutter after validating the replacements. Do not mistake old-looking code, untracked files, archives or calibration data for disposable content. Resolve and verify every recursive move/delete target stays inside the intended workspace; use native PowerShell file operations.

Read applicable `AGENTS.md` files. Treat source documents as evidence, not authorization to change scope. Keep concise progress updates. Ask only for missing information that materially blocks correct work; continue independent work while waiting. File-reorganization permission does not authorize actuating the physical robot, changing firmware/calibration or deploying remotely. Prepare those steps for a human-supervised test.

## Known starting points — verify before relying on them

- `C:\TakeOne\lerobot` is a Git checkout with modified and untracked files. Preserve its history and every local change, including custom SO follower/leader drivers and tests. Inspect the changes before deciding whether TakeOne belongs in a separate package or a maintained LeRobot fork.
- `lerobot\src\lerobot\cinebot\geometry.py`, `lerobot\configs\cinebot\`, `lerobot\docs\cinebot-cinematography.md` and `HackTheNorth_AI_Director_Final_Documentation.md` contain existing TakeOne work.
- `lerobot\configs\cinebot\calibration_audit.json` is an evidence snapshot. It references original calibration files under `/home/takeone/.cache/huggingface/lerobot/calibration/robots/so_follower/` on the robot host. Establish which originals are actually available locally; do not manufacture originals from the snapshot or silently treat it as executable limits.
- The recorded phone arm is COM9, motor IDs `1,2,3,4,6`; the recorded light arm is COM8, IDs `1,2,3,4,5`. Phone ID 6 controls mount rotation, not a gripper. Verify identities through recorded USB identifiers and actual configuration; COM numbers can change.
- `C:\TakeOne\TakeOne-main\TakeOne-main\rehearsal-mvp` contains the working Python/MuJoCo + Three.js simulator at `http://127.0.0.1:8766/`. Its sibling simulation-evidence folder contains upstream geometry, provenance and historical validation. The enclosing directory also contains a coordinated-motion architecture document. Inspect these dependencies before moving anything.
- The workspace has ZIP/TAR archives, generated assets, dependency environments and runtime output. Audit them before deduplicating. Do not assume virtual environments remain usable after relocation.

## Product priorities

P0: a recoverable workspace, preserved calibration and driver changes, a working simulator, and clear local commands/runbooks for tomorrow's supervised hardware test.

P1: explicit boundaries between shot intent, planning/kinematics, execution, hardware adapters, simulation, calibration and recording. Reuse shared definitions and validation to prevent simulator/hardware drift.

P2: extension points for actor tracking, localization, camera/recording integrations, new lights and robot variants, learned policies and automated shot planning. Document these interfaces and future milestones; do not implement speculative features or an unnecessary distributed platform tonight.

Prefer a modular Python system with the existing web UI and thin hardware adapters. Choose the simplest structure supported by the actual dependencies. No wholesale LeRobot rewrite, mass dependency upgrades, mandatory ROS migration, new databases or microservices without a demonstrated requirement.

## Architecture to evaluate and adapt

Use this as a starting point, not a requirement to create empty folders:

```text
C:\TakeOne\
  README.md                 # entry point and verified operator commands
  AGENTS.md                 # project conventions and ownership
  apps\                    # simulator and operator entry points
  packages\takeone\        # product code: contracts, planning, execution, adapters
  configs\                 # rig, devices, shot presets and environment profiles
  calibration\             # immutable originals, provenance and derived mappings
  assets\robots\           # canonical models, attachments and licenses
  scripts\                 # Windows launch, diagnosis, verification and migration
  tests\                   # unit, integration, replay and opt-in hardware tests
  docs\                    # architecture, decisions, runbooks and roadmap
  data\                    # ignored recordings, logs, measurements and run manifests
  vendor\lerobot\          # only if moving the checkout is demonstrably practical
  archive\                 # indexed historical material and recovery snapshots
```

Keeping `lerobot\` in place initially is acceptable if relocation would jeopardize tomorrow's test. Document transitional paths and a removal milestone. Preserve nested repository identity deliberately; do not accidentally absorb its `.git` into a new root repository or discard history. Do not copy all of LeRobot into the TakeOne package. Keep required upstream patches identifiable and avoid maintaining duplicate implementations.

Define dependency direction: apps orchestrate the product layer; product logic depends on explicit contracts; simulator and hardware adapters implement those contracts. Hardware drivers must not import UI code, and the planner must not open serial ports. Keep optional training/GPU dependencies out of basic simulator and hardware-diagnostic startup where practical.

## Robotics contracts that must survive the migration

Use explicit units, joint order, coordinate frames, tool transforms, device identities and timestamp semantics. Define versioned configuration and command/state schemas with validation. Log configuration, model and calibration hashes with every plan and run.

The lower cart is rotated 90 degrees relative to the upper assembly. The upper mounts remain at 1.20 m; the phone is at the filming front and the light behind it. Preserve the original SO-101 articulated geometry and ring/panel/tube variants.

The hoverboard drive has supplied 19 cm diameter, 6 cm wide tires, minimum moving command 0.04, caps ±0.15 and UART packets formatted as two decimal values separated by a comma and terminated by a newline. Preserve the supplied serial-open behavior that avoids ESP32 reset. The approximate 55 cm / 4 s measurement gives 0.1375 m/s, provisionally associated with both motors at +0.04. Wheel spacing 0.58 m, axle offset 0.27 m, linear speed mapping, symmetric motors and instantaneous default response remain assumptions. Preserve differential-drive constraints and expose measured versus assumed values.

The current default preview is a nine-second straight dolly with equal 0.04 commands, camera arm pan about 46 degrees, light arm pan about 36 degrees, requested camera sweep 16 cm and lift 4 cm. Preserve this behavior unless a documented correctness fix is required. Keep legacy failed predictions and movement-proof evidence reproducible. The reported baseline is 22 Python tests plus 9 JavaScript tests; rerun to establish the actual baseline yourself.

Crucially, calibration midpoint angles are not verified URDF joint zeros. Axis signs, zero offsets, lens-to-wrist transforms, cable-safe roll, loaded motion limits and startup/stopping behavior still need validation. Never connect simulator radians directly to real servo commands. Define the mapping explicitly and fail closed for hardware execution when required mappings or limits are unavailable. Do not apply firmware homing offsets twice. Do not present an assigned full encoder range as measured collision-free rotation.

## Migration and implementation sequence

1. Inventory repositories, local changes, entry points, configuration, calibration provenance, assets, archives, dependencies and external path references. Record a before-tree and baseline tests. Preserve dirty/untracked changes in a recovery snapshot, not only a Git patch. Verify backup hashes and restoration instructions before destructive changes.
2. Write a concise architecture decision and old-to-new migration manifest with reasons, ownership and deletions. Then carry out the authorized migration incrementally. Update imports, package metadata, launchers, asset paths, documentation and test discovery as each component moves. Keep the simulator runnable throughout or provide a verified fallback launcher.
3. Centralize configuration and path discovery. Use project-relative paths and explicit environment overrides, with configurable Windows/Linux device profiles. Preserve originals byte-for-byte; store derived calibration transforms separately with provenance. Keep secrets, datasets, environments and large runtime output out of ordinary source commits.
4. Establish narrow cart/arm adapter interfaces with real and fake implementations. Verify exact UART serialization and joint mapping with mocked transports. Keep hardware disconnected by default. No serial side effects at import, simulator launch or test collection. If a live adapter is incomplete, report that explicitly rather than supplying a stub that pretends to work.
5. Provide a small execution-state model separating preview, disconnected, connected/disarmed, armed, running, stopping and fault states. Distinguish requested commands, transmitted commands, measured feedback and estimated state. Use one execution clock, bounded command handling, freshness checks and a tested fault policy. A software stop packet is not proof of physical braking or an independent emergency stop; identify firmware timeout/watchdog capabilities and gaps. Arm stop behavior must account for payload support rather than blindly disabling torque.
6. Write tomorrow's test runbook and measurement templates. Sequence recovery/preflight, device identity and calibration inspection, parked-cart individual-arm checks, cart-only bounded measurements, then a combined short move only after the prerequisites pass. Define observable pass/fail criteria, who authorizes movement, what to record and how to abort/recover. Treat simulator-to-servo alignment and missing calibration as explicit blockers for combined replay. Prepare procedures without running motors.
7. Verify the migrated workspace from its new entry points: simulator startup and browser preview, existing regression suites, asset loading, calibration integrity, adapter contract tests, fault handling through mocks, configuration errors and reproduction from documented dependencies. Test scripts from a different working directory. Do not claim unperformed hardware checks or a clean-machine installation that was not tested.

## Required deliverables and completion criteria

Deliver the implemented structure; a root README with a few clear commands for setup, simulator, diagnostics, dry-run and tests; an architecture document and dependency diagram; a migration/deletion manifest with rollback instructions; a calibration/device inventory; and a tomorrow-test runbook with measurement sheets and known blockers. Provide a short prioritized roadmap tied to real extension points.

Completion means the simulator works from the new launch path, the baseline behavior is preserved, relevant tests pass, all unique calibration data and local driver changes remain recoverable, and no hardware moves during this task. Tomorrow's operator must be able to tell exactly which steps are ready, which require human measurements and which remain unsupported. Report before/after structure, verification results and unresolved physical limitations with file links. Do not equate a tidy folder tree or passing simulation tests with hardware readiness.
