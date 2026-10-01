# iPhone camera view and reusable zoom

The phone monitor now names the iPhone 17 Pro Max and offers a camera-output
channel on every named movement, the drawn-path editor, and the original orbit.
This review step covers framing and lenses. Scripted pauses in the cart/arm
movement schedule are a separate next feature; the preview Play/Pause control
still only pauses local rehearsal.

## Upright framing and intentional roll

**Landscape filming start:** every shot now aims the physical phone horizontally
during its stationary setup. The optical image width follows the handset's long
edge. This changes the solved wrist goals, not only the monitor rotation. Both
arms still start at their exact saved calibration counts; filming begins after
the move into the landscape pose. Roll/handheld effects begin from this landscape
orientation and then follow the selected choreography. Existing saved settings
receive this correction when compiled again.

The initial phone solve considers both wrist-wrap directions. A small continuity
preference keeps the free arm posture from changing faster than the existing
motor timeline can follow during tilt and lift. A path that returns to its exact
opening target reuses those opening encoder goals. These are planning choices;
they add no measured-error stop condition. Phone wrist-roll remains motor ID 6.
An upward tilt is solved back from its face-facing end pose so the lower opening
pose belongs to a continuous arm branch. The shot duration and motor-rate limit
stay the same; this changes the precomputed setup and joint path.

The screenshot at 00:00 showed the raw optical axes of the calibrated arm pose.
That pose can have a sideways image even while the actor stands upright.

**Horizon** now offers:

- **Auto**: upright output for ordinary shots; physical phone roll for roll and
  handheld presets, so their intended effects remain visible.
- **Keep horizon level**: remove output roll while retaining the achieved lens
  position and aiming direction.
- **Follow the phone's roll**: show the uncorrected optical orientation.

The world model, calibrated starting counts, and motor commands remain the
physical model. Each frame retains its original `camera` FK pose and adds an
explicit `camera_view` output pose. Level framing projects world up into the
image plane. Looking straight up/down has no unique horizon; the output keeps
the sensor's right axis at that singularity rather than producing invalid data.

Apple provides separate orientation compensation for preview and capture through
[AVCaptureDevice.RotationCoordinator](https://developer.apple.com/documentation/avfoundation/avcapturedevice/rotationcoordinator).
The simulator's level view is an ideal framing preview, not a claim that the
built-in Camera app cancels every roll during a recording. Recording-app
orientation, stabilization crop, distortion, automatic lens switching and
real-device video processing are not reproduced. Match the intended output mode
in the recording app. No iPhone capture or zoom commands are transmitted.

## Lenses on any movement

The shortcuts use the iPhone 17 Pro Max's equivalent focal lengths: 13 mm
(0.5x), 24 mm (1x), 48 mm (2x sensor crop), 100 mm (4x), and 200 mm (8x sensor
crop). Apple's published video specification allows 15x digital zoom; the extra
15x shortcut uses approximately 360 mm equivalent framing relative to the
24 mm main camera. This is digital framing, not another physical lens. See
[Apple's specifications](https://support.apple.com/en-sg/125091).

**Lens movement** offers the preset's lens behavior, one fixed focal length,
an editable zoom curve, or Dolly Zoom based on optical depth. The curve editor
supports up to 32 ordered points, each with a shot percentage, focal length and
transition to the next point. It also displays the corresponding shot time.
Times start after the calibrated arm setup and follow changes in shot duration.

Equal adjacent focal lengths create a lens hold. Smooth transitions use quintic
easing, linear transitions keep a constant focal-length rate, and Hold then cut
keeps the value until the next point. For a 10-second shot, 24 mm at 0%, 48 mm at
30%, 48 mm at 60%, and 24 mm at 100% means zoom in over three seconds, hold for
three seconds, then zoom out over four seconds.

The camera uses a 36 mm equivalent image width and a 16:9 crop, so vertical field
of view is `2 * atan((36 / (16/9)) / (2 * focal_mm))`. Dolly Zoom uses
`f(t) = f0 * optical_depth(t) / optical_depth(0)`, preserving projected scale
until the 13-360 mm simulated range is reached. Framing drift remains reported.
If the actor crosses behind the camera, Dolly Zoom is undefined and the camera
editor asks for a different framing; no hardware threshold was introduced.

## Script and saved-shot contract

The optional `camera` object has the same form for all movement modes. Existing
saved shots without it load with Auto horizon and the preset's lens behavior.
For example, a stationary zoom-in/hold/zoom-out shot is:

```json
{
  "mode": "template",
  "template_id": "static",
  "duration_s": 10,
  "focal_mm": 24,
  "camera": {
    "horizon": "auto",
    "zoom": "keyframes",
    "keyframes": [
      {"at": 0, "focal_mm": 24, "ease": "smooth"},
      {"at": 0.3, "focal_mm": 48, "ease": "smooth"},
      {"at": 0.6, "focal_mm": 48, "ease": "smooth"},
      {"at": 1, "focal_mm": 24, "ease": "smooth"}
    ]
  }
}
```

`horizon` accepts `auto`, `level` and `phone`. `zoom` accepts `preset`, `fixed`,
`keyframes` and `dolly`. `at` is normalized shot time from 0 to 1. The camera
curve is saved with the shot and contributes to the prepared plan identity.
Timestamped `camera_cues` remain explicitly simulated lens cues. Original-orbit
preparation maps them onto its adjusted robot clock.

Camera-output and focal-length edits reuse cached arm/cart solutions. The camera
layer evaluates the output and lens curve after motion compilation. The renderer
reuses orientation vectors and evaluates the small zoom curve without IK,
geometry allocation, or hardware work during playback.

## Recovery and verification

Original changed files are preserved under
`C:\TakeOne\data\recovery\iphone-camera-20260913` with their workspace-relative
paths. Product changes are camera options in catalog/validators, cached motion
compilation in compiler/path/templates, and cue timing in studio_plan. The new
camera.py owns output/lens evaluation; phone-camera.js and camera-controls.js
provide rendering math and editing. Existing orbit.js, index.html, orbit.css,
and shot-library.js integrate them. The later landscape-start correction changes
only the phone optical site's basis in simulation/model.py and its three generated
XML models; lens position, handset geometry and calibration are unchanged. Its
recovery copies are under `data/recovery/landscape-start-20260913`.
The associated compiler change selects landscape wrist solutions, path.py keeps
returning targets repeatable, and camera.py pins the authored ending zoom value
despite floating-point clock rounding. Updated GLBs are generated from the same
calibrated starting model with `node apps/rehearsal/export_models.mjs`.

Verification output is under
`C:\TakeOne\data\verification\iphone-camera-20260913`. Tests cover raw-versus-output
orientation, singular vertical aim, zoom holds/cuts, Dolly Zoom depth, saved
settings, all-template acceptance, unchanged motor packets and cache reuse.
Hardware tests are not part of this run.
