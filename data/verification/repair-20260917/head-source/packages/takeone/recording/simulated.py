"""Deterministic acknowledgements for offline recorder rehearsal."""

from dataclasses import dataclass

SCENARIOS = frozenset(
    {
        "normal",
        "delayed_start",
        "start_timeout",
        "disconnect",
        "stop_timeout",
        "save_failure",
        "corrupt_media",
    }
)


@dataclass(frozen=True, slots=True)
class StartAttempt:
    acknowledge_at_ns: int | None
    timeout_at_ns: int


@dataclass(frozen=True, slots=True)
class StopAttempt:
    outcome: str
    timeout_at_ns: int | None = None


def _milliseconds(value, name):
    if type(value) is not int or value < 0 or value > 60_000:
        raise ValueError(f"{name} must be an integer from 0 to 60000 ms")


class SimulatedRecorder:
    """A clock-plan producer that opens no camera, microphone or device."""

    def __init__(self, *, start_delay_ms=100, delayed_start_ms=2_000, timeout_ms=3_000):
        _milliseconds(start_delay_ms, "Start delay")
        _milliseconds(delayed_start_ms, "Delayed start")
        _milliseconds(timeout_ms, "Timeout")
        if start_delay_ms >= timeout_ms or delayed_start_ms >= timeout_ms:
            raise ValueError("Acknowledgement delays must be shorter than the timeout")
        self.start_delay_ms = start_delay_ms
        self.delayed_start_ms = delayed_start_ms
        self.timeout_ms = timeout_ms

    def request_start(self, take_id, scenario, requested_ns):
        del take_id
        if scenario not in SCENARIOS:
            raise ValueError("Unknown simulated recording scenario")
        delay_ms = self.delayed_start_ms if scenario == "delayed_start" else self.start_delay_ms
        acknowledge_at_ns = None if scenario == "start_timeout" else requested_ns + delay_ms * 1_000_000
        return StartAttempt(acknowledge_at_ns, requested_ns + self.timeout_ms * 1_000_000)

    def request_stop(self, take_id, scenario, requested_ns):
        del take_id
        if scenario == "disconnect":
            return StopAttempt("disconnect")
        if scenario == "stop_timeout":
            return StopAttempt("timeout", requested_ns + self.timeout_ms * 1_000_000)
        return StopAttempt("acknowledged")
