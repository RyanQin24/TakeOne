# Engineering prompt: iPhone capture, shared lens cues, and color

Implement this task in the verified TakeOne checkout, not an assumed drive.
Read AGENTS.md, CLAUDE.md and the existing camera, Director, playback and HTTP code first.
Preserve unrelated edits, calibration bytes, plan fidelity, serial watchdogs and explicit robot approval.

## Outcome
A reviewed robot run starts an iPhone recording before any motion, consumes the existing camera_cues
on the robot's actual playback clock, and stops its own recording on completion or failure.
An explicitly linked simulator sends its FILM-camera focal length, not the orbit/navigation camera zoom.
Director scripts describe numerical zoom/hold timing and compile to the existing camera keyframes.
A color workflow distinguishes a monitoring LUT from irreversible baked-in recording.

## Research-backed implementation decision
Use Blackmagic Camera for iOS 3.4+ REST, not automation of Apple's stock Camera UI.
Keep the adapter small and stdlib-only. Do not create a native app/build system without a demonstrated need.
The generic REST manual predates mobile REST: probe the real device and reject unsupported capabilities.
Never claim the unconnected iPhone was tested or that HTTP acknowledgement proves captured image quality.
Use an explicitly supplied private-network endpoint; do not scan the network or expose the robot server.

## Integration constraints
Reuse camera_cues, camera.zoom/keyframes and the existing quintic/linear/hold convention.
Record acknowledgement is a pre-motion barrier. Network IO never runs in the arm/cart dispatch loops.
Use one phone owner per simulator session; reject preview edits while a robot capture owns the camera.
Use bounded network deadlines, no automatic retry of record-start, bounded latest-wins preview updates,
and an absolute monotonic scheduler that skips overdue zoom samples instead of accumulating a backlog.
Preserve uncertain recording outcomes, distinguish requested/acknowledged/device-reported evidence,
and attempt stop in finally only for a recording this operation may have started.

## Lens and color truth
Do not equate REST normalised zoom, physical focalLength, displayed x and 35mm-equivalent millimetres.
Capture operator-labelled equivalent focal/normalised calibration points from device readback.
Bind calibration to device and recording format, refuse extrapolation, and label interpolation estimated.
Lens switches, stabilization crop and perspective matching need an on-device framing check.
Validate custom 17/33-point .cube files, finite values, size and color-space metadata; hash the exact bytes.
LUT import/selection and Log 2 capture settings remain explicit phone setup unless supported API proves them.
Never pass a Rec.709 look directly over Log 2 or apply two log-to-display transforms.
Check displayLUT readback when that endpoint exists; otherwise require a clearly labelled operator confirmation.
Do not invent a remotely selected LUT, baked footage, optical zoom or genlock guarantee.

## Code quality
Prefer a small client, calibrated lens mapping, capture scheduler and integration service over frameworks.
Validate at external boundaries; trust validated internal structures. Give errors a concrete corrective action.
No catch-and-pretend-success, duplicate scene schema, hidden fallback to simulated recording or gratuitous rewrite.
No camera requests during render: queue only changed focal targets and drain asynchronously at a bounded rate.
Persist a per-run camera sidecar without changing the reviewed motor plan or its hash.
Keep new controls accessible and consistent with the existing Shot Studio.

## Definition of done
Run baseline tests first, then fake-camera HTTP tests for readback, timeout, failed start, unknown stop,
calibration mismatch, zoom hold/endpoints, ownership, LUT mismatch and cleanup.
Exercise the real worker hook without serial devices; run existing Python, web, integrity and lint checks.
Start the simulator and run a browser smoke test if browser tooling is available.
Write the exact test commands, results and remaining on-device checks into a reproducible report.
Do not manufacture hardware evidence. Leave camera disabled until the actual phone is paired and checked.
