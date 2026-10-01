"""The behavior recorder derives its request identities instead of minting them.

A settle event can arrive twice — the same perception frame replayed, a retried
request, a restarted poll. If the adapter generated a fresh request ID each
time, the second one would open a second take. Deriving it from the behavior and
the plan makes the duplicate replay through `recording_operations` instead.
"""

import tempfile
import unittest
from pathlib import Path

from takeone.embodied.contracts import FilmingGoal
from takeone.embodied.recorder import (
    BehaviorRecordingAdapter,
    start_request_id,
    stop_request_id,
)
from takeone.recording.service import RecordingService
from takeone.recording.simulated import StartAttempt, StopAttempt

PLAN_ID = "c" * 64


class FakePhoneRecorder:
    """Stands in for a device: acknowledges immediately, confirms the stop."""

    def __init__(self):
        self.started = []
        self.stopped = []
        self.clock = 1_000_000_000

    def request_start(self, take_id, context, requested_ns):
        self.started.append((take_id, context))
        return StartAttempt(requested_ns, requested_ns + 2_000_000_000)

    def request_stop(self, take_id, requested_ns):
        self.stopped.append(take_id)
        return StopAttempt("acknowledged")

    def report(self, take_id):
        return {
            "schema_version": 1,
            "source": "device_reported",
            "start_attempted": True,
            "recording_confirmed": True,
            "stop_confirmed": True,
            "media_verified": False,
            "record_ack_clock_s": 12.5,
            "zoom_mapping": "estimated_between_operator_measured_points",
        }


def goal():
    return FilmingGoal(
        subject_track_ids=("person-0004",),
        subject_relation="one_person",
        camera_relation="approach",
        framing="medium",
        screen_target_uv=(0.5, 0.5),
        desired_subject_size_range=(0.2, 0.7),
        recording_policy="after_settle",
        max_duration_s=8,
        lost_target_policy="hold",
    )


class BehaviorRecorderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.phone = FakePhoneRecorder()
        self.service = RecordingService(root / "takes.sqlite3", root / "media", phone_recorder=self.phone)
        self.addCleanup(self.service.close)
        self.adapter = BehaviorRecordingAdapter(self.service, motion_source="operator_manual")

    def test_request_identities_are_derived_and_stable(self):
        first = start_request_id("behavior-1", PLAN_ID)
        self.assertEqual(first, start_request_id("behavior-1", PLAN_ID))
        self.assertNotEqual(first, start_request_id("behavior-2", PLAN_ID))
        self.assertNotEqual(
            stop_request_id("take-1", "target_lost:person-0004"),
            stop_request_id("take-1", "operator_stop"),
        )

    def test_a_duplicated_settle_replays_instead_of_opening_a_second_take(self):
        first = self.adapter.start(PLAN_ID, goal(), "behavior-1")
        second = self.adapter.start(PLAN_ID, goal(), "behavior-1")
        self.assertIsInstance(first, str)
        self.assertEqual(first, second)
        self.assertEqual(len(self.phone.started), 1, "the device must be asked exactly once")

    def test_context_records_the_aim_reference_and_its_unmeasured_offset(self):
        self.adapter.start(PLAN_ID, goal(), "behavior-1")
        _, context = self.phone.started[0]
        self.assertEqual(context["aim_reference"], "witness_camera")
        self.assertEqual(context["witness_to_lens_offset"], "unmeasured")
        self.assertEqual(context["motion_source"], "operator_manual")
        self.assertEqual(context["identity_scope"], "transient_visual_tracks_not_person_identity")

    def test_stop_reason_survives_into_the_evidence_trail(self):
        take_id = self.adapter.start(PLAN_ID, goal(), "behavior-1")
        self.service._poll(take_id)
        self.adapter.stop(take_id, "target_lost:person-0004")
        take = self.service.read_take(take_id) if hasattr(self.service, "read_take") else None
        if take is None:
            with self.service.repository.connect() as connection:
                row = self.service.repository.row(connection, take_id)
                take = self.service.repository.snapshot(connection, row)
        self.assertEqual(take["state"], "ready")
        self.assertEqual(take["source"], "phone")
        self.assertFalse(take["real_media_verified"])
        self.assertIsNone(take["media"])
        self.assertEqual(take["media_location"], "phone_internal_storage")
        kinds = [event["kind"] for event in take["events"]]
        self.assertIn("device_reported_stop", kinds)


if __name__ == "__main__":
    unittest.main()
