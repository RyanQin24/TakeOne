"""Strict local recording requests and bounded immutable synthetic downloads."""

import hashlib
from uuid import UUID

from takeone.voice.api import parse_owned_request
from takeone.voice.service import MUTATION_TTL_NS, VoiceServiceError

from .contracts import RecordingError, ZoomRamp
from .simulated import SCENARIOS

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024


def take_identity(value):
    try:
        canonical = str(UUID(value)) if isinstance(value, str) else None
    except ValueError:
        canonical = None
    if canonical != value or canonical is None:
        raise ValueError("Take ID must be a canonical UUID")
    return value


class RecordingAPI:
    def __init__(self, service):
        self.service = service

    def runtime(self):
        return {
            "schema_version": 1,
            "ok": True,
            "source": "simulated",
            "offline_available": True,
            "live_available": False,
            "recorder": {"ready": False, "observation_seen": False},
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

    def get(self, path, token=None):
        if path == "/api/recording/runtime":
            return self.runtime()
        if path == "/api/recording/takes":
            return self._with_metadata(token, lambda: self.service.read(token))
        prefix = "/api/recording/takes/"
        if path.startswith(prefix):
            take_id = take_identity(path.removeprefix(prefix))
            return self._with_metadata(token, lambda: self.service.read(token, take_id))
        raise KeyError("Recording endpoint not found")

    def post(self, path, body, token=None):
        prefix = "/api/recording/takes/"
        if path.startswith(prefix) and path.endswith("/review"):
            take_id = take_identity(path.removeprefix(prefix).removesuffix("/review"))
            envelope = parse_owned_request(body)
            return self._with_metadata(token, lambda: self.service.review(token, envelope, take_id))
        if path not in {"/api/recording/start", "/api/recording/stop", "/api/recording/recover"}:
            raise KeyError("Recording endpoint not found")
        kind = path.rsplit("/", 1)[1]
        required = {"request_id", "zoom", "scenario"} if kind == "start" else {"request_id", "take_id"}
        envelope = parse_owned_request(body, required)
        request_id = body["request_id"]
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise ValueError("Request ID must contain 1 to 200 characters")
        options = {}
        if kind == "start":
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
