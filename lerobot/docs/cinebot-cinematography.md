# Cinematography for the TakeOne mobile camera rig

Research and engineering design notes, 7 September 2026.

## The physical model

TakeOne is one mobile filming platform: a cart carries an independent phone arm on COM9 and light arm on COM8. The actor or object is in the shooting area ahead of the camera, outside the cart and arm footprint. There is no requirement to put a subject between the arms. The cart supplies room-scale travel; the phone arm supplies local camera position and pointing; the other arm positions and aims a light.

The user's COM9 description is the authoritative functional mapping: the bottom joint turns left/right; the next three joints bend vertically; the final joint rotates the camera mount. COM9 uses servo IDs `1,2,3,4,6`, where ID 6 is the final mount-rotation joint. It is not a gripper opening command. COM8 uses `1,2,3,4,5`. Each arm has its own targets and feedback, with a shared execution clock.

The last joint rotating through approximately one revolution does not establish unlimited continuous rotation. The phone mount, cable routing, mechanical range, and encoder wrap handling determine usable rotation. Nor does rotating that joint necessarily roll the image about its optical center: that depends on the measured lens-to-wrist transform.

The virtual camera pose must come from the entire rig:

```text
world_to_lens = world_to_cart × cart_to_phone_base × phone_FK(q) × wrist_to_lens
world_to_light = world_to_cart × cart_to_light_base × light_FK(q) × wrist_to_light
```

For fixed cart position, five independent joints cannot generally satisfy six independent camera-pose constraints. Prioritize lens position and pointing, report residual error, and relax horizon roll only when the shot allows it. Use the actual five-joint chain and measured tool offsets with the [official SO101 model](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md). LeRobot's [Placo-based kinematics implementation](https://github.com/huggingface/lerobot/blob/main/src/lerobot/model/kinematics.py) uses weighted soft tasks; a returned joint vector therefore needs an independent forward-kinematics error check.

## Techniques this rig can explore

Professional dollies provide controlled camera translation on straight or curved tracks or a smooth floor. The American Society of Cinematographers describes slow creep-ins, short slider moves, and combined dolly/zoom shots as distinct tools with different visual effects. TakeOne's feasibility assessments below are engineering proposals for this particular rig, not claims that its current hardware already achieves professional dolly smoothness. [ASC: Tools for Camera Movement](https://theasc.com/article/shot-craft-camera-movement/).

The durations below are illustrative rehearsal targets. They are not measured hardware limits or universal filmmaking rules.

| Technique | Intended image | Cart contribution | Arm/light contribution | Illustrative take |
|---|---|---|---|---|
| Static hold | Stable composition for dialogue, product, or edit insert | Park | Phone holds; light aims independently | 3–8 s |
| Push-in / pull-out | Change perspective and apparent subject size | Straight approach or retreat | Maintain framing; small local reach correction | 4–8 s |
| Pan / tilt | Redirect view left/right or up/down | Usually parked | Solve camera direction; account for lens motion caused by offset pivots | 3–6 s |
| Small pedestal / mini-jib | Raise or lower viewpoint | Park | Coordinate the three vertical-bending joints; maintain pointing within reachable space | 4–7 s |
| Parallax reveal | Foreground slides relative to subject/background | Short translated path | Phone tracks the chosen subject | 4–8 s |
| Truck / side-track | Travel parallel to subject | Requires an achievable lateral camera path | Yaw/IK keeps subject framed | 5–10 s |
| Short arc | Change viewpoint around an external subject | Follow a feasible curved path | Compensate pointing and lighting | 6–12 s |
| Subject tracking | Preserve composition as actor walks | Follow a planned route if needed | Bounded visual correction maintains framing | 6–15 s |
| Light sweep / reveal | Change beam coverage or near-camera lighting angle | Usually parked | COM8 changes aim/position while COM9 holds or moves independently | 3–6 s |
| Dutch-angle transition | Deliberately tilt the horizon | Usually parked | Final joint contributes only if mount geometry supports the desired optical roll | 3–6 s |
| Dolly zoom | Hold subject image size while perspective changes | Approach/retreat | Requires synchronized camera zoom as well as pointing/focus control | 5–10 s |
| Montage coverage | Several different shots form an edited sequence | Reposition between takes | Record repeatable angles/details with independent lighting | Several takes |

A cart with ordinary differential drive cannot command pure sideways body motion. Its available body commands are forward velocity and yaw rate; ROS's differential-drive reference implements those components and ignores the others. A truck shot can instead use a cart aligned along the travel direction with the phone aimed sideways, provided arm limits, visibility, and the desired rig layout allow it. Otherwise a different base or repositioning strategy is required. Do not draw a sideways translation and label it physically executable before identifying the wheel arrangement. [ROS 2 differential-drive controller](https://control.ros.org/rolling/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html).

Likewise, a complete orbit is conditional on floor clearance, base steering, localization, cable routing, and arm pointing range throughout the path. The subject remains outside the moving rig's footprint. A parked cart plus base-joint rotation produces a pan with a small lens arc; it does not create a room-scale orbit. Whip pans and full revolutions should remain unavailable until measured payload dynamics and cable limits support them.

A dolly zoom requires controllable zoom. Changing distance alone makes the subject grow or shrink. A digital crop may approximate the framing effect at a resolution cost, but is not automatically equivalent to an optical zoom or a seamless phone lens switch. The ASC describes the defining coordination of translation and zoom while preserving subject image size. [ASC: Tools for Camera Movement](https://theasc.com/article/shot-craft-camera-movement/).

## What the light arm can change

Because both arms travel on the same cart, the light remains close to the camera compared with a distant actor. Its useful first skills are near-camera key/fill positioning, small height/side changes, beam aiming, and local product highlights. Re-aiming a lamp changes where its beam lands; it does not move the source to the far side of the subject.

For an illustrative geometry with camera/light at the same depth, a lateral camera-to-light baseline `b` and subject distance `d` give an angular separation of approximately `atan(b / d)`. A hypothetical 0.6 m baseline is about 17° at 2 m and 9° at 4 m. These are example calculations, not measured rig dimensions. Strong side or back light on a distant person generally needs a separate light position, environmental light, or moving the whole rig to another viewpoint. The simulator should show this geometry instead of suggesting that a wrist rotation creates a backlight.

## Montage is an editing plan

Montage combines shots to create rhythm, compress events, or express an association. It is not a motor trajectory. The BFI's discussion of Eisenstein illustrates how the relationship between edited images creates meaning beyond an individual image. [BFI: Where to begin with Sergei Eisenstein](https://www.bfi.org.uk/features/where-begin-sergei-eisenstein).

An illustrative product or actor introduction can use these five takes:

| Take | Capture | Motion | Edited segment |
|---|---|---|---|
| 1 | Wide establishing image | Parked hold | 3 s |
| 2 | Medium view | Short cart push-in with gentle framing correction | 4 s |
| 3 | Detail of hands/product | Cart repositioned while recording is stopped; parked close view | 2 s |
| 4 | Three-quarter reveal | Separate setup, short feasible parallax path; light aims across detail | 4 s |
| 5 | Hero composition | Parked hold or small pedestal | 3 s |

This example produces a 16-second edit. Each take also needs lead-in/out handles, settling, possible retries, and any between-take repositioning. Capture time is longer than edit time. Cuts may switch abruptly between already recorded views; the live rig must physically travel between setups with recording stopped. A simulator should expose `REPOSITION`, `SETTLE`, `RECORD`, and `CUT` states so a montage does not hide impossible continuous motion.

## Timing and calibration evidence

Calibration files identify servo ranges and reference offsets. They do not measure maximum payload speed, acceleration, jerk, stopping distance, backlash, or cinematic stability. They also do not by themselves establish the world-space workspace or the highest possible lens position. Those require a validated geometry model, mount transforms, base height, and constraints for payloads and cables.

The planner should generate the camera path first, solve successive IK samples using the previous solution, validate the achieved camera path, and then assign time under measured limits. Ruckig supports velocity, acceleration, and jerk constraints, but timing an arbitrary joint move does not by itself prove straight lens travel or collision clearance. [Ruckig project documentation](https://github.com/pantor/ruckig).

For an illustrative straight 0.5 m move in 5 s, average speed is 0.10 m/s. If the progress uses a quintic ease-in/out `s(u) = 10u³ − 15u⁴ + 6u⁵`, peak speed is 1.875 times the average, or 0.188 m/s. That calculation is a preview demand, not an approved cart speed. Joint speeds after IK can be more restrictive, especially near a singularity. Report both requested duration and the duration feasible under measured limits; if limits are missing, report duration as provisional.

## Simulator and control responsibilities

A useful simulator can preview the cart path, both actual joint chains, phone framing, light direction, and take transitions. It should distinguish requested from achieved lens poses, show which joint approaches a limit, and mark unreachable portions rather than invent joint poses. Nominal upstream geometry, unmeasured mounts, approximate collision shapes, and simulated motor dynamics must remain identifiable. A geometric preview cannot establish vibration, slip, actual exposure, or runtime obstacle clearance.

For the hardware pipeline, keep the multimodal director at shot intent and take review. Local software owns geometry, IK, plan freshness, timing, measured joints, and camera feedback. A VLA is not required for this baseline. This design is consistent with prior automated-cinematography research separating cinematographic intent from platform-specific motion; the UAV work is precedent for the separation, not evidence that this cart has the same motion envelope. [Galvane et al.: Automated Cinematography with Unmanned Aerial Vehicles](https://arxiv.org/abs/1712.04353).

Use the cart camera and fixed markers for room/cart geometry, with calibrated camera intrinsics and known marker dimensions. Use the phone preview for the actual composition. OpenCV's marker pose is relative to the camera and requires those calibrations. MediaPipe's world landmarks have their origin at the person's hips, so they are not automatically room coordinates. [OpenCV ArUco pose estimation](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html), [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python).

The first acceptance shot should be a parked-cart hold with framing correction, followed by one validated local arm move. Then validate a short straight cart push with both arms holding appropriate independent configurations. Only after those components are measured should the coordinator combine cart travel, local phone motion, and light reveal in one recorded take.
