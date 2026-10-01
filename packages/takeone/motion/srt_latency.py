"""Measure screen-to-iPhone-to-laptop delay without opening robot hardware."""

import argparse
import json
import statistics
import threading
import time

import numpy

from takeone.config import read_json
from takeone.motion.srt_camera import SrtCamera
from takeone.motion.tracking import camera_settings
from takeone.paths import CONFIGS, DATA
from takeone.phone.client import BlackmagicCamera

WINDOW = "TakeOne Wi-Fi latency target"


def _show(level, text, cv2):
    image = numpy.full((720, 1280, 3), level, dtype=numpy.uint8)
    ink = 255 - level
    cv2.putText(
        image,
        text,
        (70, 380),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.6,
        (ink, ink, ink),
        4,
        cv2.LINE_AA,
    )
    cv2.imshow(WINDOW, image)
    cv2.waitKey(1)
    return time.perf_counter()


def _mean(frame):
    return float(numpy.mean(frame))


def _collect(camera, seconds, cv2):
    values = []
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        ok, frame = camera.read()
        if not ok:
            if not camera.isOpened():
                raise RuntimeError("The FFmpeg SRT receiver exited during the latency test")
            continue
        values.append(_mean(frame))
        if cv2.waitKey(1) & 0xFF == 27:
            raise KeyboardInterrupt()
    if not values:
        raise RuntimeError(f"No fresh iPhone frames arrived during a {seconds:g}-second measurement window")
    return values


def _wait_for(camera, *, above, threshold, cv2, timeout_s=5.0):
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        ok, frame = camera.read()
        if not ok:
            if not camera.isOpened():
                raise RuntimeError("The FFmpeg SRT receiver exited during the latency test")
            continue
        value = _mean(frame)
        if (above and value >= threshold) or (not above and value <= threshold):
            return time.perf_counter(), value
        if cv2.waitKey(1) & 0xFF == 27:
            raise KeyboardInterrupt()
    direction = "bright" if above else "dark"
    raise RuntimeError(
        f"The phone did not see the screen turn {direction}. Fill its view with the laptop display."
    )


def summarize(samples):
    if not samples:
        raise ValueError("At least one latency sample is required")
    ordered = sorted(samples)
    percentile_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return {
        "samples_ms": [round(value * 1000, 1) for value in samples],
        "median_ms": round(statistics.median(samples) * 1000, 1),
        "p95_observed_ms": round(ordered[percentile_index] * 1000, 1),
        "maximum_ms": round(max(samples) * 1000, 1),
    }


def measure(cycles=3, aim_seconds=8.0):
    import cv2

    config = camera_settings(require_latency=False)
    phone_config = read_json(CONFIGS / "iphone-camera.json")
    phone = BlackmagicCamera(
        phone_config["endpoint"],
        phone_config["timeout_s"],
        cert_sha256=phone_config.get("tls_cert_sha256", ""),
    )
    stop = threading.Event()
    camera = None
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    try:
        _show(230, "Aim the iPhone at this screen", cv2)
        camera = SrtCamera(config, cv2=cv2, numpy=numpy, phone=phone, stop=stop)
        _collect(camera, aim_seconds, cv2)

        _show(0, "DARK", cv2)
        dark_values = _collect(camera, 2.0, cv2)
        dark = statistics.median(dark_values[-min(20, len(dark_values)) :])

        first_change = _show(255, "BRIGHT", cv2)
        first_seen, first_bright = _wait_for(
            camera,
            above=True,
            threshold=dark + 20.0,
            cv2=cv2,
        )
        samples = [first_seen - first_change]
        bright_values = _collect(camera, 1.0, cv2)
        # The iPhone's auto exposure can pull a sustained white screen back
        # toward the earlier dark mean. The first threshold crossing is the
        # actual transition evidence, so retain its peak for later cycles.
        bright = max(first_bright, max(bright_values))
        midpoint = (dark + bright) / 2.0

        for _ in range(cycles):
            changed = _show(0, "DARK", cv2)
            seen, _ = _wait_for(camera, above=False, threshold=midpoint, cv2=cv2)
            samples.append(seen - changed)
            _collect(camera, 0.75, cv2)

            changed = _show(255, "BRIGHT", cv2)
            seen, _ = _wait_for(camera, above=True, threshold=midpoint, cv2=cv2)
            samples.append(seen - changed)
            _collect(camera, 0.75, cv2)
    finally:
        if camera is not None:
            camera.release()
        cv2.destroyWindow(WINDOW)

    report = {
        "schema_version": 1,
        "source": "TakeOne-iPhone Blackmagic SRT",
        "method": "laptop screen luminance transition observed through mounted iPhone",
        "motors_opened": False,
        "serial_ports_opened": False,
        "dark_mean": round(dark, 1),
        "bright_mean": round(bright, 1),
        **summarize(samples),
        "latency_qualified": False,
        "qualification_reason": "Measurement recorded; an operator-approved motion limit is still required.",
    }
    folder = DATA / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "iphone-srt-latency.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report"] = str(path.resolve())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--aim-seconds", type=float, default=8.0)
    args = parser.parse_args(argv)
    if not 1 <= args.cycles <= 10:
        parser.error("--cycles must be between 1 and 10")
    if not 3 <= args.aim_seconds <= 30:
        parser.error("--aim-seconds must be between 3 and 30")
    print(json.dumps(measure(args.cycles, args.aim_seconds), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
