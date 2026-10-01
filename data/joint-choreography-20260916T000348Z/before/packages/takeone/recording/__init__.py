"""Offline recorder lifecycle with explicit simulated provenance."""

from .contracts import RecordingError, ZoomRamp
from .media import SyntheticMediaWriter
from .service import RecordingService
from .simulated import SimulatedRecorder

__all__ = [
    "RecordingError",
    "RecordingService",
    "SimulatedRecorder",
    "SyntheticMediaWriter",
    "ZoomRamp",
]
