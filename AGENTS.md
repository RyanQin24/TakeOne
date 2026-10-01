# TakeOne working conventions

- Read the root README and relevant docs before changing subsystem boundaries. LeRobot has its own AGENTS.md; preserve its independent repository and user changes.
- Product code belongs in packages/takeone. The app consumes it. No UI imports in drivers, no serial imports in simulation, and no hardware side effects during import/test discovery.
- Core contracts use SI units, explicit coordinate frames, monotonic timestamps and named arm roles. URDF radians require a verified mapping before servo-degree conversion. Preserve phone wrist-roll ID 6 and light wrist-roll ID 5.
- Preserve calibration originals byte-for-byte. Audit snapshots are evidence, not live calibration or safe limits. Measured, assumed, simulated and transmitted values must remain distinguishable.
- Run scripts/TakeOne.ps1 -Command test after relevant changes. Hardware tests are opt-in human-supervised work, never part of automatic verification.
- Do not alter hardware, firmware, torque or calibration for filesystem tasks. Retain known physical blockers rather than inventing approvals or measurement results.
- Dependencies for the simulator are lightweight and pinned. LeRobot's training environment is independent. Avoid full upstream test suites or GPU installs for unrelated product changes.
- Source refactors require a before/after mapping and recovery for unique content. Do not delete apps/rehearsal/dist as a cache. No recursive move/delete without checking absolute paths inside the intended workspace.
- Keep docs, launchers and evidence reproducible from another working directory. Never claim hardware readiness from a simulated test.
