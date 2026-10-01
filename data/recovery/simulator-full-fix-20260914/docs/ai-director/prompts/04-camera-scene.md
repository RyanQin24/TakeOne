# 04 — Camera input and scene evidence

Implement work package 04 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, the existing recording reference config, the delivery plan and package 01 record. Follow shared rules. Dependency: 01. This package can precede completed creative planning.

## Outcome

The Director receives actual camera evidence, stays associated with a selected actor and knows when the evidence is insufficient. The application distinguishes the shooting phone's composition from a separate context camera. It does not claim that a monocular detector has measured the whole room.

## Implement

1. Inventory the available camera/phone integration without opening motor connections. Verify the actual phone OS and capture software; historical references do not settle it. Write a short integration decision covering preview, timestamps, crop/lens settings, start/stop control and master transfer. If the device facts are unavailable, ask for the exact missing detail while completing replay and independent camera code.
2. Implement a bounded timestamped replay source and one explicitly selected real camera source. Track capture, arrival and processing times, source/sequence/clock epoch, dropped frames and uncertainty. Use latest-value observation delivery, not an unbounded backlog.
3. Add selected-actor locking and basic local pose/framing features using the chosen lightweight perception stack in an isolated optional dependency group. Camera source labels must remain visible. A webcam may demonstrate context perception but cannot certify the phone's final composition.
4. Add scene evidence with normalized-image coordinates distinct from metric room coordinates. A metric setup requires measured scale, intrinsics/extrinsics, floor/mark transforms and uncertainty. Unknown space stays unknown. Do not build arbitrary 3D reconstruction or infer exact distances from an uncalibrated image.
5. Produce typed observations usable by beat checks: visible/not observable, face/head direction proxy, mark-relative position where calibrated, and motion direction. Keep confidence, evidence frame references and expiry. Distinguish planned exits from tracking loss; head pose is not exact eye gaze or emotion.
6. Add a device/scene screen with actual preview, actor selection, evidence freshness and calibration status. Report camera transform changes caused by robot motion; dynamic phone-to-world estimates require current measured joints and tool mapping in package 10. Static calibration cannot silently remain valid after movement.

## Acceptance

- Selected actor A crosses actor B, leaves and returns: preserve identity or report loss, never silently switch.
- Frozen/delayed frames, bad timestamps and camera loss become stale/unknown promptly.
- A planned exit can satisfy its beat while an unexpected occlusion remains unknown.
- Screen-space detection cannot be consumed as a measured room-space position.
- Preview and master crop differences remain visible as an unverified mapping until measured.
- Import/test discovery has no camera or motor side effects; real-camera tests require explicit selection.

Run root verification and an opt-in actual-camera demonstration when available; record device, conditions and p50/p95/p99 observation age. Do not claim the latency target passed without measurement. Leave `docs/ai-director/implementation/04-camera-scene.md` and update package 04 from actual evidence.
