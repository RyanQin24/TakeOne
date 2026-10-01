"""`source="phone"` is a real column value, and the fields that stay false, stay false."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from takeone.recording.api import RecordingAPI
from takeone.recording.contracts import RecordingError, ZoomRamp
from takeone.recording.repository import SCHEMA, RecordingRepository
from takeone.recording.service import RecordingService
from takeone.recording.simulated import StartAttempt, StopAttempt

V2_SCHEMA = SCHEMA.replace(
    ",\n    source TEXT NOT NULL DEFAULT 'simulated' CHECK(source IN ('simulated','phone')),\n"
    "    media_location TEXT,\n"
    "    device_reported TEXT",
    "",
).replace("PRAGMA user_version=3;", "PRAGMA user_version=2;")

V2_TAKE = (
    "INSERT INTO recording_takes(take_id,state,scenario,start_request_id,context,zoom,"
    "created_ns,start_request_ns) VALUES ('t1','ready','normal','r1','{}','{}','0','0')"
)


class FakePhoneRecorder:
    def __init__(self):
        self.calls = []

    def request_start(self, take_id, context, requested_ns):
        self.calls.append(("start", take_id))
        return StartAttempt(requested_ns, requested_ns + 2_000_000_000)

    def request_stop(self, take_id, requested_ns):
        self.calls.append(("stop", take_id))
        return StopAttempt("acknowledged")

    def report(self, take_id):
        return {
            "source": "device_reported",
            "start_attempted": True,
            "recording_confirmed": True,
            "stop_confirmed": True,
            "media_verified": False,
        }


def context():
    return {"source": "embodied_behavior", "behavior_id": "behavior-1"}


class PhoneSourceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.phone = FakePhoneRecorder()
        self.service = RecordingService(
            self.root / "takes.sqlite3", self.root / "media", phone_recorder=self.phone
        )
        self.addCleanup(self.service.close)

    def take(self):
        snapshot = self.service.start("r-1", context(), None, source="phone")
        self.service._poll(snapshot["take_id"])
        return snapshot["take_id"]

    def test_a_v2_database_migrates_to_v3_and_keeps_its_rows(self):
        path = self.root / "legacy.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript(V2_SCHEMA)
            connection.execute(V2_TAKE)
        repository = RecordingRepository(path)
        with repository.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
            row = repository.row(connection, "t1")
            snapshot = repository.snapshot(connection, row)
        self.assertEqual(snapshot["source"], "simulated")
        self.assertFalse(snapshot["real_media_verified"])

    def test_only_two_sources_are_accepted(self):
        with self.assertRaises(RecordingError) as caught:
            self.service.start("r-x", context(), None, source="webcam")
        self.assertEqual(caught.exception.code, "invalid_source")
        self.assertIn("simulated", str(caught.exception))
        self.assertIn("phone", str(caught.exception))

    def test_phone_source_refuses_without_an_adapter(self):
        service = RecordingService(self.root / "b.sqlite3", self.root / "b")
        self.addCleanup(service.close)
        with self.assertRaises(RecordingError) as caught:
            service.start("r-1", context(), None, source="phone")
        self.assertEqual(caught.exception.code, "phone_recorder_unavailable")

    def test_a_simulated_take_still_needs_its_zoom_and_scenario(self):
        with self.assertRaises(RecordingError) as caught:
            self.service.start("r-1", context(), None, source="simulated")
        self.assertEqual(caught.exception.code, "invalid_zoom")
        with self.assertRaises(RecordingError) as caught:
            self.service.start(
                "r-2", context(), ZoomRamp(1.0, 2.0, 250), "not_a_scenario", source="simulated"
            )
        self.assertEqual(caught.exception.code, "invalid_scenario")

    def test_a_phone_take_carries_no_media_and_says_where_the_footage_is(self):
        take_id = self.take()
        snapshot = self.service.stop(take_id, "r-stop")
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["source"], "phone")
        self.assertIsNone(snapshot["media"])
        self.assertFalse(snapshot["real_media_verified"])
        self.assertEqual(snapshot["media_location"], "phone_internal_storage")
        self.assertFalse(snapshot["optical_framing_verified"])
        self.assertEqual(snapshot["zoom_mapping"], "estimated_between_operator_measured_points")
        self.assertTrue(snapshot["device_reported"]["recording_confirmed"])
        self.assertFalse(snapshot["device_reported"]["media_verified"])

    def test_the_media_route_refuses_phone_footage_specifically(self):
        class Bridge:
            def __init__(self, take):
                self.take = take

            def read(self, token, take_id):
                return {"take": self.take}

        take_id = self.take()
        take = self.service.stop(take_id, "r-stop")
        api = RecordingAPI(Bridge(take))
        with self.assertRaises(RecordingError) as caught:
            api._media_bytes(None, take_id)
        self.assertEqual(caught.exception.code, "media_on_device")
        self.assertIn("TakeOne has not read these frames", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
