"""Small deterministic transient-ID tracker over local person detections."""

import math
from dataclasses import dataclass

from .contracts import PersonDetection, TrackedPerson


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / max(area_a + area_b - intersection, 1e-9)


@dataclass(slots=True)
class _Track:
    track_id: str
    bbox_uv: tuple[float, float, float, float]
    center_uv: tuple[float, float]
    last_seen_ns: int
    velocity_uv_s: tuple[float, float] = (0.0, 0.0)


class PersonTracker:
    def __init__(self, *, max_missing_ms=750, max_center_distance=0.28):
        if not 100 <= max_missing_ms <= 10_000:
            raise ValueError("max_missing_ms must be 100 to 10000")
        if not 0.02 <= max_center_distance <= 1:
            raise ValueError("max_center_distance must be 0.02 to 1")
        self.max_missing_ns = int(max_missing_ms * 1_000_000)
        self.max_center_distance = float(max_center_distance)
        self._tracks = {}
        self._next_id = 1

    def _new(self, detection, timestamp_ns):
        track_id = f"person-{self._next_id:04d}"
        self._next_id += 1
        center = _center(detection.bbox_uv)
        track = _Track(track_id, detection.bbox_uv, center, timestamp_ns)
        self._tracks[track_id] = track
        return track

    def _cost(self, track, detection):
        center = _center(detection.bbox_uv)
        distance = math.dist(track.center_uv, center)
        if distance > self.max_center_distance:
            return None
        return distance + 0.35 * (1 - _iou(track.bbox_uv, detection.bbox_uv))

    def update(self, timestamp_ns, detections):
        if type(timestamp_ns) is not int or timestamp_ns < 0:
            raise ValueError("timestamp_ns must be non-negative integer nanoseconds")
        detections = tuple(detections)
        if any(not isinstance(detection, PersonDetection) for detection in detections):
            raise ValueError("PersonTracker accepts PersonDetection values")
        self._tracks = {
            key: track
            for key, track in self._tracks.items()
            if timestamp_ns - track.last_seen_ns <= self.max_missing_ns
        }
        candidates = []
        for track in self._tracks.values():
            for index, detection in enumerate(detections):
                cost = self._cost(track, detection)
                if cost is not None:
                    candidates.append((cost, track.track_id, index))
        candidates.sort()
        assigned_tracks, assigned_detections, matches = set(), set(), {}
        for _cost, track_id, index in candidates:
            if track_id in assigned_tracks or index in assigned_detections:
                continue
            assigned_tracks.add(track_id)
            assigned_detections.add(index)
            matches[index] = self._tracks[track_id]
        visible = []
        for index, detection in enumerate(detections):
            track = matches.get(index) or self._new(detection, timestamp_ns)
            center = _center(detection.bbox_uv)
            elapsed_s = max((timestamp_ns - track.last_seen_ns) / 1_000_000_000, 1e-6)
            velocity = tuple((b - a) / elapsed_s for a, b in zip(track.center_uv, center))
            track.bbox_uv = detection.bbox_uv
            track.center_uv = center
            track.last_seen_ns = timestamp_ns
            track.velocity_uv_s = velocity
            visible.append(
                TrackedPerson(
                    track.track_id,
                    detection.bbox_uv,
                    detection.confidence,
                    velocity,
                    timestamp_ns,
                )
            )
        return tuple(sorted(visible, key=lambda person: person.track_id))

    def reset(self):
        self._tracks.clear()
        self._next_id = 1
