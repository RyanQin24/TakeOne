"""Strict versioned JSON parsing for local voice routes."""

from .contracts import MAX_INTEGER, VoiceScope
from .service import MAX_FIXTURE_DELAY_MS, MAX_QUESTION_BYTES

TOKEN_HEADER = "X-TakeOne-Voice-Token"
ENVELOPE_FIELDS = {
    "schema_version",
    "voice_session_id",
    "scope",
    "generation",
    "expires_monotonic_ns",
}


def _fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    required = set(required)
    optional = set(optional)
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise ValueError(f"Invalid fields; missing: {sorted(missing)}, unknown: {sorted(extra)}")
    return value


def _schema(body):
    if type(body["schema_version"]) is not int or body["schema_version"] != 1:
        raise ValueError("Unsupported voice request schema")


def _integer(value, name, maximum=MAX_INTEGER):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _nanoseconds(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 19:
        raise ValueError("Monotonic nanoseconds must be a decimal string")
    return _integer(int(value), "Monotonic nanoseconds")


def _label(value, name, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain 1 to {maximum} characters")
    return value


def _scope(value):
    _fields(
        value,
        {
            "runtime_epoch",
            "session_id",
            "revision",
            "cancellation_generation",
            "plan_id",
            "take_id",
        },
    )
    return VoiceScope(**value)


def _envelope(body):
    _schema(body)
    return (
        _label(body["voice_session_id"], "Voice session ID"),
        _scope(body["scope"]),
        _integer(body["generation"], "Voice generation"),
        _nanoseconds(body["expires_monotonic_ns"]),
    )


def parse_owned_request(body, required=(), optional=()):
    """Shared strict schema and scoped envelope for voice-owned local operations."""
    _fields(body, ENVELOPE_FIELDS | set(required), optional)
    return _envelope(body)


class VoiceAPI:
    def __init__(self, service):
        self.service = service

    def get(self, path, token=None):
        if path == "/api/voice/runtime":
            return self.service.runtime()
        if path == "/api/voice/snapshot":
            return self.service.snapshot(token)
        raise KeyError("Voice endpoint not found")

    def post(self, path, body, token=None):
        if path == "/api/voice/sessions":
            _fields(body, {"schema_version", "mode"}, {"director_session_id"})
            _schema(body)
            mode = body["mode"]
            if mode not in ("offline", "live"):
                raise ValueError("Voice mode must be offline or live")
            session_id = body.get("director_session_id")
            if session_id is not None:
                session_id = _label(session_id, "Director session ID")
            return self.service.create(mode, session_id)

        routes = {
            "/api/voice/questions": ({"request_id", "question"}, {"fixture_delay_ms"}),
            "/api/voice/interrupt": ({"reason"}, set()),
            "/api/voice/disconnect": (set(), set()),
            "/api/voice/fixture-recording": ({"event_scope", "sequence", "state"}, set()),
            "/api/voice/live-sessions": ({"offer_sdp"}, set()),
        }
        if path not in routes:
            raise KeyError("Voice endpoint not found")
        required, optional = routes[path]
        envelope = parse_owned_request(body, required, optional)

        if path == "/api/voice/questions":
            request_id = _label(body["request_id"], "Request ID")
            question = _label(body["question"], "Question", 4000)
            if len(question.encode("utf-8")) > MAX_QUESTION_BYTES:
                raise ValueError("Question exceeds the 4 KiB UTF-8 limit")
            delay = body.get("fixture_delay_ms")
            if delay is not None:
                _integer(delay, "Fixture delay", MAX_FIXTURE_DELAY_MS)
            return self.service.question(token, *envelope, request_id, question, fixture_delay_ms=delay)
        if path == "/api/voice/interrupt":
            return self.service.interrupt(token, *envelope, _label(body["reason"], "Interrupt reason"))
        if path == "/api/voice/disconnect":
            return self.service.disconnect(token, *envelope)
        if path == "/api/voice/fixture-recording":
            return self.service.fixture_recording(
                token,
                *envelope,
                _scope(body["event_scope"]),
                _integer(body["sequence"], "Recording sequence"),
                _label(body["state"], "Recording state"),
            )
        return self.service.create_live_session(
            token,
            *envelope,
            _label(body["offer_sdp"], "WebRTC offer SDP", 61440),
        )
