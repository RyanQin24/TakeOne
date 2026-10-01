# Light-arm replacement calibration, 17 September 2026

## September 20 correction: straight wrist at reset

The operator confirmed that the real light wrist and holder are straight in line
with the forearm at the usual reset pose. The prior mapping rendered a 42.022°
wrist bend at the unchanged reset count of 1669. Its −45.89010989010989° offset
preserved an older angle reference across the motor/encoder update; it did not
establish the new physical reference pose.

The wrist-flex offset is now **−3.868131868131868°**, calculated as
`(1669 - (547 + 2879) / 2) * 360 / 4095`. This maps reset count 1669 to zero
model radians. It supersedes the historical wrist-zero preservation described
below. The other joint offsets, all min/max counts, starting goals, and original
calibration files are unchanged. No firmware, torque, or goal registers were
written. The confirmation covers this wrist reference only; the full arm and
tool-transform verification flags remain false.

The preceding mapping, documentation, and regression test are preserved in
`data/recovery/light-wrist-straight-20260920/`. Reload the studio and generate new
plans because this correction changes the conversion of planned wrist angles
to encoder commands. Do not reuse plans prepared with the prior mapping.

## September 17 history

The operator reported a light-arm motor upgrade, supplied replacement encoder
limits, then revised wrist-flex minimum to 547 and supplied explicit starting
goals. After the 06:50:52 UTC inspection, the operator revised shoulder-lift
minimum from 1686 to 1684 and wrist-flex maximum from 2066 to 2879.

```python
Light_ARM_GOAL_POSITIONS = {1: 1880, 2: 2900, 3: 2472, 4: 1669, 5: 2629}
Light_ARM_Min_POSITIONS = {1: 619, 2: 1684, 3: 1308, 4: 547, 5: 1398}
Light_ARM_Max_POSITIONS = {1: 3313, 2: 4085, 3: 3511, 4: 2879, 5: 4090}
```

| Motor ID | Joint | Minimum | Maximum | Arithmetic midpoint | Shot Studio starting goal |
|---|---|---:|---:|---:|---:|
| 1 | shoulder_pan | 619 | 3313 | 1966 | 1880 |
| 2 | shoulder_lift | 1684 | 4085 | 2884.5 | 2900 |
| 3 | elbow_flex | 1308 | 3511 | 2409.5 | 2472 |
| 4 | wrist_flex | 547 | 2879 | 1713 | 1669 |
| 5 | wrist_roll | 1398 | 4090 | 2744 | 2629 |

The active representation is the existing named-joint `raw_range_overrides`
dictionary in `calibration/derived/light.json`, with both `range_min` and
`range_max` for every joint. The named-joint `raw_goal_positions` dictionary holds
the supplied goals. ArmMapping requires all five goals to be integer counts
inside the configured ranges. The shared `previs/start_pose.py::initial_counts`
uses these explicit goals for Shot Studio reset, aiming and between-shot parking;
the robot plan validator uses the same function. With no goal dictionary, it
retains the existing floor-midpoint fallback, including the phone arm.

The separate direct motor diagnostic and Motor Lab retain their explicitly
midpoint-based sweep/default pose. They still use the updated minimum and maximum
limits. Light wrist roll remains ID 5; phone wrist roll remains ID 6.

## Midpoints and model alignment

Starting goals and model zero are separate. The supplied GOAL dictionary specifies
the reset pose; it does not assert that each corresponding model joint angle is
zero. Servo-degree normalization still uses `(min + max) / 2`, with the configured
axis signs and zero offsets mapping those degrees to the nominal model.

The initial replacement calibration used midpoint-based model zero and removed
the old light-elbow endpoint correction. The subsequent wrist-flex minimum
revision changes its normalization midpoint from 1191 to 1306.5. An offset of
`-(1306.5 - 1191) * 360 / 4095 = -10.153846153846153` degrees preserves the prior
software model angle at a given encoder count. Updating a range or a starting
goal therefore does not silently redefine the model's angular reference. This
is arithmetic consistency, not a new physical alignment measurement.

The latest range revision changes the shoulder-lift midpoint from 2885.5 to
2884.5 and the wrist-flex midpoint from 1306.5 to 1713. Applying
`new_offset = old_offset - (new_midpoint - old_midpoint) * 360 / 4095` gives
shoulder-lift offset `0.08791208791208792` degrees and wrist-flex offset
`-45.89010989010989` degrees. This preserves the same software angle at a given
raw count, including the supplied starting goals. It does not establish the
physical model alignment after the operator changed the encoder reference.

The existing 2-degree planning margin remains a planning policy. Exact raw
endpoints remain accepted by the startup position check. Old visual-pose and
firmware evidence is retained as historical evidence, not applied to the upgraded
arm. `verified` and `visual_pose_match_confirmed` are false for the new mapping.
The older commissioning pipeline therefore still requires physical pose
confirmation; this update does not add or remove a gate in studio playback.

## Inspection history and operator follow-up

A separately authorized read-only inspection at 2026-09-17 06:29:33 UTC found
light wrist flex at 39, below the then-configured minimum 316. The other four
readings were in range. All five motors reported torque off, firmware limits
0..4095 and homing values different from the saved old calibration. No motor
registers were written and the snapshot was printed to the conversation only.

The operator subsequently reported realigning the encoder so the 39 anomaly
would no longer exist, and reconfirmed the new goals and minimum 547. No fresh
hardware inspection or motion was performed for that goal/minimum update.

The run started at 2026-09-17 06:48:28 UTC failed the light-arm starting-position
check with the then-active limits. Its plan's light mapping hash matched the
file at that time (`6bf7e92ffd5461134c6d0f7b520877fbb2cba60a0ba7ab02513bf51f6a001c35`).
The [worker log](../data/runs/studio-31db6b1591da80b60c0e17cc/worker.log)
records the error but omits individual light readings. The run stopped before
motion, and its historical log has not been rewritten.

A separate, authorized read-only inspection at 2026-09-17 06:50:52 UTC
(02:50:52 Toronto time) confirmed COM8 / USB serial `5A7A058801` and returned
the following readings. This table transcribes the tool output captured in the
conversation; it is not a new hardware reading or a measurement from the failed run.

| Motor ID | Joint | Captured count | Range at inspection | Result at inspection | Latest operator range |
|---|---|---:|---|---|---|
| 1 | shoulder_pan | 2972 | 619..3313 | Within range | 619..3313 |
| 2 | shoulder_lift | 1685 | 1686..4085 | 1 below minimum | 1684..4085 |
| 3 | elbow_flex | 3509 | 1308..3511 | Within range | 1308..3511 |
| 4 | wrist_flex | 2599 | 547..2066 | 533 above maximum | 547..2879 |
| 5 | wrist_roll | 2630 | 1398..4090 | Within range | 1398..4090 |

All five motors reported torque disabled and firmware limits 0..4095.
Wrist-flex firmware homing offset was -989, changed from the earlier 1502.
The earlier 39 reading is historical. The new snapshot confirms changed
encoder readings and homing settings, without establishing physical endpoint
or model alignment. No motor settings were written during either inspection.

The operator then supplied the current min/max dictionaries shown above. All
five captured counts pass the exact raw starting-range check under these revised
limits. This is an offline comparison with that snapshot; no new hardware
inspection, simulation or playback is part of this range update.

## Preserved files and hardware scope

Both original calibration JSON files remain byte-for-byte unchanged. The phone
derived mapping is also unchanged. The light registry keeps the earlier wrist
revision in `configured_revision_history` and identifies this software range
replacement separately. No torque, goal, firmware range or homing register was
written by these software updates. The saved homing values and driver model are
retained compatibility data, not verified calibration of the replacement motors.

Do not use the old maximum-only firmware revision command to install these
ranges: it supports only increasing maxima and deliberately rejects replacement
minima. The operator's supplied ranges have been installed in software only.

## Loading the update

Restart the running simulator to clear cached model/mapping state, reload the
browser page and prepare a new robot plan. Existing prepared plans and raw-count
exports describe the old calibration and should not be replayed after this change.
Reopening saved shot settings and preparing them again uses the new mapping.

The initial range replacement passed 21 focused tests. The goal/minimum follow-up
passed all 24 focused tests and source lint/format checks. It adds validation of explicit goals, invalid/incomplete goals, independent returned
dictionaries, midpoint fallback and the aiming transition's exact start/end
counts. Focused validation uses `tests.test_calibration_revision`,
`tests.test_arm_commission`, and `tests.test_motor_panel.MotorTableTests` without
starting the simulator or opening hardware ports. The full simulation suite and
physical playback remain unexecuted, respecting the operator's instruction not
to run the simulation.

SHA-256 checks confirm both original calibration files and the phone derived
mapping are unchanged. No motor-register writes or hardware reads were performed
during the goal/minimum follow-up.

The latest shoulder-lift minimum / wrist-flex maximum revision also passed all
24 focused tests. These checks include accepting the captured 06:50:52 UTC
positions under the real player's loaded raw limits, rejecting values outside
the revised endpoints, retaining the explicit goals, and preserving the
software angle-to-count mapping. This validation opened no hardware ports and
ran no simulation. The original calibration files and phone mapping retain
their previous SHA-256 hashes.
