"""Validated values exposed by the offline recording package."""

import math
from dataclasses import dataclass

MIN_ZOOM_FACTOR = 1.0
MAX_ZOOM_FACTOR = 4.0
MIN_ZOOM_DURATION_MS = 250
MAX_ZOOM_DURATION_MS = 10_000
RECORDING_ERROR_CODES = frozenset(
    {
        "invalid_context",
        "finalization_busy",
        "invalid_request_id",
        "invalid_scenario",
        "invalid_take_id",
        "invalid_transition",
        "invalid_zoom",
        "media_integrity_failed",
        "media_unavailable",
        "operation_conflict",
        "runtime_replaced",
        "take_not_found",
        "take_unresolved",
    }
)


class RecordingError(RuntimeError):
    """Bounded error returned at the recording service boundary."""

    def __init__(self, status: int, code: str, message: str):
        if type(status) is not int or status not in {400, 404, 409, 503}:
            raise ValueError("Recording error status is invalid")
        if code not in RECORDING_ERROR_CODES:
            raise ValueError("Recording error code is invalid")
        if not isinstance(message, str) or not message or len(message) > 300:
            raise ValueError("Recording error message is invalid")
        super().__init__(message)
        self.status = status
        self.code = code

    def wire(self):
        return {"status": self.status, "code": self.code, "message": str(self)}


def _factor(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not MIN_ZOOM_FACTOR <= value <= MAX_ZOOM_FACTOR:
        raise ValueError(f"{name} must be within the simulator range 1x to 4x")
    return float(value)


@dataclass(frozen=True, slots=True)
class ZoomRamp:
    """A simulator-only zoom intent, not a calibrated optical capability."""

    start_factor: float
    end_factor: float
    duration_ms: int

    def __post_init__(self):
        object.__setattr__(self, "start_factor", _factor(self.start_factor, "Start factor"))
        object.__setattr__(self, "end_factor", _factor(self.end_factor, "End factor"))
        if (
            type(self.duration_ms) is not int
            or not MIN_ZOOM_DURATION_MS <= self.duration_ms <= MAX_ZOOM_DURATION_MS
        ):
            raise ValueError("Duration must be an integer within the simulator range 250 to 10000 ms")

    def factor_at(self, elapsed_ms):
        if (
            isinstance(elapsed_ms, bool)
            or not isinstance(elapsed_ms, (int, float))
            or not math.isfinite(elapsed_ms)
            or elapsed_ms < 0
        ):
            raise ValueError("Elapsed time must be a finite non-negative number of milliseconds")
        progress = min(float(elapsed_ms) / self.duration_ms, 1.0)
        return self.start_factor + (self.end_factor - self.start_factor) * progress

    def wire(self):
        return {
            "start_factor": self.start_factor,
            "end_factor": self.end_factor,
            "duration_ms": self.duration_ms,
            "rate_factor_per_s": (self.end_factor - self.start_factor) * 1000 / self.duration_ms,
            "bounds_source": "simulator",
        }
