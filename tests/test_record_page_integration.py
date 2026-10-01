"""Record page HTTP contracts with fake phone IO and the real ownership bridge."""

import unittest
from uuid import uuid4

from tests import test_recording_api as recording_http
from tests.test_recording_phone_source import FakePhoneRecorder


class RecordPageIntegrationTests(unittest.TestCase):
    setUp = recording_http.RecordingHTTPTests.setUp
    launch = recording_http.RecordingHTTPTests.launch
    stop_server = recording_http.RecordingHTTPTests.stop_server
    request = recording_http.RecordingHTTPTests.request
    create = recording_http.RecordingHTTPTests.create
    envelope = recording_http.RecordingHTTPTests.envelope
    mutate = recording_http.RecordingHTTPTests.mutate
    take = recording_http.RecordingHTTPTests.take

    def attach_phone(self):
        self.phone = FakePhoneRecorder()
        self.server.behavior_recorder.service.phone_recorder = self.phone
        self.create()

    def test_phone_start_needs_no_simulated_fixture_and_stop_releases_quiet(self):
        self.attach_phone()
        status, started, _ = self.request(
            "/api/recording/start",
            {**self.envelope(), "request_id": str(uuid4()), "source": "phone"},
            token=self.token,
        )
        self.assertEqual(status, 200, started)
        take_id = started["take"]["take_id"]
        rolling = self.take(take_id)
        self.assertEqual(rolling["take"]["state"], "recording")
        self.assertTrue(rolling["snapshot"]["quiet"])
        self.assertEqual(rolling["take"]["source"], "phone")
        status, stopped, _ = self.mutate("stop", take_id)
        self.assertEqual(status, 200, stopped)
        self.assertEqual(stopped["take"]["state"], "ready")
        self.assertFalse(stopped["snapshot"]["recording_latch_active"])
        self.assertFalse(stopped["take"]["real_media_verified"])
        self.assertIsNone(stopped["take"]["media"])
        status, media, _ = self.request(f"/api/recording/takes/{take_id}/media", token=self.token)
        self.assertEqual(status, 409, media)
        self.assertEqual(media["code"], "media_on_device")

    def perception(self):
        status, result, _ = self.request(
            "/api/voice/perception",
            {
                **self.envelope(),
                "perception": {
                    "source_frame_age_ms": 0,
                    "detections": [{"bbox_uv": [0.35, 0.3, 0.65, 0.7], "confidence": 0.99}],
                },
            },
            token=self.token,
        )
        self.assertEqual(status, 200, result)
        return result

    def test_observe_capture_keeps_voice_ownership_and_silence_without_arming(self):
        self.attach_phone()
        manager = self.server.behavior_manager
        manager._compiler = lambda settings: {"plan_id": "a" * 64}
        reading = self.perception()
        track_id = reading["perception"]["people"][0]["track_id"]
        status, prepared, _ = self.request(
            "/api/voice/tool",
            {
                **self.envelope(),
                "request_id": str(uuid4()),
                "tool": "prepare_filming_behavior",
                "arguments": {
                    "subject_track_ids": [track_id],
                    "subject_relation": "one_person",
                    "camera_relation": "hold",
                    "framing": "medium",
                    "recording_policy": "after_settle",
                },
            },
            token=self.token,
        )
        self.assertEqual(status, 200, prepared)
        self.assertTrue(prepared["ok"], prepared)
        status, observing, _ = self.request(
            "/api/live-director/observe",
            {**self.envelope(), "behavior_id": prepared["behavior_id"], "motion_source": "operator_manual"},
            token=self.token,
        )
        self.assertEqual(status, 200, observing)
        for _ in range(4):
            self.perception()
        starts = [entry for entry in self.phone.calls if entry[0] == "start"]
        self.assertEqual(len(starts), 1)
        take_id = starts[0][1]
        rolling = self.take(take_id)
        self.assertTrue(rolling["snapshot"]["recording_latch_active"])
        self.assertEqual(rolling["take"]["context"]["voice_session_id"], self.owner["voice_session_id"])
        status, stopped, _ = self.request(
            "/api/live-director/stop-observing",
            self.envelope(),
            token=self.token,
        )
        self.assertEqual(status, 200, stopped)
        final = self.take(take_id)
        self.assertEqual(final["take"]["state"], "ready")
        self.assertFalse(final["snapshot"]["recording_latch_active"])


if __name__ == "__main__":
    unittest.main()
