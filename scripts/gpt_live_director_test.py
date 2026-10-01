"""Local-only GPT-Live voice acceptance server for TakeOne.

Robot tools prepare proposals. A separate local operator route approves one
finite cart commissioning test. No AI execution/arming or calibration tools exist.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from takeone.voice.live_robot import BACKEND_INSTRUCTIONS, TOOLS, VOICE_INSTRUCTIONS, ToolSessions

HOST = "127.0.0.1"
OPENAI_HOST = "api.openai.com"
OPENAI_PATH = "/v1/live/sessions"
MODEL = "gpt-live-1"
BACKEND_MODEL = "gpt-5.6-terra"
MAX_REQUEST_BYTES = 65_536
MAX_PROVIDER_BYTES = 131_072
PAGE = Path(__file__).resolve().parents[1] / "apps" / "rehearsal" / "dist" / "gpt-live-test.html"
SCRIPT = Path(__file__).resolve().parents[1] / "apps" / "rehearsal" / "dist" / "gpt-live-test.js"


def session_payload(sdp: str, tools_enabled: bool = True) -> bytes:
    body = {
        "session": {
            "model": MODEL,
            "instructions": VOICE_INSTRUCTIONS
            if tools_enabled
            else "You are TO. This listen-only check has no microphone or robot tools. Say a short greeting.",
            "delegation": {
                "type": "responses",
                "responses": {
                    "model": BACKEND_MODEL,
                    "instructions": BACKEND_INSTRUCTIONS,
                    "tools": TOOLS if tools_enabled else [],
                    "parallel_tool_calls": False,
                },
            },
            "store": False,
        },
        "transport": {"type": "webrtc", "sdp": sdp},
    }
    return json.dumps(body, allow_nan=False, separators=(",", ":")).encode()


class DirectorLiveHandler(BaseHTTPRequestHandler):
    server_version = "TakeOneGPTLiveTest/1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}", flush=True)

    def _reply(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict) -> None:
        self._reply(status, json.dumps(value, separators=(",", ":")).encode())

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        port = self.server.server_port
        return origin in {f"http://{HOST}:{port}", f"http://localhost:{port}"}

    def do_GET(self) -> None:
        if self.path in (
            "/takeone-tokens.css",
            "/takeone-base.css",
            "/takeone-components.css",
            "/gpt-live-test.css",
        ):
            return self._reply(200, PAGE.with_name(self.path[1:]).read_bytes(), "text/css; charset=utf-8")
        if self.path in {
            f"/fonts/{family}-{weight}.woff2"
            for family, weights in (("inter", (400, 500, 600)), ("ibm-plex-mono", (400, 500)))
            for weight in weights
        }:
            return self._reply(200, (PAGE.parent / self.path[1:]).read_bytes(), "font/woff2")
        if self.path == "/":
            return self._reply(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/gpt-live-test.js":
            return self._reply(200, SCRIPT.read_bytes(), "text/javascript; charset=utf-8")
        if self.path == "/gpt-live-tools.js":
            return self._reply(
                200, SCRIPT.with_name("gpt-live-tools.js").read_bytes(), "text/javascript; charset=utf-8"
            )
        if self.path == "/gpt-live-nudge.js":
            return self._reply(
                200, SCRIPT.with_name("gpt-live-nudge.js").read_bytes(), "text/javascript; charset=utf-8"
            )
        if self.path == "/gpt-live-arm.js":
            return self._reply(
                200, SCRIPT.with_name("gpt-live-arm.js").read_bytes(), "text/javascript; charset=utf-8"
            )
        if self.path == "/api/status":
            return self._json(
                200,
                {
                    "ok": True,
                    "model": MODEL,
                    "backend_model": BACKEND_MODEL,
                    "key_present": bool(os.environ.get("OPENAI_API_KEY")),
                    "scope": "operator_confirmed_cart_commissioning",
                },
            )
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        if self.path not in (
            "/api/session",
            "/api/tools",
            "/api/tools/close",
            "/api/nudge/session",
            "/api/nudge/prepare",
            "/api/nudge/start",
            "/api/nudge/status",
            "/api/nudge/heartbeat",
            "/api/nudge/stop",
            "/api/arm/pose",
            "/api/arm/review",
        ):
            return self._json(404, {"ok": False, "error": "Not found"})
        if not self._same_origin():
            return self._json(403, {"ok": False, "error": "Unexpected request origin"})
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            return self._json(400, {"ok": False, "error": "Bounded JSON required"})
        self.connection.settimeout(5)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_REQUEST_BYTES:
            return self._json(400, {"ok": False, "error": "A bounded SDP offer is required"})
        try:
            request = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeError, OSError):
            return self._json(400, {"ok": False, "error": "Invalid JSON request"})
        if self.path.startswith("/api/arm/"):
            try:
                token = self.headers.get("X-TakeOne-Live-Token")
                self.server.tool_sessions.require(token)
                arms = self.server.tool_sessions.tools.arms
                if arms is None:
                    raise ValueError("Arm rehearsal service not attached")
                if not isinstance(request, dict):
                    raise ValueError("Expected object")
                if self.path == "/api/arm/pose":
                    if set(request) != {"source"}:
                        raise ValueError("Expected source only")
                    if request["source"] == "measured_snapshot":
                        self.server.tool_sessions.tools.check_idle()
                    result = arms.set_pose(token, request["source"])
                else:
                    if request:
                        raise ValueError("No review arguments accepted")
                    result = arms.review(token)
                return self._json(200, result)
            except PermissionError as error:
                return self._json(403, {"ok": False, "error": str(error)})
            except (ValueError, TypeError, KeyError, OSError) as error:
                return self._json(409, {"ok": False, "error": str(error)})
        if self.path.startswith("/api/nudge/"):
            try:
                if not isinstance(request, dict):
                    raise ValueError("Expected a JSON object")
                if self.path == "/api/nudge/session":
                    if request:
                        raise ValueError("No arguments accepted")
                    return self._json(201, {"tool_token": self.server.tool_sessions.create()})
                token = self.headers.get("X-TakeOne-Live-Token")
                self.server.tool_sessions.require(token)
                nudges = self.server.tool_sessions.tools.nudges
                if nudges is None:
                    raise ValueError("Cart commissioning service is not attached")
                action = self.path.rsplit("/", 1)[1]
                fields = {
                    "prepare": {"direction"},
                    "start": {"review_id", "plan_id", "request_id", "operator_ready"},
                    "heartbeat": {"run_id"},
                    "status": set(),
                    "stop": set(),
                }
                if set(request) != fields[action]:
                    raise ValueError("Unexpected operator request fields")
                result = getattr(nudges, action)(token, **request)
                return self._json(200, result)
            except PermissionError as error:
                return self._json(403, {"ok": False, "error": str(error)})
            except (ValueError, TypeError, KeyError, OSError) as error:
                return self._json(409, {"ok": False, "error": str(error)})
        if self.path.startswith("/api/tools"):
            token = self.headers.get("X-TakeOne-Live-Token")
            if self.path == "/api/tools/close":
                self.server.tool_sessions.close(token)
                return self._json(200, {"ok": True})
            try:
                if not isinstance(request, dict) or set(request) != {"call_id", "name", "arguments"}:
                    raise ValueError("Expected call_id, name and arguments")
                result = self.server.tool_sessions.execute(token, **request)
                return self._json(200, result)
            except PermissionError as error:
                return self._json(403, {"ok": False, "error": str(error)})
            except (ValueError, TypeError) as error:
                return self._json(400, {"ok": False, "error": str(error)})
        if (
            not isinstance(request, dict)
            or set(request) != {"sdp", "tools_enabled"}
            or type(request["tools_enabled"]) is not bool
        ):
            return self._json(400, {"ok": False, "error": "SDP and tools_enabled are required"})
        sdp = request["sdp"]
        if not isinstance(sdp, str) or not sdp.strip() or len(sdp.encode()) > 61_440:
            return self._json(400, {"ok": False, "error": "A bounded SDP offer is required"})
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return self._json(503, {"ok": False, "error": "OPENAI_API_KEY is not set"})

        existing_token = self.headers.get("X-TakeOne-Live-Token")
        if existing_token and request["tools_enabled"]:
            try:
                self.server.tool_sessions.require(existing_token)
            except PermissionError as error:
                return self._json(403, {"ok": False, "error": str(error)})

        connection = http.client.HTTPSConnection(OPENAI_HOST, timeout=20)
        try:
            connection.request(
                "POST",
                OPENAI_PATH,
                session_payload(sdp, request["tools_enabled"]),
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            raw = response.read(MAX_PROVIDER_BYTES + 1)
            if len(raw) > MAX_PROVIDER_BYTES:
                return self._json(502, {"ok": False, "error": "OpenAI response exceeded its limit"})
            if response.status not in (200, 201):
                print(f"OpenAI Live session creation returned HTTP {response.status}", flush=True)
                return self._json(
                    response.status if 400 <= response.status < 600 else 502,
                    {"ok": False, "error": f"OpenAI Live returned HTTP {response.status}"},
                )
            try:
                result = json.loads(raw)
                session_id = result["session"]["id"]
                answer = result["transport"]["sdp"]
                transport_type = result["transport"]["type"]
                if not isinstance(session_id, str) or not session_id:
                    raise ValueError()
                if transport_type != "webrtc" or not isinstance(answer, str) or not answer:
                    raise ValueError()
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return self._json(502, {"ok": False, "error": "OpenAI returned invalid session data"})
            # Never forward provider credentials or extra session fields to the page.
            self._json(
                201,
                {
                    "session": {"id": session_id},
                    "transport": {"type": "webrtc", "sdp": answer},
                    "tool_token": (existing_token or self.server.tool_sessions.create())
                    if request["tools_enabled"]
                    else None,
                },
            )
        except (OSError, TimeoutError, socket.timeout, http.client.HTTPException):
            self._json(502, {"ok": False, "error": "OpenAI Live could not be reached"})
        finally:
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the loopback TakeOne GPT-Live voice test")
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    if not 1 <= args.port <= 65_535:
        parser.error("port must be between 1 and 65535")
    server = ThreadingHTTPServer((HOST, args.port), DirectorLiveHandler)
    from takeone.cart.nudge import NudgeService
    from takeone.voice.arm_rehearsal import ArmRehearsal
    from takeone.voice.live_robot import LiveRobotTools

    robot_tools = LiveRobotTools(arms=ArmRehearsal())
    robot_tools.nudges = NudgeService(robot_tools.check_idle)
    server.tool_sessions = ToolSessions(robot_tools)
    print(f"TakeOne GPT-Live test: http://{HOST}:{args.port}", flush=True)
    print(
        "One-shot cart commissioning requires separate local operator approval. No autonomous arming.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        robot_tools.nudges.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
