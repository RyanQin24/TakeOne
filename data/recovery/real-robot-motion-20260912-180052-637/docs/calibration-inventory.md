# Calibration and device inventory

No serial ports or remote hosts were accessed during inventory. Recorded identity is not a live port probe.

| Role | Recorded Windows port | USB serial | Ordered motor IDs | Calibration ID |
|---|---|---|---|---|
| Phone | COM9 | 5B14111456 | 1, 2, 3, 4, 6 | arm_5B14111456 |
| Light | COM8 | 5A7A058801 | 1, 2, 3, 4, 5 | arm_5A7A058801 |
| Cart | COM5 in supplied wrapper | unknown | left/right UART channels | no identified speed/stop calibration |

Joint order is shoulder pan, shoulder lift, elbow flex, wrist flex, wrist roll. The phone's ID 6 is wrist roll, not a gripper. Device profiles preserve the audit's stable Linux `/dev/serial/by-id/` identifiers. The cart's Linux device is unknown and is left null rather than guessed.

`calibration/evidence/calibration_audit.json` is an exact byte copy of `lerobot/configs/cinebot/calibration_audit.json`. `calibration/registry.json` stores its hash, expected original hashes, IDs and recorded remote paths. Original robot files are recorded under `/home/takeone/.cache/huggingface/lerobot/calibration/robots/so_follower/`. They were not found in the local LeRobot configs or the two conventional Windows cache locations checked. Other host-specific locations could exist; the inventory does not claim to have searched every disk or accessed the robot host.

When originals are retrieved through an authorized operator workflow, preserve their exact bytes under `calibration/originals/`, compare with the recorded SHA-256, and update the registry with the actual relative path and provenance. A different hash must be investigated and recorded as a new calibration revision, not silently accepted as the audited file. Leave the historical snapshot unchanged.

Derived mapping templates in `calibration/derived/` are deliberately unverified and contain null signs, offsets and limits. The required convention is:

```text
servo_degrees[j] = axis_sign[j] * degrees(model_radians[j]) + zero_offset_degrees[j]
raw_target = int(servo_degrees * 4095 / 360 + (range_min + range_max) / 2)
```

Homing offsets are already applied by the firmware and must not be added again. The safe model-radian range must be physically observed with the actual payload/cables and also lie inside the encoder range after conversion. The wrist's assigned 0..4095 range does not prove safe full rotation. Geometry validation must include the camera lens/light tool transforms and model reference hash.

The original `lerobot/configs/cinebot/` remains untouched. Imported copies in `configs/reference/` are historical input for future reconciliation, not active motion definitions. That earlier preview uses optical +X forward, +Y left, +Z up, whereas the current simulator uses optical +Z forward, +X image right, +Y image down. Do not combine their transforms without an explicit frame conversion. Existing `lerobot/src/lerobot/cinebot/geometry.py` is preserved as a historical/reference implementation; TakeOne's active planner uses the MuJoCo chain.

The root diagnosis command checks evidence integrity and lists blockers; a zero diagnostic exit code means the offline files are readable and consistent, not that hardware is ready. All qualification flags remain false. The existing estimate of required arm torque exceeds the assumed 0.800 N·m allowance; that payload check has not been physically resolved.
