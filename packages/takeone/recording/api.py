"""Strict local recording requests and bounded immutable synthetic downloads."""

import hashlib
from uuid import UUID

from takeone.voice.api import parse_owned_request
from takeone.voice.service import MUTATION_TTL_NS, VoiceServiceError

from .contracts import RecordingError, ZoomRamp
from .simulated import SCENARIOS

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
# A reviewed lens timeline is bounded here so an unbounded browser payload can
# never reach the take context, which is stored and fingerprinted. The authority
# on cue ordering and coverage stays `phone.capture.lens_schedule`.
MAX_CAMERA_CUES = 2000


def take_identity(value):
    try:
        canonical = str(UUID(value)) if isinstance(value, str) else None
    except ValueError:
        canonical = None
    if canonical != value or canonical is None:
        raise ValueError("Take ID must be a canonical UUID")
    return value


def _finite(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return value


def shot_reference(value):
    """The reviewed shot a phone take is filming, including its lens timeline.

    Without this the phone recorder had no authored lens cues at all, so the
    handset recorded while its lens stayed exactly where the operator left it:
    a planned Dolly Zoom produced a static frame. The cues are the simulator's
    own `camera_cues` for the plan being shot, carried through unchanged.
    """
    if not isinstance(value, dict) or value.keys() - {
        "plan_id",
        "duration_s",
        "camera_cues",
        "scene_id",
        "label",
    }:
        raise ValueError("shot accepts plan_id, duration_s, camera_cues, scene_id and label")
    plan_id = value.get("plan_id")
    if plan_id is not None and not (
        isinstance(plan_id, str)
        and len(plan_id) == 64
        and all(character in "0123456789abcdef" for character in plan_id)
    ):
        raise ValueError("shot plan_id must be a lowercase SHA-256 digest")
    duration = _finite(value["duration_s"], "shot duration_s", 0.25, 600)
    cues = value["camera_cues"]
    if not isinstance(cues, list) or not 2 <= len(cues) <= MAX_CAMERA_CUES:
        raise ValueError(f"shot camera_cues must hold 2 to {MAX_CAMERA_CUES} entries")
    cleaned = []
    for cue in cues:
        if not isinstance(cue, dict) or cue.keys() != {"time_s", "focal_mm"}:
            raise ValueError("Each camera cue needs exactly time_s and focal_mm")
        cleaned.append(
            {
                "time_s": _finite(cue["time_s"], "Camera cue time_s", 0, duration),
                "focal_mm": _finite(cue["focal_mm"], "Camera cue focal_mm", 13, 360),
            }
        )
    for key in ("scene_id", "label"):
        text = value.get(key)
        if text is not None and not (isinstance(text, str) and 0 < len(text) <= 120):
            raise ValueError(f"shot {key} must be 1 to 120 characters")
    return {
        "plan_id": plan_id,
        "duration_s": duration,
        "camera_cues": cleaned,
        "scene_id": value.get("scene_id"),
        "label": value.get("label"),
    }


class RecordingAPI:
    def __init__(self, service, phone=None):
        self.service = service
        # Optional. When present, `live_available` and `recorder.ready` are
        # computed from what the device actually reported, never from what the
        # configuration claims: `enabled: true` is not evidence of anything.
        self.phone = phone

    def _device(self):
        if self.phone is None:
            return None, False, False
        try:
            status = self.phone.status()
        except Exception:
            return None, False, False
        observed = status.get("observed")
        if not isinstance(observed, dict):
            return None, False, False
        reachable = bool(observed.get("product"))
        idle = reachable and observed.get("recording") is False and not status.get("uncertain")
        return observed, reachable, idle

    def runtime(self):
        observed, reachable, idle = self._device()
        return {
            "schema_version": 1,
            "ok": True,
            "source": "simulated",
            "offline_available": True,
            "live_available": reachable,
            "recorder": {"ready": idle, "observation_seen": observed is not None},
            "now_monotonic_ns": str(self.service.voice.clock()),
            "mutation_ttl_ns": str(MUTATION_TTL_NS),
            "clock_domain": "server_monotonic",
            "simulator": {
                "zoom_min_factor": 1,
                "zoom_max_factor": 4,
                "zoom_min_duration_ms": 250,
                "zoom_max_duration_ms": 10000,
                "scenarios": sorted(SCENARIOS),
                "dolly_zoom_available": False,
            },
        }

    def _with_metadata(self, token, operation):
        try:
            return operation()
        except RecordingError as error:
            snapshot = self.service.voice.recording_authority(token)["snapshot"]
            raise VoiceServiceError(error.status, error.code, str(error), snapshot=snapshot) from error

    def sync(self, *, write=False):
        """What of the phone's footage has reached this computer, and what has not.

        Read-only with respect to take state: it inspects the inbox folder and
        joins by clip name. A take stays `on_phone` until a file carrying its
        name is actually on this disk.
        """
        from takeone.phone.transfer import status as transfer_status

        from .sync import reconcile, write_manifest

        report = reconcile(self.service.recording.list_takes())
        report["transfer"] = transfer_status()
        if write:
            report["manifest_path"] = str(write_manifest(report))
        return {"schema_version": 1, "ok": True, "code": "recording_sync", **report}

    def get(self, path, token=None):
        if path == "/api/recording/runtime":
            return self.runtime()
        if path == "/api/recording/sync":
            return self.sync()
        if path == "/api/recording/takes":
            return self._with_metadata(token, lambda: self.service.read(token))
        prefix = "/api/recording/takes/"
        if path.startswith(prefix):
            take_id = take_identity(path.removeprefix(prefix))
            return self._with_metadata(token, lambda: self.service.read(token, take_id))
        raise KeyError("Recording endpoint not found")

    def post(self, path, body, token=None):
        if path == "/api/recording/sync":
            # Reads the inbox and writes one manifest beside it. It starts no
            # take, touches no device and changes no take's recorded evidence.
            return self.sync(write=True)
        prefix = "/api/recording/takes/"
        if path.startswith(prefix) and path.endswith("/review"):
            take_id = take_identity(path.removeprefix(prefix).removesuffix("/review"))
            envelope = parse_owned_request(body)
            return self._with_metadata(token, lambda: self.service.review(token, envelope, take_id))
        if path not in {"/api/recording/start", "/api/recording/stop", "/api/recording/recover"}:
            raise KeyError("Recording endpoint not found")
        kind = path.rsplit("/", 1)[1]
        source = body.get("source", "simulated") if kind == "start" else "simulated"
        if source not in {"simulated", "phone"}:
            raise ValueError("source must be simulated or phone")
        optional = {"shot"} if kind == "start" and source == "phone" else set()
        required = (
            ({"request_id", "source"} if source == "phone" else {"request_id", "zoom", "scenario"})
            if kind == "start"
            else {"request_id", "take_id"}
        )
        envelope = parse_owned_request(body, required, optional)
        request_id = body["request_id"]
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise ValueError("Request ID must contain 1 to 200 characters")
        options = {}
        if kind == "start" and source == "phone":
            options["source"] = source
            if body.get("shot") is not None:
                options["shot"] = shot_reference(body["shot"])
        elif kind == "start":
            zoom = body["zoom"]
            if not isinstance(zoom, dict) or zoom.keys() != {"start_factor", "end_factor", "duration_ms"}:
                raise ValueError("Zoom requires exactly start_factor, end_factor and duration_ms")
            options["zoom"] = ZoomRamp(**zoom)
            scenario = body["scenario"]
            if not isinstance(scenario, str) or scenario not in SCENARIOS:
                raise ValueError("Unknown simulator scenario")
            options["scenario"] = scenario
        else:
            options["take_id"] = take_identity(body["take_id"])
        return self._with_metadata(
            token, lambda: self.service.mutate(kind, token, envelope, request_id, **options)
        )

    def media(self, path, token):
        take_id = take_identity(path.removeprefix("/api/recording/takes/").removesuffix("/media"))
        return self._with_metadata(token, lambda: self._media_bytes(token, take_id))

    def _media_bytes(self, token, take_id):
        take = self.service.read(token, take_id)["take"]
        media = take["media"]
        if take["source"] == "phone":
            # A clean, specific refusal rather than a 500: the footage is on the
            # handset and this server does not have it.
            raise RecordingError(
                409,
                "media_on_device",
                "The clip is on the phone. TakeOne has not read these frames.",
            )
        if take["state"] != "ready" or media is None or take["source"] != "simulated":
            raise RecordingError(409, "media_unavailable", "Validated synthetic media is unavailable.")
        relative = f"{take_id}/synthetic.mp4"
        root = self.service.recording.media_root.resolve()
        path = (root / relative).resolve()
        if (
            media.get("relative_path") != relative
            or path.parent != root / take_id
            or type(media.get("size_bytes")) is not int
            or not 0 < media["size_bytes"] <= MAX_DOWNLOAD_BYTES
        ):
            raise RecordingError(409, "media_integrity_failed", "Stored synthetic media identity is invalid.")
        try:
            with path.open("rb") as stream:
                # Validate the very bytes sent, with bounded allocation even if
                # the file changes after it was originally published.
                content = stream.read(MAX_DOWNLOAD_BYTES + 1)
        except OSError:
            raise RecordingError(
                409, "media_integrity_failed", "Stored synthetic media is missing."
            ) from None
        if len(content) != media["size_bytes"] or hashlib.sha256(content).hexdigest() != media.get("sha256"):
            raise RecordingError(409, "media_integrity_failed", "Stored synthetic media content changed.")
        return content
