"""Opt-in live check that the iPhone lens actually moves, and that the movement
library's focal lengths are inside this phone's measured calibration.

Two failures produce the same symptom — a take that records with a completely
static frame where a Dolly Zoom was planned — and they need different fixes:

  1. The take carried no authored lens cues, so nothing ever commanded the lens.
     Fixed in the recorder; `--take-plan` shows what a Record-page take now
     sends.
  2. The take carried cues the calibration cannot map. `mapped_zoom` refuses
     anything outside the measured focal range rather than clamping the lens
     somewhere it was never measured, so the take is refused instead of silently
     wrong. That is a calibration job, and this prints exactly which focal
     lengths are missing.

This talks to the handset. It never moves the robot and never starts a
recording. It leaves the lens where it found it.

    python scripts/phone_lens_check.py                # report only, no device writes
    python scripts/phone_lens_check.py --sweep        # drive the lens and read back
"""

import argparse
import json
import sys
import time

from takeone.paths import CONFIGS
from takeone.phone.client import BlackmagicCamera, CameraError, calibration_points, mapped_zoom
from takeone.phone.service import PhoneService

# Every focal length the installed movement library can ask a take to hold.
# Keep this list in step with previs/templates.py rather than guessing a range.
LIBRARY_FOCALS = (24.0, 35.0, 48.0, 70.0, 120.0)


def report_calibration(config):
    points = config["calibration"]
    print(f"Configured endpoint : {config['endpoint'] or '(none)'}")
    print(f"Calibration points  : {len(points)}")
    for point in points:
        print(f"  {point['focal_mm']:>6.1f} mm -> normalised {point['normalised']:.6f}")
    if len(points) < 2:
        print("\nFewer than two measured points: no mapping exists, so every lens cue is refused.")
        return None
    measured = calibration_points(points)
    low, high = measured[0][0], measured[-1][0]
    print(f"\nMeasured focal range: {low:g}-{high:g} mm")
    missing = [focal for focal in LIBRARY_FOCALS if not low <= focal <= high]
    if missing:
        print("Movement-library focal lengths OUTSIDE that range, which will be refused:")
        for focal in missing:
            print(f"  {focal:g} mm")
        print(
            "\nMeasure these on the handset: set the lens, read its focal length, then use\n"
            "Phone setup -> Lens calibration -> Record this focal length."
        )
    else:
        print("Every movement-library focal length is inside the measured range.")
    return measured


def report_take_plan(service):
    """What a Record-page take now hands the phone, without contacting it."""
    from takeone.recording.phone import PhoneRecorder

    recorder = PhoneRecorder(service)
    cues = [{"time_s": 0.0, "focal_mm": 48.0}, {"time_s": 3.0, "focal_mm": 24.0}]
    context = {"shot": {"plan_id": None, "duration_s": 3.0, "camera_cues": cues, "label": "Dolly Zoom"}}
    print("\nA take carrying a reviewed shot now builds this phone plan:")
    print(json.dumps(recorder._plan("example", context), indent=2))
    print("\nA behavior-driven take with no authored shot still builds:")
    print(json.dumps(recorder._plan("example", {}), indent=2))


def sweep(camera, measured, settle_s):
    """Drive the lens across the measured range and print what the device reports."""
    resting = camera.zoom()
    print(f"\nResting normalised zoom: {resting:.6f}")
    print("Driving the lens. Watch the handset.\n")
    print(f"{'focal_mm':>9}  {'requested':>10}  {'observed':>10}  {'delta':>9}  {'ms':>6}")
    worst = 0.0
    try:
        for focal in [point[0] for point in measured]:
            target = mapped_zoom(measured, focal)
            started = time.perf_counter()
            observed = camera.zoom(target)
            elapsed = (time.perf_counter() - started) * 1000
            time.sleep(settle_s)
            settled = camera.zoom()
            delta = abs(settled - target)
            worst = max(worst, delta)
            print(f"{focal:>9.1f}  {target:>10.6f}  {settled:>10.6f}  {delta:>9.6f}  {elapsed:>6.0f}")
            del observed
    finally:
        camera.zoom(resting)
        print(f"\nLens returned to {resting:.6f}.")
    print(f"Worst readback difference: {worst:.6f}")
    # PhoneTake aborts a take when a readback misses its target by more than this.
    if worst > 0.02:
        print(
            "\nThat exceeds the 0.02 tolerance PhoneTake enforces during a take, so a real take\n"
            "would abort with a zoom-readback refusal. Re-measure the calibration points."
        )
    else:
        print("\nWithin the 0.02 tolerance PhoneTake enforces during a take.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", action="store_true", help="Drive the lens across measured points.")
    parser.add_argument("--settle-s", type=float, default=0.6, help="Wait before reading back.")
    parser.add_argument("--take-plan", action="store_true", help="Print the phone plan a take builds.")
    args = parser.parse_args()

    service = PhoneService(CONFIGS / "iphone-camera.json")
    config = service.config
    measured = report_calibration(config)
    if args.take_plan:
        report_take_plan(service)
    if not args.sweep:
        return 0
    if measured is None:
        print("\nNothing to sweep without a mapping.")
        return 1
    if not config["enabled"] or not config["endpoint"]:
        print("\nEnable the phone and save its address before sweeping.")
        return 1
    camera = BlackmagicCamera(config["endpoint"], config["timeout_s"], cert_sha256=config["tls_cert_sha256"])
    observed = camera.probe()
    print(f"\nDevice: {observed['product'].get('productName')}")
    if observed["recording"]:
        print("The phone is recording. This tool will not touch the lens mid-clip.")
        return 1
    if observed["fingerprint"] != config["fingerprint"]:
        print("Phone identity or format changed since calibration. Recalibrate before trusting a sweep.")
        return 1
    sweep(camera, measured, args.settle_s)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CameraError, ValueError) as error:
        print(f"phone lens check: {error}", file=sys.stderr)
        sys.exit(1)
