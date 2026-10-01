"""Loopback-facing phone ownership and setup. No device connection until an explicit action."""

import copy
import json
import secrets
import threading
import time
from pathlib import Path

from takeone.paths import CONFIGS, DATA

from .capture import PhoneTake, lens_schedule
from .client import BlackmagicCamera, CameraError, calibration_points, endpoint, mapped_zoom, number
from .color import color_recipe, validate_cube

TOKEN_HEADER = "X-TakeOne-Phone-Token"


def defaults():
    return dict(
        schema_version=1,
        enabled=False,
        endpoint="",
        timeout_s=0.75,
        zoom_hz=10,
        calibration=[],
        fingerprint="",
        color=dict(
            capture_space="rec709",
            lut_input_space="rec709",
            lut_name="",
            mode="monitor",
            operator_confirmed=False,
            display="",
            cube_sha256="",
        ),
    )


class PhoneService:
    def __init__(self, path=None, *, client_factory=BlackmagicCamera):
        self.path = Path(path) if path else CONFIGS / "iphone-camera.json"
        self.config = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else defaults()
        self.token, self.lock = secrets.token_urlsafe(32), threading.RLock()
        self.client_factory = client_factory
        self.owner, self.observed, self.last_result, self.uncertain = None, None, None, False
        c = self.config
        if set(c) != set(defaults()) or c["schema_version"] != 1 or type(c["enabled"]) is not bool:
            raise ValueError("Invalid iphone-camera.json configuration.")
        if c["endpoint"]:
            c["endpoint"] = endpoint(c["endpoint"])
        number(c["timeout_s"], "Camera timeout", 0.1, 3)
        number(c["zoom_hz"], "Zoom rate", 1, 20)
        color_recipe(c["color"])

    def status(self):
        with self.lock:
            return dict(
                token=self.token,
                config=copy.deepcopy(self.config),
                owner=self.owner,
                observed=copy.deepcopy(self.observed),
                last_result=copy.deepcopy(self.last_result),
                uncertain=self.uncertain,
                hardware_verified=False,
            )

    def authorize(self, token):
        if not isinstance(token, str) or not secrets.compare_digest(token, self.token):
            raise PermissionError("Reload Shot Studio before controlling the iPhone.")

    def _idle(self):
        if self.owner:
            raise CameraError("The iPhone belongs to an active take; preview/setup changes are locked.")

    def _client(self):
        return self.client_factory(self.config["endpoint"], self.config["timeout_s"])

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix(".tmp")
        pending.write_text(json.dumps(self.config, indent=2, allow_nan=False), encoding="utf-8")
        pending.replace(self.path)

    def _ready(self):
        if self.uncertain:
            raise CameraError("Previous recording outcome is unknown. Inspect the phone and probe it first.")
        endpoint(self.config["endpoint"])
        points = calibration_points(self.config["calibration"])
        if not self.config["fingerprint"]:
            raise ValueError("Capture lens calibration from the actual phone first.")
        color_recipe(self.config["color"], ready=True)
        return points

    def reserve(self, plan):
        with self.lock:
            self._idle()
            if not self.config["enabled"]:
                return None
            self._ready()
            lens_schedule(self.config, plan)
            self.owner = "robot"
            return copy.deepcopy(self.config)

    def release(self, folder, *, launched=True):
        with self.lock:
            if self.owner != "robot":
                return
            result = Path(folder) / "phone-capture.json"
            try:
                self.last_result = json.loads(result.read_text(encoding="utf-8")) if result.exists() else None
            except (ValueError, OSError):
                self.last_result = None
            self.uncertain = launched and (
                self.last_result is None
                or (self.last_result.get("start_attempted") and not self.last_result.get("stop_confirmed"))
            )
            self.owner = None

    def post(self, action, body, token):
        self.authorize(token)
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object.")
        if action == "test-record":
            return self.test_record(body)
        with self.lock:
            self._idle()
            if action == "configure":
                if set(body) != {"endpoint", "enabled"} or type(body["enabled"]) is not bool:
                    raise ValueError("Configure requires endpoint and enabled.")
                address = endpoint(body["endpoint"])
                if address != self.config["endpoint"]:
                    self.config.update(calibration=[], fingerprint="")
                    self.config["color"]["operator_confirmed"] = False
                    self.observed = None
                self.config.update(endpoint=address, enabled=body["enabled"])
                self._save()
            elif action == "probe":
                if body:
                    raise ValueError("Probe does not accept parameters.")
                self.observed = self._client().probe()
                if not self.observed["recording"]:
                    self.uncertain = False
            elif action == "calibrate":
                if set(body) != {"focal_mm"}:
                    raise ValueError("Label the phone's CURRENT framing with focal_mm equivalent.")
                focal = number(body["focal_mm"], "Equivalent focal length", 13, 360)
                self.observed = observed = self._client().probe()
                if observed["recording"]:
                    raise CameraError("Stop recording before lens calibration.")
                if self.config["fingerprint"] != observed["fingerprint"]:
                    self.config.update(calibration=[], fingerprint=observed["fingerprint"])
                    self.config["color"]["operator_confirmed"] = False
                points = [p for p in self.config["calibration"] if p["focal_mm"] != focal]
                points.append(dict(focal_mm=focal, normalised=observed["normalised"]))
                points.sort(key=lambda p: p["focal_mm"])
                if len(points) >= 2:
                    calibration_points(points)
                self.config["calibration"] = points
                self._save()
            elif action == "zoom":
                if set(body) != {"focal_mm"}:
                    raise ValueError("Preview zoom requires focal_mm.")
                points = self._ready()
                observed = self._client().zoom(mapped_zoom(points, body["focal_mm"]))
                return dict(
                    source="device_reported",
                    normalised=observed,
                    focal_mm=body["focal_mm"],
                    mapping="estimated_between_operator_measured_points",
                    optical_framing_verified=False,
                )
            elif action == "color":
                self.config["color"] = color_recipe(body)
                digest = self.config["color"]["cube_sha256"]
                if digest and not (DATA / "phone-luts" / (digest + ".cube")).is_file():
                    raise ValueError("Register the chosen LUT file before confirming its hash.")
                self._save()
            elif action == "lut":
                if set(body) != {"cube", "input_space"} or body["input_space"] not in (
                    "rec709",
                    "apple_log2",
                ):
                    raise ValueError("LUT registration needs cube text and its documented input_space.")
                info = validate_cube(body["cube"])
                folder = DATA / "phone-luts"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / (info["sha256"] + ".cube")).write_bytes(body["cube"].encode("utf-8"))
                return dict(
                    info,
                    input_space=body["input_space"],
                    uploaded_to_phone=False,
                    next_step="Import this exact file and select it in Blackmagic Camera on the phone.",
                )
            else:
                raise ValueError("Unknown phone action.")
            return self.status()

    def test_record(self, body):
        if set(body) != {"seconds"}:
            raise ValueError("Camera-only test requires seconds; it never moves the robot.")
        seconds = number(body["seconds"], "Recording test seconds", 1, 10)
        with self.lock:
            self._idle()
            points = self._ready()
            config = copy.deepcopy(self.config)
            self.owner = "camera-test"
        folder = DATA / "phone-tests" / secrets.token_hex(12)
        plan = dict(
            plan_id="phone-test-" + secrets.token_hex(8),
            duration_s=seconds,
            camera_cues=[dict(time_s=t, focal_mm=points[0][0]) for t in (0, seconds)],
        )
        stop = threading.Event()
        take = PhoneTake(config, plan, folder, stop, client=self._client())
        try:
            with take:
                take.start_clock(time.perf_counter())
                stop.wait(seconds + 0.1)
            return dict(take.report, directory=str(folder), robot_moved=False)
        finally:
            with self.lock:
                self.last_result = take.report
                self.uncertain = take.report["start_attempted"] and not take.report["stop_confirmed"]
                self.owner = None

    def close(self):
        # RobotPlayback owns stopping its worker. Never stop an unowned phone recording.
        pass
