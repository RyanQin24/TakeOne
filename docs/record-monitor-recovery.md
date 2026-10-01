# Record controls and cart-camera recovery

The Record page puts recording controls before the monitor and shot list. For a
loaded plan, **Start filming** now prepares and starts the selected shot through
the existing robot worker, which owns cart, arm and iPhone capture together.
**Stop shot** stops that worker and its phone capture; completion never selects
the next shot. Planned shots use manual initiation. Without a loaded plan, the
legacy camera-only recording and framing observation remain available.
The iPhone remains the recorder; the cart-mounted CAM 313 is a witness view, not
the iPhone lens, even when mounted nearby. Its lens offset remains unmeasured.

The right preview selects one shot's source frames, with a zero-based scrubber
bounded by that shot's duration. Shot metadata includes its compiled motor-plan
digest; preparation rejects changed settings or windows outside that plan.
Source windows use the existing 40 ms arm and 20 ms cart command clocks. A
separately filmed continuation adds a stationary-cart arm setup before its
selected source interval. Startup errors are reported to Record even when the
3D module cannot load, and readiness is emitted when compilation finishes.

September 19 verification: the ten-shot night script displayed 10.28 seconds for
shot 1 and 14.24 seconds for shot 2; scrubbing to shot 2's end retained shot 2.
The live API prepared shot 1 with `ports_opened: false`. Read-only inspection
initially reported Windows access denied on COM9 and COM8; a later inspection
read both arms successfully. No physical playback was started for verification.

The subsequent "Camera cues must be strictly time ordered" failure came from
the browser representing the 10.28-second endpoint as 10.280000000000001. The
shot compiler retained that source endpoint and appended it again. Interior
lens cues now exclude the explicitly supplied boundaries, including after
shifting a cropped shot onto its local clock. Regression checks pass full and
cropped windows, with both directions of floating-point rounding, through the
phone's actual `lens_schedule` validator. The user's Tilt up settings and saved
phone calibration also pass. The live prepare API returns the corrected plan
without opening ports.

The earlier recovery notes below describe the previous camera-only workflow.

The previous local camera-selection changes excluded the CAM 313 for all source
types and refused witness sources. Filtering is now restricted to phone-feed
selection. A saved named input must still resolve exactly: a missing phone feed
cannot silently fall back to the cart camera or another webcam.

A shared camera could report a live track while the Record video element had
no `srcObject`. Record now binds shared/new/replaced tracks, waits for decoded
video dimensions and exposes playback failure or an eight-second no-frame
timeout. Pending device/permission requests show a waiting hint after ten
seconds. It does not certify continuously fresh frames or optical alignment.

If recording is disabled because another tab owns the voice/recording session,
the reason stays next to the controls. Stop TO/voice in the owning tab, then use
**Reconnect recorder**. This retries normal ownership checks; it neither steals
ownership nor starts a take. Existing unknown-take recovery requirements remain.

Verification: 354 browser tests passed, including witness/phone source filtering,
shared-track attachment, no-frame timeout, late recovery, playback rejection and
cleanup without stopping another camera consumer. The top controls and ownership
message were inspected in the browser. Actual camera frames were not confirmed:
the test browser waited for camera access. No recording or robot movement was
started. A separate native tracking process may contend for the same USB camera;
this change does not add a shared stream between browsers and native processes.

## Manual scene recording and subject recovery

Each scene card has a **Record scene N** action, carrying that scene's reviewed
lens cues into the phone take. It does not require person detection or 100%
confidence. If automatic framing is observing, manual recording first stops
observation and rechecks recorder availability. A failed cancellation, unresolved
take, lost ownership, missing lens timeline or calibration gap cannot be bypassed.
Only a newly confirmed starting/recording take marks the scene filmed.

The subject selector replaces a vanished ID when exactly one person is visible;
with multiple people it requires a fresh choice rather than selecting somebody
arbitrarily. Raw confidence is available in Evidence, not as a percentage in the person selector. Watching must
successfully select the current visible subject before preparing observation.
The aim display now matches the controller's per-axis 0.04 deadband, not a
stricter vector-length test. Aim offset, frame height and detection confidence
are labelled separately; none is a progress bar toward 100%. No controller
thresholds or motor behavior changed.

Phone status reports configuration readiness, cached connection evidence and the
last confirmed recording result separately from physical qualification. The
permanently false hardware-verification field no longer yields a permanently
failing "not qualified" badge. Connection checks are not claims of live health,
pixel verification or robot readiness.

Verification for this follow-up: 26 focused Record tests passed. The complete web
suite passed 363 of 364 tests; the unrelated untracked `gpt-live-test.html` fails
the stylesheet contract. Browser inspection confirmed all ten scene actions in
the loaded night-demo plan and the manual default. Buttons were correctly blocked
in that separate tab by the existing recorder owner. No take or robot movement
was started, and the native tracking controller was not changed.

The person selector now says **detected** instead of showing an apparent progress
percentage. This does not fabricate a 100% detector result or loosen physical
tracking thresholds. Manual mode explicitly says detection and framing scores do
not block recording. Phone status also exposes an observed identity/format
mismatch before recording instead of treating configuration completeness as
proof that the saved lens calibration still matches the connected handset.

The September 19 follow-up compared the connected handset with a saved successful
camera-only test: only `product.softwareVersion` differed. After the operator
explicitly confirmed the same phone/lens and requested retaining calibration,
the local saved fingerprint was updated. All other configuration fields,
including the measured 24/48 mm points, were preserved. The original file is
backed up under `data/recovery/phone-version-confirmation-f30689ee5f37430eaf366d17cc5b7dd1/`.
A subsequent read-only phone probe confirmed matching identity/format and idle
recording state at 1080p60. No new recording, zoom or robot motion was commanded.
This is an operator-confirmed migration, not automatic acceptance of future
camera changes. The service now reports observed fingerprint mismatches in its
readiness response as well. Twenty-seven focused Record tests and fourteen
phone route/readiness tests passed; the full repository runner was started.
