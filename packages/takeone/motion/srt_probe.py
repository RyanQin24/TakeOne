"""Receive the wireless iPhone feed without opening motors or serial ports."""

import argparse
import json
import threading
import time
from pathlib import Path

import cv2
import numpy

from takeone.config import read_json
from takeone.motion.srt_camera import SrtCamera
from takeone.motion.tracking import camera_settings
from takeone.paths import CONFIGS, DATA
from takeone.phone.client import BlackmagicCamera


def probe(seconds=5.0, output=None):
    config = camera_settings(require_latency=False)
    phone_config = read_json(CONFIGS / "iphone-camera.json")
    phone = BlackmagicCamera(
        phone_config["endpoint"],
        phone_config["timeout_s"],
        cert_sha256=phone_config.get("tls_cert_sha256", ""),
    )
    stop = threading.Event()
    camera = SrtCamera(config, cv2=cv2, numpy=numpy, phone=phone, stop=stop)
    started = time.monotonic()
    first_at = None
    frames = 0
    last = None
    gaps = []
    previous = None
    try:
        deadline = started + seconds
        while time.monotonic() < deadline:
            ok, frame = camera.read()
            now = time.monotonic()
            if not ok:
                raise RuntimeError("The iPhone SRT feed stopped or did not deliver a fresh frame")
            first_at = first_at or now
            if previous is not None:
                gaps.append(now - previous)
            previous = now
            last = frame
            frames += 1
    finally:
        camera.release()
    folder = DATA / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    image_path = Path(output) if output else folder / "iphone-srt-frame.png"
    if last is None or not cv2.imwrite(str(image_path), last):
        raise RuntimeError("No iPhone SRT frame was saved")
    report = dict(
        schema_version=1,
        source="TakeOne-iPhone Blackmagic SRT",
        motors_opened=False,
        serial_ports_opened=False,
        frames=frames,
        width=int(last.shape[1]),
        height=int(last.shape[0]),
        time_to_first_frame_s=round(first_at - started, 4),
        max_inter_frame_gap_s=round(max(gaps, default=0.0), 4),
        elapsed_s=round(time.monotonic() - started, 4),
        latency_qualified=False,
        image=str(image_path.resolve()),
    )
    report_path = image_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 60:
        parser.error("--seconds must be between 1 and 60")
    print(json.dumps(probe(args.seconds, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
