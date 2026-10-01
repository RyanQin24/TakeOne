"""A recording barrier and independent lens scheduler; no serial or render-loop IO."""

import bisect
import json
import threading
import time
from pathlib import Path

from .client import BlackmagicCamera, CameraError, calibration_points, mapped_zoom, number
from .color import apply_color


def lens_schedule(config, plan):
    """The authored lens timeline, or nothing at all.

    A visual-servo take has no authored lens timeline — the rig is aimed by hand
    or by supervised playback and there are no cues to follow. Such a plan says
    so by carrying no `camera_cues` at all, and gets an empty schedule: the lens
    is left exactly where the operator framed it, or set once from `focal_mm`.
    Cues are never fabricated to fill the gap.
    """
    points = calibration_points(config["calibration"])
    cues = plan.get("camera_cues")
    if cues is None:
        if "focal_mm" in plan:
            return [0.0], [mapped_zoom(points, plan["focal_mm"])]
        return [], []
    if not isinstance(cues, list) or not 2 <= len(cues) <= 30001:
        raise ValueError("Prepare a simulator shot with timestamped camera cues before phone capture.")
    times, targets, previous = [], [], -1.0
    for cue in cues:
        stamp = number(cue["time_s"], "Camera cue time", 0, plan["duration_s"] + 1e-7)
        if stamp <= previous:
            raise ValueError("Camera cues must be strictly time ordered.")
        previous = stamp
        times.append(stamp)
        targets.append(mapped_zoom(points, cue["focal_mm"]))
    if times[0] != 0 or abs(times[-1] - plan["duration_s"]) > 1e-6:
        raise ValueError("Camera cues must cover the complete reviewed robot clock.")
    return times, targets


class PhoneTake:
    def __init__(self, config, plan, folder, stop, *, client=None):
        self.config, self.plan, self.folder, self.stop = config, plan, Path(folder), stop
        self.client = client or BlackmagicCamera(
            config["endpoint"],
            config["timeout_s"],
            cert_sha256=config.get("tls_cert_sha256", ""),
        )
        self.times, self.targets = lens_schedule(config, plan)
        self.period = 1 / number(config["zoom_hz"], "Zoom update rate", 1, 20)
        self.finished, self.thread = threading.Event(), None
        self.report = dict(
            schema_version=1,
            plan_id=plan["plan_id"],
            source="device_reported",
            start_attempted=False,
            recording_confirmed=False,
            stop_confirmed=False,
            media_verified=False,
            zoom_mapping="estimated_between_operator_measured_points",
            zoom_commands=0,
            probe_attempts=0,
            max_request_s=0.0,
            error=None,
            samples=[],
        )
        self.closed = False

    def _probe(self):
        """Retry one transient, read-only preflight before any record command."""
        for attempt in range(2):
            self.report["probe_attempts"] = attempt + 1
            try:
                return self.client.probe()
            except CameraError:
                if attempt or self.stop.wait(0.25):
                    raise

    def __enter__(self):
        try:
            if self.stop.is_set():
                raise CameraError("Capture cancelled before recording.")
            observed = self._probe()
            self.report["probe"] = observed
            if observed["recording"]:
                raise CameraError("Phone already recording. TakeOne will not take over or stop that clip.")
            if self.plan.get("schema") == "takeone.studio-motion.v1":
                resolution = observed["format"].get("recordResolution", {})
                width, height = resolution.get("width"), resolution.get("height")
                if type(width) is not int or type(height) is not int or width <= height:
                    raise CameraError(
                        "This robot shot is planned in landscape, but Blackmagic reports portrait or "
                        "unknown recording orientation. Match the phone format before Run on robot."
                    )
            if observed["fingerprint"] != self.config["fingerprint"]:
                raise CameraError(
                    "Phone identity/format changed. Recalibrate this lens and confirm color setup."
                )
            self.report["color"] = apply_color(self.client, self.config["color"])
            self.report["lens_controlled"] = bool(self.targets)
            if self.targets:
                self._zoom(0)
            self.report["start_attempted"] = True
            self.client.request(
                "POST", "/transports/0/record", {"clipName": "TakeOne-" + self.plan["plan_id"][:12]}
            )
            self.client.wait_recording(True)
            self.report.update(recording_confirmed=True, record_ack_clock_s=time.perf_counter())
            if self.stop.is_set():
                raise CameraError("Capture cancelled while waiting for recording acknowledgement.")
            return self
        except (CameraError, ValueError, KeyError) as error:
            self.report["error"] = str(error)
            self.close()
            raise

    def start_clock(self, epoch):
        """Called once with the same perf_counter epoch as motors, offset by approach time."""
        if not self.report["recording_confirmed"] or self.thread:
            raise CameraError("Recording must be acknowledged before starting its lens clock.")
        self.report["shot_epoch_s"] = epoch
        self.thread = threading.Thread(target=self._run, args=(epoch,), name="iphone-lens", daemon=True)
        self.thread.start()

    def _zoom(self, index):
        started = time.perf_counter()
        observed = self.client.zoom(self.targets[index])
        latency = time.perf_counter() - started
        self.report["max_request_s"] = max(self.report["max_request_s"], latency)
        self.report["zoom_commands"] += 1
        self.report["samples"].append(
            dict(
                cue_time_s=self.times[index],
                requested=self.targets[index],
                observed=observed,
                ack_clock_s=time.perf_counter(),
            )
        )
        if abs(observed - self.targets[index]) > 0.02:
            raise CameraError("Phone zoom readback differs from the requested target; inspect lens settings.")

    def _run(self, epoch):
        last, health_at = (self.targets[0] if self.targets else None), 0.0
        try:
            while not self.finished.is_set() and not self.stop.is_set():
                now = time.perf_counter()
                elapsed = now - epoch
                if self.targets:
                    index = max(0, min(len(self.times) - 1, bisect.bisect_right(self.times, elapsed) - 1))
                    if self.targets[index] != last:
                        self._zoom(index)
                        last = self.targets[index]
                if now >= health_at:
                    if not self.client.recording():
                        raise CameraError("Phone stopped recording during robot playback.")
                    if self.client.request("GET", "/system/format") != self.report["probe"]["format"]:
                        raise CameraError("Phone recording format changed during the take.")
                    health_at = now + 1.0
                # A cue-free take has no authored end; it runs until stopped.
                if len(self.times) > 1 and elapsed >= self.times[-1]:
                    break
                # Absolute-clock lookup skips late samples; it never replays a backlog.
                self.finished.wait(self.period)
        except (CameraError, ValueError) as error:
            self.report["error"] = str(error)
            self.stop.set()

    def close(self):
        if self.closed and (not self.report["start_attempted"] or self.report["stop_confirmed"]):
            return
        self.closed = True
        self.finished.set()
        if self.thread:
            self.thread.join()
        if self.report["start_attempted"]:
            try:
                self.client.request("POST", "/transports/0/stop", {})
                self.client.wait_recording(False)
                self.report["stop_confirmed"] = True
            except CameraError as error:
                self.report["stop_error"] = str(error)
                self.report["error"] = self.report["error"] or str(error)
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "phone-capture.json").write_text(
            json.dumps(self.report, indent=2, allow_nan=False), encoding="utf-8"
        )

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        if exc is None and self.report["error"]:
            raise CameraError(self.report["error"])
        return False
