# TAKE ONE rehearsal simulator

This application lives under `apps/rehearsal`. Start with [the root README](../../README.md). It imports the installed `takeone` package directly; no local import shims or bootstrap remain. XML/meshes live in `assets/robots`. The authored `dist/` directory is not disposable build output.

The cart now uses **offline differential-drive UART prediction**. Read [DRIVE-PROOF.md](DRIVE-PROOF.md) for equations, test evidence, measured inputs and remaining calibration needs.

## Current robot

- Lower cart rotated **90 degrees clockwise** so the powered wheels roll along local +X.
- Uprights, top deck and both SO-101 arm mounts keep their exact previous transforms. The phone remains in front of the light toward local +Y (the filming direction).
- Powered tires are **19 cm diameter × 6 cm wide**, as supplied by the user.
- Mount height stays **1.20 m**; the original SO-101 chain is not scaled. The raised optical-point witness remains about 1.701 m.
- Wheel-center spacing is provisionally **58 cm**, editable in the simulator. The powered axle is estimated to be 27 cm ahead of the cart center. Other cart dimensions, tool sizes and masses remain estimates.
- Ring, panel and tube light attachments remain selectable. GLB downloads are static inspection models; the simulator uses the articulated MuJoCo geometry plus wheel odometry.

## Run

From the workspace root, run `scripts/TakeOne.ps1 -Command simulator` and open http://127.0.0.1:8766/. The local `Start-Rehearsal.ps1` forwards to that root launcher. The root `.venv` replaces the former app environment. Restart the server after Python or model changes.

The server binds to loopback only. This simulator does not open a serial port or run the motors.

## Motion model

The supplied driver clamps left/right commands to ±0.15 and formats each to two decimals before sending `left,right` plus newline. The simulator mirrors this wire protocol, then applies the user-supplied minimum moving command of 0.04. Magnitudes below 0.04 are modeled as stalled.

The approximate measurement **55 cm / 4 s = 0.1375 m/s** is provisionally associated with both motors at +0.04. The configured `cart.reverse_enabled` mode sends -0.04 and assumes the same speed magnitude in the opposite direction. That negative-command response is not measured. Above the minimum magnitude, a linear speed map and symmetric motors are assumed. This single point does not establish the full speed curve, directional response, acceleration, braking, tire slip or caster friction. Response/braking times are editable assumptions; zero means the ideal instantaneous limit.

The powered-axle midpoint follows the wheel-derived motion. The cart-center position includes the axle offset. Blue dashes show the requested cart-center curve; orange shows the command prediction. Live readings show the transmitted command, left/right rolling speeds and axle path error. Drive-wheel rotation uses rolling distance divided by wheel radius; casters align with their local travel velocity without modeled swivel resistance.

The default is a **9-second arm-led reverse tracking move**: both motors hold -0.04, the base keeps its heading, and the cart-relative arm sweep is mirrored automatically under the same global direction setting. The actor timeline is unchanged. The camera arm pans about 45° with a requested 16 cm sweep and 4 cm mid-shot lift; the light arm pans about 35° and uses 75% of the sweep/lift. These controls are editable. Duration sets straight travel distance at the assumed minimum speed magnitude. The default passes the existing arm motion and sampled clearance screens within its continuous tracking window; startup and stopping transitions remain unvalidated.

The old 16-second smooth shot is retained in the proof as a diagnostic example. Under the provisional map its left wheel stalls and it misses the requested axle path by about **71.3 cm**. **Preview prediction** shows this failure rather than forcing the cart onto the ideal path. Failed motion/clearance checks remain visible. Preview availability is separate from `playable` feasibility in the exported data.

**Compare base-led arc** sets a mathematically consistent constant-command example under the same provisional speed map. It does not certify startup, braking, arm demand or physical motion. This example's ideal velocity jumps are not finite-force dynamics.

Motor replay runs at the original command timing. Slower actor pace affects only the actor. Adaptive actor-follow retiming and simulated obstacle/tracking-loss stops are disabled because they would invent below-minimum speeds or instant braking. Pause and scrub pause the visualization, not a physical cart. Replay ends at the recorded command window; assumed coasting beyond a final stop is reported separately.

The arm solver follows the predicted cart poses. It retains its original joint, aim, sampled clearance and inverse-dynamics screens. Those arm-demand estimates are not full cart dynamics, impact, traction or stability validation.

## Files and reproduction

- `python -m takeone.simulation.model`: reproduces the three robot XML variants and ring OBJ assets using the root environment.
- `packages/takeone/simulation/drive.py`: UART emulation, conditional motor response and powered-axle odometry.
- `packages/takeone/planning/`: validated settings, independent arm targets, IK, trajectory generation, dense forward checks and plan compilation.
- `node export_models.mjs`: rebuilds `dist/models/take-one-{ring,panel,tube}.glb` from compiled simulator geometry, centered on the cart in meters, glTF Y-up.
- From the workspace root: `.venv/Scripts/python.exe apps/rehearsal/verify_drive.py` runs 22 simulation tests and writes the current proof plus machine-readable evidence under this app's `verification/`.
- `npm test`: playback and GLB-import checks. `npm run check`: JavaScript syntax check.
- `tests/fixtures/upper_before_rotation.json` at the workspace root: saved upper-assembly transforms before the lower-cart correction.
- `verification/default-prediction.json`, `verification/legacy-orbit-prediction.json` and `verification/steady-arc-prediction.json`: full poses, timestamped UART sequence, settings, hashes and diagnostics.

`MATH-PHYSICS-AUDIT.md` is the historical pre-correction audit. `DRIVE-PROOF.md` describes the current wheel model; the older audit's cart-center spline and Ackermann-steering assumptions no longer apply.

Robot arm geometry derives from TheRobotStudio/SO-ARM100, revision eecbe3e0a9ebb23e25ad7b2759b03884c6660903, under Apache-2.0. Original source, provenance and license remain in the neighboring validation bundle's `upstream/` folder. Three.js is MIT licensed. The original evidence XML remains byte-for-byte unchanged.
