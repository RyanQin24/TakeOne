"""Capture the cart camera's desired person framing without opening robot hardware."""

import argparse
import json
import math
import os
import statistics
import threading
import time
from collections import deque
from urllib.request import urlopen

from takeone.config import read_json
from takeone.motion.dshow_camera import DirectShowCamera
from takeone.motion.studio_worker import device_ownership
from takeone.motion.tracking import camera_settings, settings
from takeone.paths import CONFIGS, DATA

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
MIN_SAMPLES = 15
MAX_SAMPLES = 45


def measurement(landmarks, width, height):
    """Return shoulder midpoint and width as resolution-independent fractions."""
    left, right = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]
    if min(getattr(left, "visibility", 1.0), getattr(right, "visibility", 1.0)) < 0.5:
        return None
    left_x, left_y = left.x * width, left.y * height
    right_x, right_y = right.x * width, right.y * height
    return (
        (left_x + right_x) / (2 * width),
        (left_y + right_y) / (2 * height),
        math.hypot(right_x - left_x, right_y - left_y) / width,
    )


def median_target(samples, previous):
    if len(samples) < MIN_SAMPLES:
        raise ValueError(f"Hold the desired pose until at least {MIN_SAMPLES} valid frames are visible")
    center_x, center_y, shoulder_width = (statistics.median(values) for values in zip(*samples, strict=True))
    return {
        **previous,
        "center_x_fraction": round(center_x, 6),
        "center_y_fraction": round(center_y, 6),
        "shoulder_width_fraction": round(shoulder_width, 6),
        "calibrated": True,
        "source": "operator_pose_median",
        "sample_count": len(samples),
        "calibrated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def save_target(target, path=CONFIGS / "tracking.json"):
    document = read_json(path)
    document["camera"]["body_target"] = target
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def model_path():
    folder = settings()[1] / "models"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "pose_landmarker_lite.task"
    if not path.exists():
        print("Downloading the MediaPipe pose model…", flush=True)
        with urlopen(MODEL_URL, timeout=30) as response:
            path.write_bytes(response.read())
    return path


def calibrate():
    import cv2
    import mediapipe as mp
    import numpy

    config = camera_settings(require_latency=False)
    if config["kind"] != "directshow":
        raise ValueError("Cart framing calibration requires the DirectShow cart camera")
    detector = mp.tasks.vision.PoseLandmarker.create_from_options(
        mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path())),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.7,
            min_pose_presence_confidence=0.7,
            min_tracking_confidence=0.7,
        )
    )
    stop = threading.Event()
    samples = deque(maxlen=MAX_SAMPLES)
    last_frame = None
    target = None
    with device_ownership():
        camera = DirectShowCamera(config, cv2=cv2, numpy=numpy, stop=stop)
        try:
            while True:
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError("The cart camera stopped during framing calibration")
                last_frame = frame.copy()
                height, width = frame.shape[:2]
                result = detector.detect(
                    mp.Image(
                        image_format=mp.ImageFormat.SRGB,
                        data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                    )
                )
                current = (
                    measurement(result.pose_landmarks[0], width, height) if result.pose_landmarks else None
                )
                if current is not None:
                    samples.append(current)
                    x = round(current[0] * width)
                    y = round(current[1] * height)
                    shoulder_width = round(current[2] * width)
                    cv2.drawMarker(frame, (x, y), (0, 255, 0), cv2.MARKER_CROSS, 28, 2)
                    cv2.putText(
                        frame,
                        f"Shoulder width: {shoulder_width}px | samples: {len(samples)}/{MIN_SAMPLES}",
                        (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 255, 0),
                        2,
                    )
                else:
                    samples.clear()
                    cv2.putText(
                        frame,
                        "Stand where you want the robot to converge",
                        (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 0, 255),
                        2,
                    )
                cv2.putText(
                    frame,
                    "Hold still, then press SPACE to save | Esc cancels",
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 255, 255),
                    2,
                )
                cv2.imshow("TakeOne Cart Framing Calibration - NO MOTORS", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    return None
                if key in (13, 32, ord("c"), ord("C")):
                    try:
                        target = median_target(list(samples), config["body_target"])
                    except ValueError as error:
                        print(str(error), flush=True)
                        continue
                    save_target(target)
                    break
        finally:
            stop.set()
            camera.release()
            detector.close()
            cv2.destroyAllWindows()
    folder = DATA / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    image_path = folder / "cart-tracking-calibration.png"
    if last_frame is not None:
        cv2.imwrite(str(image_path), last_frame)
    return {
        "schema_version": 1,
        "camera": config["device_label"],
        "motors_opened": False,
        "serial_ports_opened": False,
        "target": target,
        "image": str(image_path.resolve()),
    }


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    report = calibrate()
    if report is None:
        print("Cart framing calibration cancelled; the saved target was not changed.")
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
