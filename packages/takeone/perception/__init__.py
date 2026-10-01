"""Low-latency local perception contracts and transient tracking."""

from .contracts import PerceptionState, PersonDetection, TrackedPerson, VisionFrame
from .tracker import PersonTracker

__all__ = ["PerceptionState", "PersonDetection", "TrackedPerson", "VisionFrame", "PersonTracker"]
