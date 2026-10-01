"""Loopback HTTP proof for Gemini/local-perception embodied boundaries."""

import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from takeone.director.repository import SessionRepository
from takeone.director.service import DirectorService
from takeone.paths import WORKSPACE

from tests.test_session_context import fixture_catalog
from tests.test_voice_tools import fake_preview

SPEC = importlib.util.spec_from_file_location(
    "rehearsal_server_embodied", WORKSPACE / "apps/rehearsal/server.py"
)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class EmbodiedHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        database = Path(self.folder.name) / "sessions.sqlite3"
        director = DirectorService(SessionRepository(database))
        self.server = SERVER.make_server(
            0,
            database,
            {"ring": {"source": "embodied HTTP fixture"}},
            {"previewAvailable": True},
            director_service=director,
        )
        self.server.voice_tools._compilers = {
            "catalog": fixture_catalog,
            "compile_preview": fake_preview,
        }
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def _close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, path, payload=None, token=None, robot_token=None):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-TakeOne-Voice-Token"] = token
        if robot_token:
            headers["X-TakeOne-Robot-Token"] = robot_token
        request = Request(self.base + path, data=body, headers=headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode())

    def envelope(self, created, snapshot=None):
        snapshot = snapshot or created["snapshot"]
        status, runtime = self.request("/api/voice/runtime")
        self.assertEqual(status, 200)
        return {
            "schema_version": 1,
            "voice_session_id": created["voice_session_id"],
            "scope": snapshot["scope"],
            "generation": snapshot["generation"],
            "expires_monotonic_ns": str(int(runtime["now_monotonic_ns"]) + int(runtime["mutation_ttl_ns"])),
        }

    def test_owned_perception_to_prepared_behavior_stays_disarmed(self):
        status, created = self.request("/api/voice/sessions", {"schema_version": 1, "mode": "offline"})
        self.assertEqual(status, 201, created)
        token = created["ownership_token"]
        perception = {
            **self.envelope(created),
            "perception": {
                "source_frame_age_ms": 20,
                "detections": [{"bbox_uv": [0.25, 0.12, 0.55, 0.88], "confidence": 0.94}],
            },
        }
        status, observed = self.request("/api/voice/perception", perception, token)
        self.assertEqual(status, 200, observed)
        track_id = observed["perception"]["people"][0]["track_id"]
        self.assertEqual(track_id, "person-0001")

        prepared_body = {
            **self.envelope(created, observed["snapshot"]),
            "tool": "prepare_filming_behavior",
            "request_id": "prepare-http-1",
            "arguments": {
                "subject_track_ids": [track_id],
                "subject_relation": "one_person",
                "camera_relation": "approach",
                "framing": "medium",
            },
        }
        status, prepared = self.request("/api/voice/tool", prepared_body, token)
        self.assertEqual(status, 200, prepared)
        self.assertTrue(prepared["ok"], prepared)
        self.assertFalse(prepared["physical_motion"])

        start_body = {
            **self.envelope(created, prepared["snapshot"]),
            "tool": "start_filming_behavior",
            "request_id": "start-http-1",
            "arguments": {"behavior_id": prepared["behavior_id"]},
        }
        status, started = self.request("/api/voice/tool", start_body, token)
        self.assertEqual(status, 200, started)
        self.assertFalse(started["ok"])
        self.assertEqual(started["code"], "live_director_disarmed")
        self.assertFalse(self.server.behavior_manager.snapshot()["armed"])

    def test_operator_arming_requires_both_authorities_and_verified_physical_path(self):
        status, created = self.request("/api/voice/sessions", {"schema_version": 1, "mode": "offline"})
        self.assertEqual(status, 201, created)
        voice_token = created["ownership_token"]
        status, live_status = self.request("/api/live-director/status")
        self.assertEqual(status, 200, live_status)
        self.assertFalse(live_status["armable"])
        self.assertFalse(live_status["armed"])

        arm_body = {
            **self.envelope(created),
            "lease_ms": 30_000,
            "operator_confirmed": True,
        }
        status, denied = self.request("/api/live-director/arm", arm_body, voice_token, "wrong-robot-token")
        self.assertEqual(status, 403, denied)
        self.assertEqual(denied["code"], "robot_authority_required")

        status, robot = self.request("/api/robot/status")
        self.assertEqual(status, 200, robot)
        status, unverified = self.request("/api/live-director/arm", arm_body, voice_token, robot["token"])
        self.assertEqual(status, 409, unverified)
        self.assertEqual(unverified["code"], "physical_path_unverified")
        self.assertFalse(self.server.behavior_manager.snapshot()["armed"])


if __name__ == "__main__":
    unittest.main()
