"""Loopback rehearsal, Director sessions and explicitly started robot playback."""

import argparse
import hashlib
import json
import mimetypes
import os
import socket
import sqlite3
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from takeone.config import file_hash, process_inputs_changed, read_json
from takeone.direct import direct_shot
from takeone.director.api import DirectorAPI
from takeone.director.repository import SessionRepository
from takeone.director.service import DirectorService, OwnerReplacedError
from takeone.director.studio import SKILL_PATH
from takeone.motion.limits import preflight
from takeone.motion.plan import prepare_shot
from takeone.motion.studio import TOKEN_HEADER as ROBOT_TOKEN_HEADER
from takeone.motion.studio import RobotPlayback
from takeone.paths import APP as ROOT
from takeone.paths import CONFIGS, DATA
from takeone.planning.compiler import compile_shot
from takeone.planning.settings import DEFAULTS, parameters
from takeone.previs.catalog import catalog as orbit_catalog
from takeone.previs.compiler import compile_orbit
from takeone.recording.api import RecordingAPI
from takeone.recording.voice_bridge import RecordingVoiceBridge
from takeone.simulation.robot import visual_model
from takeone.voice.api import TOKEN_HEADER, VoiceAPI
from takeone.voice.live_tokens import LiveTokenGate
from takeone.voice.provider import LiveProvider
from takeone.voice.provider_gemini import GeminiLiveProvider
from takeone.voice.service import VoiceService, VoiceServiceError
from takeone.voice.tools import VoiceTools

SERVER_SOURCE = Path(__file__).resolve()
SERVER_SOURCE_HASH = file_hash(SERVER_SOURCE)


def application_inputs(root=SKILL_PATH.parent.parent.parent):
    """Track interactive code/skills separately from cached motion-model inputs."""
    return {
        str(path.relative_to(root)): file_hash(path)
        for package in ("director", "voice", "recording", "asset_library")
        for pattern in ("*.py", "*.md")
        for path in sorted((root / package).rglob(pattern))
    }


APPLICATION_INPUTS = application_inputs()


def model_etag(model):
    """Content validator for a robot-model payload (mesh JSON is megabytes)."""
    canonical = json.dumps(model, sort_keys=True, separators=(",", ":")).encode()
    return f'"{hashlib.sha256(canonical).hexdigest()[:32]}"'


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

    def translate_path(self, path):
        requested = unquote(urlparse(path).path)
        if requested.startswith("/vendor/"):
            base = (ROOT / "node_modules/three").resolve()
            candidate = (base / requested.removeprefix("/vendor/")).resolve()
            return str(candidate if candidate.is_relative_to(base) else ROOT / "dist/missing")
        return super().translate_path(path)

    def json_response(self, data, status=200, *, etag=None):
        blob = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        # Immutable-per-process payloads (the robot model is megabytes of mesh
        # JSON) carry a validator so reloads revalidate instead of re-downloading.
        # A source or configuration change restarts the process and thus the tag.
        if etag:
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(blob)

    def not_modified(self, etag):
        self.send_response(304)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def director_response(self, operation):
        try:
            result = operation()
            self.json_response(result, 200 if result.get("ok", True) else 409)
        except (ValueError, TypeError) as error:
            self.json_response({"error": str(error)}, 400)
        except KeyError:
            self.json_response({"error": "Director session or endpoint not found."}, 404)
        except OwnerReplacedError as error:
            self.json_response({"error": str(error)}, 409)
        except (sqlite3.Error, OSError):
            self.json_response(
                {"error": "Director storage or configuration is unavailable. Nothing was acknowledged."}, 503
            )

    def local_request_error(self):
        port = self.server.server_port
        hosts = (f"127.0.0.1:{port}", f"localhost:{port}")
        if self.headers.get("Host") not in hosts:
            return "Local host required"
        origin = self.headers.get("Origin")
        if origin and origin not in tuple("http://" + host for host in hosts):
            return "Local origin required"
        return None

    def request_error_response(self, path, message, status, code="invalid_request"):
        if path.startswith(("/api/voice/", "/api/recording/")):
            return self.json_response(
                {
                    "schema_version": 1,
                    "ok": False,
                    "code": code,
                    "message": message[:300],
                },
                status,
            )
        return self.json_response({"error": message}, status)

    def voice_response(self, operation, status=200, *, respond=None):
        try:
            return (respond or self.json_response)(operation(), status)
        except VoiceServiceError as error:
            result = {
                "schema_version": 1,
                "ok": False,
                "code": error.code,
                "message": str(error)[:300],
            }
            if error.snapshot is not None:
                result["snapshot"] = error.snapshot
            return self.json_response(result, error.status)
        except (ValueError, TypeError) as error:
            return self.json_response(
                {
                    "schema_version": 1,
                    "ok": False,
                    "code": "invalid_request",
                    "message": str(error)[:300],
                },
                400,
            )
        except KeyError:
            return self.json_response(
                {
                    "schema_version": 1,
                    "ok": False,
                    "code": "not_found",
                    "message": "Voice endpoint not found.",
                },
                404,
            )
        except OwnerReplacedError:
            return self.json_response(
                {
                    "schema_version": 1,
                    "ok": False,
                    "code": "runtime_changed",
                    "message": "Another Director runtime owns this database. Reload that runtime.",
                },
                409,
            )
        except (sqlite3.Error, OSError):
            return self.json_response(
                {
                    "schema_version": 1,
                    "ok": False,
                    "code": "voice_unavailable",
                    "message": "Voice storage or configuration is unavailable.",
                },
                503,
            )

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/recording/"):
            local_error = self.local_request_error()
            if local_error:
                return self.request_error_response(path, local_error, 403, "local_request_required")
            if urlparse(self.path).query:
                return self.request_error_response(
                    path, "Recording routes do not accept query parameters", 400
                )
            token = self.headers.get(TOKEN_HEADER)
            if path.startswith("/api/recording/takes/") and path.endswith("/media"):
                return self.voice_response(
                    lambda: self.server.recording.media(path, token), respond=self.recording_media_response
                )
            return self.voice_response(lambda: self.server.recording.get(path, token))
        if path == "/api/robot/status":
            error = self.local_request_error()
            if error:
                return self.json_response({"error": error}, 403)
            return self.json_response(self.server.robot.status())
        if path == "/api/previs/orbit":
            return self.json_response(orbit_catalog())
        if path == "/api/previs/templates":
            from takeone.previs.templates import catalog

            return self.json_response(catalog())
        if path.startswith("/api/voice/"):
            local_error = self.local_request_error()
            if local_error:
                return self.json_response(
                    {
                        "schema_version": 1,
                        "ok": False,
                        "code": "local_request_required",
                        "message": local_error,
                    },
                    403,
                )
            if path == "/api/voice/live/status":
                return self.json_response(
                    {"schema_version": 1, "ok": True, **self.server.live_tokens.status()}
                )
            return self.voice_response(lambda: self.server.voice.get(path, self.headers.get(TOKEN_HEADER)))
        if path.startswith("/api/director/"):
            return self.director_response(lambda: self.server.director.get(path))
        if path == "/api/model":
            query = parse_qs(urlparse(self.path).query)
            variant = query.get("lightType", ["ring"])[0]
            if variant not in self.server.model_data:
                return self.json_response({"error": "Unknown light type"}, 400)
            try:
                track = parameters(
                    {"trackWidth": float(query.get("trackWidth", [str(DEFAULTS["trackWidth"])])[0])}
                )["trackWidth"]
            except (ValueError, TypeError):
                return self.json_response({"error": "Invalid wheel separation"}, 400)
            if track == DEFAULTS["trackWidth"]:
                etag = self.server.model_etags[variant]
                if self.headers.get("If-None-Match") == etag:
                    return self.not_modified(etag)
                return self.json_response(self.server.model_data[variant], etag=etag)
            # Built per request, so the validator must cover the full payload
            # (joint limits come from calibration, not only the model XML).
            model = visual_model(variant, track)
            etag = model_etag(model)
            if self.headers.get("If-None-Match") == etag:
                return self.not_modified(etag)
            return self.json_response(model, etag=etag)
        if path == "/api/shot":
            return self.json_response(self.server.default_shot)
        if path == "/api/motors":
            from takeone.motors import motor_table

            return self.json_response(motor_table())
        if path == "/api/health":
            return self.json_response(
                {
                    "ok": True,
                    "mode": "local rehearsal",
                    "workspace": str(ROOT.parents[1]),
                    "hardwareConnected": None if self.server.robot.status()["active"] else False,
                    "robotPlayback": self.server.robot.status()["phase"],
                    "director": "creative planning",
                }
            )
        return super().do_GET()

    def recording_media_response(self, content, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        # Serialize robot requests with the idle-to-restart decision. An active
        # take keeps running; a new take cannot start after shutdown is chosen.
        if urlparse(self.path).path.startswith("/api/robot/"):
            with self.server.robot_request_lock:
                if self.server.restart_requested.is_set():
                    return self.planner_restarting()
                return self.handle_post()
        return self.handle_post()

    def planner_restarting(self):
        return self.json_response(
            {"error": "The simulator is restarting. Please wait a moment.", "code": "planner_restarting"},
            503,
        )

    def handle_post(self):
        path = urlparse(self.path).path
        # Consume a bounded body before an early rejection. Closing a Windows
        # socket with unread POST bytes can reset it before the client sees 403.
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if path == "/api/review-plan":
                limit = 32 * 1024 * 1024
            elif path == "/api/director/creative":
                limit = 98304
            elif path == "/api/voice/live-sessions":
                limit = 65536
            elif path in ("/api/previs/path", "/api/robot/prepare", "/api/previs/sequence"):
                limit = 131072
            elif path.startswith(("/api/director/", "/api/voice/", "/api/recording/")):
                limit = 16384
            else:
                limit = 4096
            if not 1 <= size <= limit or self.headers.get("Transfer-Encoding") is not None:
                raise ValueError("Invalid request size or framing")
            self.connection.settimeout(5.0)
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete request body")
        except (ValueError, OSError) as error:
            return self.request_error_response(path, str(error), 400)
        if (
            path
            not in (
                "/api/compile",
                "/api/direct",
                "/api/pose",
                "/api/robot-plan",
                "/api/review-plan",
                "/api/previs/orbit",
                "/api/previs/path",
                "/api/previs/templates",
                "/api/previs/sequence",
                "/api/previs/reposition",
            )
            and not path.startswith("/api/director/")
            and not path.startswith("/api/voice/")
            and not path.startswith("/api/robot/")
            and not path.startswith("/api/recording/")
        ):
            return self.json_response({"error": "Not found"}, 404)
        local_error = self.local_request_error()
        if local_error:
            return self.request_error_response(path, local_error, 403, code="local_request_required")
        if self.headers.get_content_type() != "application/json":
            return self.request_error_response(path, "JSON content required", 415)
        try:
            body = json.loads(raw, object_pairs_hook=unique_fields)
        except (ValueError, TypeError, UnicodeError) as error:
            return self.request_error_response(path, str(error), 400)
        if path.startswith("/api/robot/"):
            try:
                self.server.robot.authorize(self.headers.get(ROBOT_TOKEN_HEADER))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                if path == "/api/robot/prepare":
                    result = self.server.robot.prepare(body["settings"])
                elif path == "/api/robot/start":
                    result = self.server.robot.start(body["plan_id"], body["request_id"])
                elif path in ("/api/robot/stop", "/api/robot/heartbeat"):
                    result = self.server.robot.command(path.rsplit("/", 1)[1], body["run_id"])
                else:
                    return self.json_response({"error": "Unknown robot endpoint"}, 404)
                return self.json_response(result)
            except PermissionError as error:
                return self.json_response({"error": str(error)}, 403)
            except (ValueError, TypeError, KeyError) as error:
                return self.json_response({"error": str(error)}, 409)
            except OSError as error:
                return self.json_response({"error": f"Robot runtime could not start: {error}"}, 503)
        if path.startswith("/api/director/"):
            return self.director_response(lambda: self.server.director.post(path, body))
        if path.startswith("/api/recording/"):
            if urlparse(self.path).query:
                return self.request_error_response(
                    path, "Recording routes do not accept query parameters", 400
                )
            return self.voice_response(
                lambda: self.server.recording.post(path, body, self.headers.get(TOKEN_HEADER))
            )
        if path == "/api/voice/live/token":
            return self.voice_response(
                lambda: self.server.live_tokens.post(body, self.headers.get(TOKEN_HEADER))
            )
        if path == "/api/voice/tool":
            return self.voice_response(
                lambda: self.server.voice_tools.post(body, self.headers.get(TOKEN_HEADER))
            )
        if path.startswith("/api/voice/"):
            return self.voice_response(
                lambda: self.server.voice.post(path, body, self.headers.get(TOKEN_HEADER)),
                201 if path == "/api/voice/sessions" else 200,
            )
        if path == "/api/pose":
            # Forward kinematics only. Deliberately outside the compile lock so
            # dragging a motor slider never waits on, or rejects against, a shot.
            from takeone.motors import pose_from_counts

            try:
                return self.json_response(pose_from_counts(body))
            except (ValueError, TypeError, KeyError) as error:
                return self.json_response({"error": str(error)}, 400)
        # Two open studios can request a preview at the same time. Queue their
        # calculations instead of leaving one tab on a failed/default scene.
        if not self.server.compile_lock.acquire(timeout=30):
            return self.json_response({"error": "The planner is busy. Retry this preview shortly."}, 503)
        try:
            if self.server.restart_requested.is_set():
                return self.planner_restarting()
            if path == "/api/previs/templates":
                from takeone.previs.cache import compile_preview

                return self.json_response(compile_preview(body))
            if path == "/api/previs/path":
                from takeone.previs.path import compile_path

                return self.json_response(compile_path(body)["preview"])
            if path == "/api/previs/sequence":
                from takeone.previs.sequence import build_program

                return self.json_response(build_program(body))
            if path == "/api/previs/reposition":
                from takeone.previs.reposition import compile_reposition

                return self.json_response(compile_reposition(body))
            if path == "/api/previs/orbit":
                if not isinstance(body, dict):
                    raise ValueError("Expected orbit settings as a JSON object")
                return self.json_response(compile_orbit(body))
            if path == "/api/direct":
                return self.json_response(direct_shot(body))
            if path == "/api/review-plan":
                from takeone.motion.plan import load_plan, reconstruct

                plan = reconstruct(load_plan(body["plan"]))
                shot = compile_shot(plan.to_dict()["settings"])
                return self.json_response(
                    {"plan": plan.to_dict(), "shot": shot, "preflight": preflight(plan)}
                )
            if path == "/api/robot-plan":
                shot = compile_shot(body["settings"])
                if body["shotId"] != shot["planId"]:
                    return self.json_response(
                        {"error": "Preview changed. Recalculate and review it first."}, 409
                    )
                plan = prepare_shot(shot)
                return self.json_response({"plan": plan.to_dict(), "preflight": preflight(plan)})
            return self.json_response(compile_shot(body))
        except (ValueError, TypeError, KeyError) as error:
            return self.json_response({"error": str(error)}, 400)
        except Exception as error:
            print("Compile failed:", repr(error), flush=True)
            return self.json_response({"error": "Shot compilation failed. Previous plan preserved."}, 500)
        finally:
            self.server.compile_lock.release()


class RehearsalServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits two live listeners on this address. Requests
    # then reach different Director owners and saving a script fails randomly.
    allow_reuse_address = os.name != "nt"
    allow_reuse_port = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def request_reload(self):
        if not self.compile_lock.acquire(blocking=False):
            return False
        try:
            with self.robot_request_lock:
                if self.robot.status()["active"]:
                    return False
                self.restart_requested.set()
                return True
        finally:
            self.compile_lock.release()

    def server_close(self):
        if getattr(self, "reload_stop", None) is not None:
            self.reload_stop.set()
        if getattr(self, "recording", None) is not None and not getattr(self, "_recording_closed", False):
            self._recording_closed = True
            self.recording.service.close()
        if getattr(self, "robot", None) is not None:
            self.robot.close()
        if getattr(self, "voice", None) is not None and not getattr(self, "_voice_closed", False):
            self._voice_closed = True
            self.voice.service.close()
        super().server_close()


def make_server(
    port,
    director_database,
    model_data,
    default_shot,
    *,
    director_service=None,
    voice_service=None,
    voice_live_config=None,
    robot_service=None,
    gemini_provider=None,
):
    mimetypes.add_type("text/javascript", ".js")
    server = RehearsalServer(("127.0.0.1", port), Handler)
    server.robot = robot_service or RobotPlayback()
    try:
        director_service = director_service or DirectorService(SessionRepository(director_database))
        server.director = DirectorAPI(director_service)
        if voice_service is None:
            live_provider = LiveProvider(
                voice_live_config
                or {
                    "schema_version": 1,
                    "enabled": False,
                    "model": "gpt-live-1",
                    "timeout_seconds": 10,
                    "max_session_duration_seconds": None,
                }
            )
            voice_service = VoiceService(director_service, live_provider=live_provider)
        server.voice = VoiceAPI(voice_service)
        recording_directory = Path(director_database).parent / "recording"
        recording_bridge = RecordingVoiceBridge(voice_service, recording_directory)
        server.recording = RecordingAPI(recording_bridge)
        # Browser-direct Gemini live transport: this server only mints single-use
        # tokens and answers tool calls; audio never passes through this process.
        gemini = gemini_provider or GeminiLiveProvider(read_json(CONFIGS / "voice-live.json"))
        server.voice_tools = VoiceTools(voice_service, server.director, recording_bridge)
        server.live_tokens = LiveTokenGate(
            voice_service, server.director, gemini, recording_bridge, tools=server.voice_tools
        )
    except BaseException:
        server.server_close()
        raise
    server.model_data = model_data
    server.model_etags = {variant: model_etag(model) for variant, model in model_data.items()}
    server.default_shot = default_shot
    server.compile_lock = threading.Lock()
    server.robot_request_lock = threading.Lock()
    server.restart_requested = threading.Event()
    server.reload_stop = threading.Event()
    return server


def restart_when_sources_change(server, interval_s=1.0):
    """Request a clean restart; the main thread closes the listener before exec.

    Compare to loaded code, not a second disk snapshot taken after startup. That
    second snapshot missed edits made while the initial model was being built.
    """
    while not server.reload_stop.wait(interval_s):
        try:
            if (
                not process_inputs_changed()
                and file_hash(SERVER_SOURCE) == SERVER_SOURCE_HASH
                and application_inputs() == APPLICATION_INPUTS
            ):
                continue
        except OSError:
            continue  # a half-written file during a checkout; look again next tick
        if not server.request_reload():
            continue
        print("Sources changed. Restarting the planner…", flush=True)
        server.shutdown()
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--director-db", type=Path, default=DATA / "director/sessions.sqlite3")
    parser.add_argument("--voice-live-enabled", action="store_true")
    parser.add_argument("--voice-live-timeout-seconds", type=int, default=10)
    parser.add_argument("--voice-live-max-duration-seconds", type=int)
    parser.add_argument("--no-reload", action="store_true", help="Do not restart when sources change")
    parser.add_argument("--no-prewarm", action="store_true", help="Skip warming the preview cache at startup")
    args = parser.parse_args()
    print("Loading MuJoCo robot and direct calibrated motor rehearsal…", flush=True)
    models = {variant: visual_model(variant) for variant in ("ring", "panel", "tube")}
    live_config = {
        "schema_version": 1,
        "enabled": args.voice_live_enabled,
        "model": "gpt-live-1",
        "timeout_seconds": args.voice_live_timeout_seconds,
        "max_session_duration_seconds": args.voice_live_max_duration_seconds,
    }
    # The default shot stays the direct calibrated joint rehearsal, which is what
    # the motor panel and the hardware player both replay.
    server = make_server(
        args.port,
        args.director_db,
        models,
        direct_shot(),
        voice_live_config=live_config,
    )
    print(f"TAKE ONE ready at http://127.0.0.1:{args.port} · Director: /director.html", flush=True)
    if not args.no_prewarm:
        # Voice direction only meets its latency budget on a warm cache: a cold
        # template compile is ~2 s, warm is ~40 ms. Direct calls, no compile lock.
        from takeone.previs.prewarm import start_background

        start_background(log=lambda message: print(message, flush=True))
    if not args.no_reload:
        threading.Thread(
            target=restart_when_sources_change, args=(server,), name="takeone-reload", daemon=True
        ).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    if server.restart_requested.is_set():
        # In particular on Windows, release the listening socket and services
        # before the replacement process tries to bind the same port.
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable, str(SERVER_SOURCE), *sys.argv[1:]])
