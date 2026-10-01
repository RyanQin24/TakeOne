# Calibration ranges, simulated position error and servo control

This amendment records the operator's 12 September instructions: assume ideal cables and mechanical stops, use calibration-defined joint position limits, and leave low-level control to the servos. The operator subsequently authorized two endpoint revisions. They were applied to the real controllers and verified as described below. The measured platform height, maximum extended height and horizontal arm extension are also recorded here.

## The two encoder readings

The earlier real inspection reported phone elbow 3086 against original maximum 3085 and light wrist flex 3204 against 3199. On the installed LeRobot conversion scale these differences are approximately 0.088 degrees and 0.440 degrees. These small endpoint differences did not require a full recalibration.

The phone elbow maximum is now **3086** and the light wrist-flex maximum is now **3204** in both the active mappings and the matching STS3215 firmware registers. Each individual firmware write was acknowledged and the complete calibration was read back. Torque stayed off on all ten motors, no goal position was written, each EEPROM lock was restored, and both ports closed. The byte-preserved original files remain unchanged at 3085 and 3199. Evidence: [phone revision](../data/phone-calibration-max-revision-20260912.json), [light revision](../data/light-calibration-max-revision-20260912.json), and [post-revision inspection](../data/arm-inspection-after-max-revision-20260912.json).

LeRobot uses `(range_min + range_max) / 2` as the degree origin, so the active normalization now includes the half-count and 2.5-count midpoint changes. A full recalibration is not needed for these two explicit endpoint revisions. Recalibration would be warranted if joint direction, zero correspondence, repeatability, or multiple measured positions disagree with the model.

An encoder observation and an allowed goal serve different purposes. A diagnostic can report an observation outside a command range without changing that range. The fresh post-revision read found the phone shoulder lift at 3176, which is 15 counts above its unchanged configured maximum of 3161. The live takeover remains strict because it copies the captured raw position into Goal_Position. Support the phone arm and move that joint inside 813..3161 before another activation. This observation is not a reason to widen a third endpoint automatically.

## Where XYZ lives and why the cart looks rotated

The requested and solved phone positions are expressed in the **world frame**. Its origin is the actor/turn-center mark in the current scene, `+Z` is up, and X/Y lie on the floor. The default plan starts the cart center near world `[-1.6,-0.21875]` m. These world coordinates describe where the lens should be in the room; they are not distances from the end effector itself.

The **cart frame** moves with the robot. Its origin is the cart center, cart `+Y` points from the light arm toward the phone arm (the filming front), and cart `-X` points toward the large powered wheels. The current plan has cart yaw `-90°`, so cart `+Y` points toward world `+X` and the actor while the powered-wheel front points toward world `+Y`. That is the visible 90-degree difference: the upper phone-facing side looks at the person while the wheel-travel front is staged sideways for a dolly move.

The **optical frame** is attached to the lens or light site. Its origin is the optical point, optical `+Z` points forward, `+X` points image-right and `+Y` points image-down. It describes aim and roll. A position such as `[-1.220,0.119,1.503]` is still a world position of that optical-frame origin.

The simulator draws world X/Y/Z at the actor mark, cyan cart `+Y` for the filming side, and orange cart `-X` for the powered-wheel front. Arm mounting yaw is another transform: each complete arm chain is now rotated -90° about cart +Z at its own mount. The accepted candidate explicitly records cart world pose and the additional staging change; physical staging must match that reviewed pose rather than being inferred from the viewing angle.

## What the 10.8 cm meant

It is the distance between the requested optical position and the position obtained from the simulator's solved joint angles. It is not a measurement of the real phone and not an encoder-calibration error.

At 3.12 seconds in the previous 11-second review (2.12 seconds into its original shot), the requested phone position was `[-1.220000, 0.118531, 1.503038]` metres in the world frame. The solved position was `[-1.219358, 0.010308, 1.503035]` metres. The distance is approximately 0.108225 m, almost entirely horizontal. The original 321-frame fidelity report likewise recorded 10.822 cm maximum; the 40 ms review-frame check locates a nearby peak independently.

The existing IK residual strongly favors pointing at the actor and can sacrifice position accuracy. A five-joint arm cannot generally satisfy arbitrary XYZ, pointing and horizon constraints simultaneously. These numbers identify a shot/IK mismatch. Reproducing the joint motion displayed in the animation and achieving the originally requested optical path are different acceptance questions. Raising the two encoder maxima does not address this mismatch. No target, IK weight or fidelity threshold was changed here.

## Applied range and controller policy

Both derived arm mappings select `range_source: calibration`. The loader starts with the byte-preserved original, applies the two explicit versioned raw-range overrides, and derives position bounds from that configured calibration plus the existing axis signs and offsets. A second cable-range table is not required. The ideal-cable and mechanical-stop basis is recorded as an operator assumption, separately from measured evidence. Model-alignment verification retains its own meaning; selecting a range source does not fabricate it.

The existing adapter writes real position goals, and the servo's onboard controller handles motion toward those goals. Configured servo speed and acceleration are separate from calibration endpoints and PID gains. TakeOne does not duplicate that PID. The host still needs to check tracking and timing to establish synchronized movement: onboard control does not guarantee that an arbitrarily timed sequence can be followed under load. Existing response/derivative qualification remains separate from the position-range assumption.

The original review artifacts are retained as history. `data/real-robot-review-geometry-calibration-final.json` binds the current plan to the revised calibration, measured 1.23 m platform height and final source hashes. The intermediate `geometry-revision` files are superseded. The software verification and hardware-revision evidence are recorded separately from earlier reports.
