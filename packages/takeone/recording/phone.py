"""Drive a real iPhone take through the RecordingService lifecycle.

`RecordingService` owns the state machine, the deadlines, the event log, the
idempotency ledger and the finalization lease. This adapter changes one thing:
acknowledgement is observed instead of scheduled.

`SimulatedRecorder.request_start` returns a pre-computed clock plan with no I/O,
because a simulator can promise when it will answer. A device cannot. So this
adapter performs the device call first — `PhoneTake.__enter__` already blocks on
the camera's own `wait_recording(True)` readback with a two-second deadline —
and only then reports an acknowledgement time it has actually measured. The
`start_ack_due_ns` it hands back is therefore a recorded instant, not a
prediction, and `_poll` needs no change to interpret it.

Nothing here opens a serial port, moves the robot, or claims TakeOne has seen a
frame of the footage.
"""

import secrets
import threading
import time

from takeone.paths import DATA

from ..phone.capture import PhoneTake
from ..phone.client import CameraError
from .simulated import StartAttempt, StopAttempt

# PhoneTake blocks up to two seconds on the device's own readback. Past that the
# take is `unknown`, never `failed`: the device may well be rolling.
START_BARRIER_S = 2.0


class PhoneRecorder:
    def __init__(self, service, *, root=None, clock=time.monotonic_ns, take_factory=PhoneTake):
        self.service = service
        self.root = root or (DATA / "phone-takes")
        self.clock = clock
        self.take_factory = take_factory
        self.lock = threading.RLock()
        self.takes = {}

    # ── start ───────────────────────────────────────────────────────────────

    def request_start(self, take_id, context, requested_ns):
        with self.lock:
            if take_id in self.takes:
                raise CameraError("This take is already recording on the phone.")
            config = self.service.reserve(self._plan(take_id, context))
            if config is None:
                raise CameraError("iPhone capture is not enabled in configs/iphone-camera.json.")
        folder = self.root / take_id
        plan = self._plan(take_id, context)
        stop = threading.Event()
        take = None
        try:
            take = self.take_factory(config, plan, folder, stop)
            take.__enter__()
        except (CameraError, ValueError, OSError):
            if take is None:
                self.service.release(folder, launched=False)
                raise
            self.service.release(folder, launched=take.report.get("start_attempted", False))
            report = dict(take.report)
            with self.lock:
                self.takes[take_id] = {"take": None, "folder": folder, "stop": stop, "report": report}
            if report.get("start_attempted") and not report.get("recording_confirmed"):
                # The device may be rolling. Timing out now moves the take to
                # `unknown`, which is what an operator has to resolve by looking.
                return StartAttempt(None, requested_ns)
            raise
        take.start_clock(time.perf_counter())
        with self.lock:
            self.takes[take_id] = {"take": take, "folder": folder, "stop": stop, "report": None}
        acknowledged_ns = self.clock()
        return StartAttempt(
            acknowledged_ns,
            acknowledged_ns + int(START_BARRIER_S * 1_000_000_000),
        )

    # ── stop ────────────────────────────────────────────────────────────────

    def request_stop(self, take_id, requested_ns):
        del requested_ns
        with self.lock:
            entry = self.takes.get(take_id)
        if entry is None:
            return StopAttempt("disconnect")
        take = entry["take"]
        if take is None:
            return StopAttempt("disconnect")
        entry["stop"].set()
        take.close()
        entry["report"] = dict(take.report)
        self.service.release(entry["folder"], launched=take.report.get("start_attempted", False))
        if not take.report.get("stop_confirmed"):
            # The device never confirmed. Uncertain, not failed.
            return StopAttempt("timeout", self.clock())
        return StopAttempt("acknowledged")

    def recover(self, take_id):
        """Retire uncertainty only after an explicit device idle readback.

        After restart we cannot own the current clip, so never send stop to it.
        """
        with self.lock:
            entry = self.takes.get(take_id)
        if entry and entry["take"] is not None:
            self.request_stop(take_id, self.clock())
        with self.service.lock:
            observed = self.service._client().probe()
            if observed["recording"]:
                raise CameraError(
                    "The phone is still recording. Stop it on the phone, then resolve this take."
                )
            if observed["fingerprint"] != self.service.config["fingerprint"]:
                raise CameraError(
                    "The phone identity changed. Reconnect the original camera before resolving."
                )
            self.service.observed = observed
            self.service.uncertain = False
        return {"source": "device_reported", "recording": False, "media_verified": False}

    def close(self):
        with self.lock:
            owned = [key for key, entry in self.takes.items() if entry["take"] is not None]
        for take_id in owned:
            self.request_stop(take_id, self.clock())

    # ── evidence ────────────────────────────────────────────────────────────

    def report(self, take_id):
        """Exactly what the device said, plus where the footage is."""
        with self.lock:
            entry = self.takes.pop(take_id, None)
        report = dict((entry or {}).get("report") or {})
        report.setdefault("schema_version", 1)
        report.setdefault("source", "device_reported")
        report.setdefault("start_attempted", False)
        report.setdefault("recording_confirmed", False)
        report.setdefault("stop_confirmed", False)
        # TakeOne never reads these frames, so this can only ever be false here.
        report["media_verified"] = False
        report["media_location"] = "phone_internal_storage"
        report["optical_framing_verified"] = False
        report.setdefault("zoom_mapping", "estimated_between_operator_measured_points")
        return report

    # ── plan ────────────────────────────────────────────────────────────────

    def _plan(self, take_id, context):
        """The take's authored lens timeline, when the caller filmed a reviewed shot.

        A take started from the Record page against a reviewed shot carries that
        shot under `context["shot"]`: its `plan_id`, `duration_s` and the
        simulator's own `camera_cues`. Those cues are what makes the handset's
        lens actually move during the take — a planned Dolly Zoom is a focal
        ramp, and without cues `lens_schedule` returns an empty schedule and the
        lens sits still for the whole clip while the clip still records.

        A behavior-driven take (visual servoing, framed by hand) genuinely has no
        authored timeline, so it still carries no cues. `PhoneTake` handles that
        case explicitly rather than being handed fabricated ones.
        """
        shot = context.get("shot") if isinstance(context, dict) else None
        scope = context.get("scope") if isinstance(context, dict) else None
        plan_id = context.get("plan_id") if isinstance(context, dict) else None
        if not plan_id and isinstance(shot, dict):
            plan_id = shot.get("plan_id")
        if not plan_id and isinstance(scope, dict):
            plan_id = scope.get("plan_id")
        plan = {
            "plan_id": plan_id or ("behavior-" + secrets.token_hex(8)),
            "duration_s": 0,
        }
        if isinstance(shot, dict) and isinstance(shot.get("camera_cues"), list):
            plan["duration_s"] = shot["duration_s"]
            plan["camera_cues"] = [
                {"time_s": cue["time_s"], "focal_mm": cue["focal_mm"]} for cue in shot["camera_cues"]
            ]
        return plan
