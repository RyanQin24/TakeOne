"""A recording barrier and independent lens scheduler; no serial or render-loop IO."""

import bisect
import json
import math
import threading
import time
from contextlib import nullcontext
from pathlib import Path

from .client import BlackmagicCamera, CameraError, calibration_points, mapped_zoom, number
from .color import apply_color
from .transfer import enqueue


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
        self.health_thread = None
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
            zoom_readbacks=0,
            requested_zoom_hz=1 / self.period,
            optical_smoothness_verified=False,
            probe_attempts=0,
            max_request_s=0.0,
            error=None,
            samples=[],
        )
        self.closed = False
        self.clips_before = None
        self.auto_transfer = bool(config.get("auto_transfer", False))

    def _read_clips(self):
        payload = self.client.request("GET", "/clips")
        if not isinstance(payload, dict) or not isinstance(payload.get("clips"), list):
            raise CameraError("The phone did not return its clip list.")
        clips = payload["clips"]
        if any(not isinstance(c, dict) or "clipUniqueId" not in c for c in clips):
            raise CameraError("The phone clip list has no reliable identifiers.")
        return {str(c["clipUniqueId"]): c for c in clips}

    def _queue_original(self):
        if not self.auto_transfer or self.clips_before is None:
            return
        try:
            # Some phones publish the clip a moment after acknowledging stop.
            for attempt in range(5):
                after = self._read_clips()
                new = [clip for key, clip in after.items() if key not in self.clips_before]
                if new or attempt == 4:
                    break
                time.sleep(0.2)
            if len(new) != 1:
                raise CameraError("Could not identify exactly one new phone clip; no file was guessed.")
            self.report["clip"] = new[0]
            self.report["transfer_job"] = enqueue(new[0], self.folder)
            self.report["transfer_state"] = "queued"
        except (CameraError, OSError, ValueError) as error:
            self.report["transfer_state"] = "needs_attention"
            self.report["transfer_error"] = str(error)

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
            if self.auto_transfer:
                try:
                    self.clips_before = self._read_clips()
                except (CameraError, OSError, ValueError) as error:
                    self.report["transfer_state"] = "needs_attention"
                    self.report["transfer_error"] = str(error)
            self.report["lens_controlled"] = bool(self.targets)
            if self.targets:
                self._zoom(self.targets[0], 0.0)
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
        self.health_thread = threading.Thread(target=self._health, name="iphone-health", daemon=True)
        self.thread = threading.Thread(target=self._run, args=(epoch,), name="iphone-lens", daemon=True)
        self.health_thread.start()
        self.thread.start()

    def _zoom(self, target, cue_time, *, verify=True):
        started = time.perf_counter()
        if verify:
            observed = self.client.zoom(target)
            self.report["zoom_readbacks"] += 1
        else:
            self.client.set_zoom(target)
            observed = None
        latency = time.perf_counter() - started
        self.report["max_request_s"] = max(self.report["max_request_s"], latency)
        self.report["zoom_commands"] += 1
        self.report["samples"].append(
            dict(
                cue_time_s=cue_time,
                requested=target,
                observed=observed,
                source="device_readback" if verify else "http_acknowledged",
                request_s=latency,
                ack_clock_s=time.perf_counter(),
            )
        )
        if verify and abs(observed - target) > 0.02:
            raise CameraError("Phone zoom readback differs from the requested target; inspect lens settings.")

    def _target_at(self, elapsed):
        """Interpolate the reviewed samples, retaining authored holds and endpoints."""
        index = max(0, bisect.bisect_right(self.times, elapsed) - 1)
        if elapsed <= self.times[0]:
            return self.targets[0]
        if index >= len(self.times) - 1:
            return self.targets[-1]
        fraction = (elapsed - self.times[index]) / (self.times[index + 1] - self.times[index])
        return self.targets[index] + fraction * (self.targets[index + 1] - self.targets[index])

    def _health(self):
        # Network checks must not insert pauses into the lens clock. The client
        # owns a fresh connection per request, so concurrent requests share no socket.
        try:
            while not self.finished.wait(1.0) and not self.stop.is_set():
                if not self.client.recording():
                    raise CameraError("Phone stopped recording during robot playback.")
                if self.finished.is_set() or self.stop.is_set():
                    break
                if self.client.request("GET", "/system/format") != self.report["probe"]["format"]:
                    raise CameraError("Phone recording format changed during the take.")
        except (CameraError, ValueError) as error:
            self.report["error"] = str(error)
            self.stop.set()

    def _run(self, epoch):
        moving = len(set(self.targets)) > 1
        stream = getattr(self.client, "zoom_stream", nullcontext) if moving else nullcontext
        try:
            with stream():
                self._run_zoom(epoch)
        except (CameraError, ValueError) as error:
            self.report["error"] = str(error)
            self.stop.set()

    def _run_zoom(self, epoch):
        last = self.targets[0] if self.targets else None
        verify_at = epoch + 0.5
        try:
            while not self.finished.is_set() and not self.stop.is_set():
                now = time.perf_counter()
                elapsed = now - epoch
                if self.targets:
                    target = self._target_at(elapsed)
                    if target != last:
                        verify = now >= verify_at or elapsed >= self.times[-1]
                        self._zoom(target, min(max(0.0, elapsed), self.times[-1]), verify=verify)
                        last = target
                        if verify:
                            verify_at = time.perf_counter() + 0.5
                # A cue-free take has no authored end; it runs until stopped.
                if len(self.times) > 1 and elapsed >= self.times[-1]:
                    break
                # Wait only until the next absolute tick. Request time already
                # consumed part (or all) of this tick; never add a whole period.
                after = time.perf_counter()
                tick = max(0, math.floor(elapsed / self.period) + 1)
                deadline = epoch + tick * self.period
                if len(self.times) > 1 and elapsed < self.times[-1]:
                    deadline = min(deadline, epoch + self.times[-1])
                self.finished.wait(max(0.0, deadline - after))
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
        if self.health_thread:
            self.health_thread.join()
        if self.report["start_attempted"]:
            try:
                self.client.request("POST", "/transports/0/stop", {})
                self.client.wait_recording(False)
                self.report["stop_confirmed"] = True
                self._queue_original()
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
