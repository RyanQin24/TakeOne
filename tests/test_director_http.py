import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from takeone.motion.plan import load_plan
from takeone.paths import WORKSPACE
from takeone.planning.compiler import compile_shot

spec = importlib.util.spec_from_file_location("rehearsal_server", WORKSPACE / "apps/rehearsal/server.py")
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class DirectorHTTPTests(unittest.TestCase):
    def test_second_listener_cannot_take_over_the_same_address(self):
        address = self.server.server_address
        with self.assertRaises(OSError):
            duplicate = server_module.RehearsalServer(address, server_module.Handler)
            duplicate.server_close()

    def test_creative_endpoint_rejects_non_object_json_without_disconnect(self):
        for raw in (b"null", b"[]", b'"text"'):
            status, result = self.request("/api/director/creative", raw=raw)
            self.assertEqual(status, 400)
            self.assertEqual(result["error"], "Expected a JSON object")

    def test_creative_sample_edit_and_missing_provider_through_http(self):
        status, catalog = self.request("/api/director/planning")
        self.assertEqual(status, 200)
        status, created = self.request(
            "/api/director/sessions",
            {
                **self.envelope(),
                "brief": catalog["samples"]["reaction"],
            },
        )
        self.assertEqual(status, 200)
        from dataclasses import asdict

        from takeone.director.contracts import Session
        from takeone.director.creative import all_shots

        session = Session.parse(created["session"])
        status, selected = self.request(
            "/api/director/creative",
            {
                **self.envelope(),
                "scope": asdict(session.scope()),
                "action": "load_sample",
                "payload": {"skill_id": "reaction"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(selected["ok"])
        session = Session.parse(selected["session"])
        detail = self.request("/api/director/sessions/" + session.session_id)[1]
        document = detail["creative"]["document"]
        all_shots(document)[0]["lines"][0]["text"] = "A user-authored reaction."
        status, saved = self.request(
            "/api/director/creative",
            {
                **self.envelope(),
                "scope": asdict(session.scope()),
                "action": "save_document",
                "payload": {"document": document},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(saved["ok"])
        latest = self.request("/api/director/sessions/" + session.session_id)[1]
        self.assertEqual(
            all_shots(latest["creative"]["document"])[0]["lines"][0]["text"], "A user-authored reaction."
        )
        self.assertEqual(latest["creative"]["provenance"]["source"], "curated_sample")
        self.assertIsNone(latest["session"]["shot"])

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.server = server_module.make_server(
            0,
            Path(cls.folder.name) / "sessions.sqlite3",
            {"ring": {"source": "HTTP test fixture"}},
            {"previewAvailable": True},
        )
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.folder.cleanup()

    def request(self, path, payload=None, headers=None, raw=None):
        data = json.dumps(payload).encode() if payload is not None else raw
        request = Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            content = response.read().decode()
            return response.status, json.loads(content) if content.startswith("{") else content

    def envelope(self):
        runtime = self.request("/api/director/runtime")[1]
        return {
            "schema_version": 1,
            "operation_id": str(uuid4()),
            "runtime_epoch": runtime["runtime_epoch"],
            "expires_monotonic_ns": str(int(runtime["now_monotonic_ns"]) + int(runtime["command_ttl_ns"])),
        }

    def test_robot_plan_endpoint_exports_both_arms_and_rejects_stale_preview(self):
        shot = compile_shot()
        status, result = self.request(
            "/api/robot-plan", {"settings": shot["settings"], "shotId": shot["planId"]}
        )
        self.assertEqual(status, 200, result)
        plan = load_plan(result["plan"])
        self.assertEqual(plan.phone[0], tuple(shot["frames"][0]["q"][3:8]))
        for actual, expected in zip(plan.light[-1], shot["frames"][-1]["q"][8:13]):
            self.assertAlmostEqual(actual, expected, places=12)
        self.assertFalse(result["preflight"]["serial_ports_opened"])
        status, _ = self.request("/api/robot-plan", {"settings": {}, "shotId": "stale"})
        self.assertEqual(status, 409)
        status, _ = self.request("/api/robot-plan", {}, headers={"Origin": "https://example.org"})
        self.assertEqual(status, 403)
        status, _ = self.request("/api/robot-live", {})
        self.assertEqual(status, 404)

    def test_served_ui_and_existing_rehearsal_routes_remain_available(self):
        for path, marker in (
            ("/director.html", "Your next film"),
            ("/director.js", "/api/director/creative"),
            ("/director.css", ".script-paper"),
            ("/", "data-t1-shell"),
            ("/takeone-phases.js", "'Production'"),
        ):
            status, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(marker, body)
        self.assertFalse(self.request("/api/health")[1]["hardwareConnected"])
        self.assertTrue(self.request("/api/shot")[1]["previewAvailable"])

    def test_http_create_revise_inspect_and_stale_rejection(self):
        body = {
            **self.envelope(),
            "brief": {
                "title": "HTTP scenario",
                "objective": "Record a product introduction.",
                "duration_ms": 12000,
                "aspect_ratio": "9:16",
            },
        }
        status, created = self.request("/api/director/sessions", body)
        self.assertEqual(status, 200)
        session = created["session"]
        scope = {
            "session_id": session["session_id"],
            "expected_revision": 0,
            "cancellation_generation": 0,
            "take_id": None,
            "plan_id": None,
        }
        command = {
            **self.envelope(),
            "scope": scope,
            "action": "revise_brief",
            "brief": {**body["brief"], "title": "Revised over HTTP"},
        }
        self.assertEqual(self.request("/api/director/commands", command)[0], 200)
        status, duplicate = self.request("/api/director/commands", command)
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["replayed"])
        stale = {**self.envelope(), "scope": scope, "action": "cancel"}
        status, rejection = self.request("/api/director/commands", stale)
        self.assertEqual(status, 409)
        self.assertEqual(rejection["code"], "stale_scope")
        detail = self.request("/api/director/sessions/" + session["session_id"])[1]
        self.assertEqual(detail["session"]["brief"]["title"], "Revised over HTTP")
        self.assertEqual(detail["session"]["revision"], 1)

    def test_cross_origin_host_and_non_json_requests_cannot_mutate_sessions(self):
        before = len(self.request("/api/director/sessions")[1]["sessions"])
        for headers, status in (
            ({"Origin": "https://untrusted.example"}, 403),
            ({"Host": "untrusted.example"}, 403),
            ({"Content-Type": "text/plain"}, 415),
        ):
            payload = self.envelope() | {"untrusted_body": "x" * 12000}
            self.assertEqual(self.request("/api/director/demo", payload, headers)[0], status)
        self.assertEqual(len(self.request("/api/director/sessions")[1]["sessions"]), before)

    def test_bad_json_duplicate_fields_and_completion_endpoint_rejected(self):
        for raw in (b"{", b'{"schema_version":1,"schema_version":2}', b"x" * 17000):
            self.assertEqual(self.request("/api/director/demo", raw=raw)[0], 400)
        self.assertEqual(self.request("/api/director/complete_job", self.envelope())[0], 404)

    def test_explicit_demonstration_does_not_claim_a_real_take(self):
        status, result = self.request("/api/director/demo", self.envelope())
        self.assertEqual(status, 200)
        self.assertFalse(result["real_media_verified"])
        self.assertEqual(result["session"]["mode"], "demonstration")
        detail = self.request("/api/director/sessions/" + result["session"]["session_id"])[1]
        self.assertTrue(all(job["result"]["evidence"]["source"] == "fixture" for job in detail["jobs"]))


if __name__ == "__main__":
    unittest.main()
