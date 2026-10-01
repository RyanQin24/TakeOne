"""Loopback rehearsal and Director sessions; no motor or cloud endpoints."""

import argparse
import json
import mimetypes
import sqlite3
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from takeone.director.api import DirectorAPI
from takeone.director.repository import SessionRepository
from takeone.director.service import DirectorService, OwnerReplacedError
from takeone.motion.limits import preflight
from takeone.motion.plan import prepare_shot
from takeone.paths import APP as ROOT
from takeone.paths import DATA
from takeone.planning.compiler import compile_shot
from takeone.planning.settings import DEFAULTS, parameters
from takeone.simulation.robot import visual_model


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

    def json_response(self, data, status=200):
        blob = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(blob)

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

    def do_GET(self):
        path = urlparse(self.path).path
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
            model = (
                visual_model(variant, track)
                if track != DEFAULTS["trackWidth"]
                else self.server.model_data[variant]
            )
            return self.json_response(model)
        if path == "/api/shot":
            return self.json_response(self.server.default_shot)
        if path == "/api/health":
            return self.json_response(
                {
                    "ok": True,
                    "mode": "local rehearsal",
                    "workspace": str(ROOT.parents[1]),
                    "hardwareConnected": False,
                    "director": "creative planning",
                }
            )
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        # Consume a bounded body before an early rejection. Closing a Windows
        # socket with unread POST bytes can reset it before the client sees 403.
        try:
            size = int(self.headers.get("Content-Length", "0"))
            limit = 98304 if path == "/api/director/creative" else 16384 if path.startswith("/api/director/") else 4096
            if not 1 <= size <= limit or self.headers.get("Transfer-Encoding") is not None:
                raise ValueError("Invalid request size or framing")
            self.connection.settimeout(5.0)
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete request body")
        except (ValueError, OSError) as error:
            return self.json_response({"error": str(error)}, 400)
        if path not in ("/api/compile", "/api/robot-plan") and not path.startswith("/api/director/"):
            return self.json_response({"error": "Not found"}, 404)
        port = self.server.server_port
        hosts = (f"127.0.0.1:{port}", f"localhost:{port}")
        if self.headers.get("Host") not in hosts:
            return self.json_response({"error": "Local host required"}, 403)
        origin = self.headers.get("Origin")
        if origin and origin not in tuple("http://" + host for host in hosts):
            return self.json_response({"error": "Local origin required"}, 403)
        if self.headers.get_content_type() != "application/json":
            return self.json_response({"error": "JSON content required"}, 415)
        try:
            body = json.loads(raw, object_pairs_hook=unique_fields)
        except (ValueError, TypeError, UnicodeError) as error:
            return self.json_response({"error": str(error)}, 400)
        if path.startswith("/api/director/"):
            return self.director_response(lambda: self.server.director.post(path, body))
        if not self.server.compile_lock.acquire(blocking=False):
            return self.json_response({"error": "A shot is already compiling. Try again shortly."}, 409)
        try:
            if path == "/api/robot-plan":
                shot = compile_shot(body["settings"])
                if body["shotId"] != shot["planId"]:
                    return self.json_response({"error": "Preview changed. Recalculate and review it first."}, 409)
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


def make_server(port, director_database, model_data, default_shot):
    mimetypes.add_type("text/javascript", ".js")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        server.director = DirectorAPI(DirectorService(SessionRepository(director_database)))
    except BaseException:
        server.server_close()
        raise
    server.model_data = model_data
    server.default_shot = default_shot
    server.compile_lock = threading.Lock()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--director-db", type=Path, default=DATA / "director/sessions.sqlite3")
    args = parser.parse_args()
    print("Loading MuJoCo robot and compiling rehearsal…", flush=True)
    models = {variant: visual_model(variant) for variant in ("ring", "panel", "tube")}
    server = make_server(args.port, args.director_db, models, compile_shot())
    print(f"TAKE ONE ready at http://127.0.0.1:{args.port} · Director: /director.html", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
