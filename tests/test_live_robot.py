"""Non-actuating GPT-Live bridge checks: every owner is injected."""

import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from takeone.cart.nudge import NudgeService
from takeone.voice.live_robot import LiveRobotTools, ToolSessions

from scripts.gpt_live_director_test import DirectorLiveHandler, session_payload


class Client:
    def __init__(self):
        self.requests = []
        self.active = False
        self.fail_robot = False

    def request(self, path, body=None, token=None, token_header=None):
        self.requests.append((path, body, token, token_header))
        if path == "/api/live-director/status":
            return dict(armed=False, actuator_available=False, physical_path_verified=False, armable=False)
        if path.endswith("/status"):
            if self.fail_robot and path == "/api/robot/status":
                raise OSError("Owner unreachable")
            return dict(
                active=self.active, phase="idle", token="SECRET", run_id="run-1", runtime_available=True
            )
        if path.endswith("/prepare"):
            return dict(plan_id="plan-1", summary={"physical_path_verified": False})
        return {}


class RobotToolsTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.tools = LiveRobotTools(self.client)

    def test_status_redacts_owner_tokens(self):
        result = self.tools.execute("get_robot_status", {})
        self.assertTrue(result["ok"])
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertFalse(result["voice_motion"]["armed"])

    def test_backward_intent_preserved_without_guessing_distance_or_moving(self):
        result = self.tools.execute("request_robot_move", dict(direction="backward", distance_m=None))
        self.assertEqual(result["requested"], dict(direction="backward", distance_m=None))
        self.assertEqual(result["code"], "relative_motion_unavailable")
        self.assertFalse(result["hardware_moved"])
        self.assertTrue(all(body is None for _, body, _, _ in self.client.requests))

    def test_invalid_and_unknown_tools_never_reach_owner(self):
        for name, args in [
            ("start_robot", {}),
            ("get_robot_status", {"armed": True}),
            ("request_robot_move", dict(direction="backward", distance_m=float("nan"))),
            ("request_robot_move", dict(direction="backward", distance_m=True)),
            ("request_robot_move", dict(direction="rotate", distance_m=1)),
        ]:
            self.assertFalse(self.tools.execute(name, args)["ok"])
        self.assertEqual(self.client.requests, [])

    def test_preparation_never_starts_hardware(self):
        result = self.tools.execute(
            "prepare_robot_shot", dict(template_id="static", distance_m=1, duration_s=2)
        )
        self.assertEqual(result["code"], "prepared_only")
        self.assertFalse(result["hardware_moved"])
        self.assertEqual(self.client.requests[-1][0], "/api/robot/prepare")

    def test_idle_stop_does_not_send_hardware_command(self):
        self.assertTrue(self.tools.execute("stop_robot", {})["ok"])
        self.assertTrue(all(body is None for _, body, _, _ in self.client.requests))

    def test_stop_attempts_both_owners_independently(self):
        self.client.active = True
        self.client.fail_robot = True
        result = self.tools.execute("stop_robot", {})
        self.assertFalse(result["ok"])
        self.assertFalse(result["physical_stop_verified"])
        self.assertEqual(self.client.requests[-1][0], "/api/tracking/stop")

    def test_transport_failure_is_not_completion(self):
        self.client.fail_robot = True
        result = self.tools.execute("get_robot_status", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["physical_state"], "unknown")


class SessionsTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.client = Client()
        self.sessions = ToolSessions(LiveRobotTools(self.client), clock=lambda: self.now)
        self.token = self.sessions.create()

    def call(self, **kwargs):
        return self.sessions.execute(self.token, "call-1", kwargs.get("name", "get_robot_status"), {})

    def test_idempotent_and_conflicting_replay(self):
        self.call()
        count = len(self.client.requests)
        self.call()
        self.assertEqual(len(self.client.requests), count)
        with self.assertRaises(ValueError):
            self.call(name="stop_robot")

    def test_expired_closed_and_missing_tokens(self):
        self.now = 301
        with self.assertRaises(PermissionError):
            self.call()
        self.now = 0
        self.sessions.close(self.token)
        with self.assertRaises(PermissionError):
            self.call()
        with self.assertRaises(PermissionError):
            self.sessions.execute(None, "call", "stop_robot", {})


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DirectorLiveHandler)
        self.server.tool_sessions = ToolSessions(LiveRobotTools(self.client))
        self.token = self.server.tool_sessions.create()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path="/api/tools", origin=None, token=None, body=None):
        port = self.server.server_port
        connection = http.client.HTTPConnection("127.0.0.1", port)
        try:
            connection.request(
                "POST",
                path,
                json.dumps(
                    dict(call_id="c1", name="get_robot_status", arguments={}) if body is None else body
                ),
                {
                    "Origin": origin or f"http://127.0.0.1:{port}",
                    "Content-Type": "application/json",
                    "X-TakeOne-Live-Token": token or self.token,
                },
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_real_http_tool_roundtrip_and_closed_session(self):
        status, result = self.request()
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertNotIn("SECRET", json.dumps(result))
        self.request("/api/tools/close")
        self.assertEqual(self.request()[0], 403)

    def test_cross_origin_and_invalid_token_rejected(self):
        self.assertEqual(self.request(origin="https://example.com")[0], 403)
        self.assertEqual(self.request(token="wrong")[0], 403)
        self.assertEqual(self.client.requests, [])

    def test_no_start_or_arm_route(self):
        self.assertEqual(self.request("/api/robot/start")[0], 404)
        self.assertEqual(self.request("/api/live-director/arm")[0], 404)
        self.assertEqual(self.client.requests, [])

    def test_arm_pose_and_review_routes_require_local_session(self):
        from takeone.voice.arm_rehearsal import ArmRehearsal

        reads = []
        service = ArmRehearsal(snapshot_reader=lambda: reads.append(True))
        self.server.tool_sessions.tools.arms = service
        self.assertEqual(
            self.request("/api/arm/pose", token="wrong", body={"source": "measured_snapshot"})[0], 403
        )
        self.assertEqual(
            self.request("/api/arm/pose", origin="https://example.com", body={"source": "measured_snapshot"})[
                0
            ],
            403,
        )
        self.assertEqual(reads, [])
        status, result = self.request("/api/arm/pose", body={"source": "simulated"})
        self.assertEqual(status, 200)
        self.assertEqual(result["pose_source"], "simulated")
        self.assertEqual(self.request("/api/arm/review", body={})[1]["review"], None)
        self.assertEqual(self.request("/api/arm/run", body={})[0], 404)
        self.request("/api/tools/close", body={})
        self.assertNotIn(self.token, service.contexts)

    def test_payload_has_tools_only_when_enabled(self):
        active = json.loads(session_payload("offer"))["session"]
        silent = json.loads(session_payload("offer", False))["session"]
        self.assertEqual(active["model"], "gpt-live-1")
        self.assertTrue(active["delegation"]["responses"]["tools"])
        self.assertEqual(silent["delegation"]["responses"]["tools"], [])

    def test_operator_review_and_ai_tools_cannot_approve_execution(self):
        launches = []
        with tempfile.TemporaryDirectory() as folder:
            nudges = NudgeService(lambda: None, folder=folder, launcher=lambda *args: launches.append(args))
            self.server.tool_sessions.tools.nudges = nudges
            status, result = self.request(
                body=dict(
                    call_id="move1",
                    name="request_robot_move",
                    arguments=dict(direction="forward", distance_m=None),
                )
            )
            self.assertEqual(status, 200)
            self.assertEqual(result["code"], "operator_review_required")
            review = result["review"]
            status, _ = self.request(
                "/api/nudge/start",
                body=dict(
                    review_id=review["review_id"],
                    plan_id=review["plan_id"],
                    request_id="test-request-123456",
                    operator_ready=False,
                ),
            )
            self.assertEqual(status, 403)
            status, result = self.request(body=dict(call_id="evil", name="start_nudge", arguments={}))
            self.assertFalse(result["ok"])
            self.assertEqual(launches, [])
            self.request("/api/tools/close", body={})
            self.assertIsNone(nudges.status(self.token)["pending"])


if __name__ == "__main__":
    unittest.main()
