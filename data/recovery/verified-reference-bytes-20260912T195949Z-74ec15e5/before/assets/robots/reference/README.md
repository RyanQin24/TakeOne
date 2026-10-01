# TAKE ONE numerical validation bundle

This is an executable simulation/evidence bundle, **not a hardware driver or deployable robot controller**.

The upstream SO-101 joint frames and meshes are pinned to RobotStudio revision
`eecbe3e0a9ebb23e25ad7b2759b03884c6660903`. Each modified arm has five actuators.
Motor 6, its moving jaw and the old gripper payload are removed. Cart, holder,
payload and actuator-response assumptions are in `assumptions.json`.

Read `../TAKE-ONE-Coordinated-Motion-Architecture.md` first, especially the
simulation coverage and the retained failed payload-capacity gate.

## Reproduce

Python 3.12 on Linux with FFmpeg/FFprobe and an EGL-capable OpenGL installation
were used. Install the exact packages in `requirements.txt` in a virtual environment.

```bash
python -m pip install -r requirements.txt
MUJOCO_GL=egl OPENBLAS_NUM_THREADS=1 python simulate.py
```

The script uses its own directory for inputs and outputs. It does not access
motors or submit cloud jobs. All robot meshes needed for the test are included;
no upstream download is necessary for replay. Rendering configuration may need
adaptation on Windows/macOS, which were not tested in this session.

Outputs include the JSON metrics, model, plotted comparison, 3D rehearsal and
FFmpeg export. The `passed` fields are scenario-specific checks, not a blanket
hardware-readiness decision. One load-margin check is intentionally retained as
failed. The script exits normally after writing the complete result, even when
an individual check is false; consumers must inspect `results[*].passed`.

The three control seeds change observation noise. The open-loop baseline is
deterministic and therefore identical across seeds. Vehicle ground-contact,
real detectors, phone capture and physical transport timing are not validated.

`results/sha256.json` is a frozen archive manifest, excluding itself and Python
cache files. A rerun changes timing measurements and regenerates files.

## Files

- `build_model.py`: pinned model adaptation and declared payload/vehicle assumptions.
- `simulate.py`: executed geometry, control, physics and workflow experiments.
- `rig_5dof.xml`: generated MuJoCo scene with two five-joint arms.
- `upstream/`: original robot source files, meshes, provenance and Apache-2.0 license.
- `results/`: measured numerical results, logs, renders, videos and hash manifest.

## Attribution

The robot model/assets derive from TheRobotStudio/SO-ARM100 under Apache-2.0.
Original files and license are preserved in `upstream/`. The generated model is
modified for this task: removed grippers, replaced distal inertias/geometry,
added rigid tools, added the assumed cart and scene, and changed simulated gains.
The robot source is not a measurement of the user's modified hardware.
