"""Emit real API/service wire responses for offline browser-boundary tests."""

import importlib.util
import json
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from takeone.director.contracts import Command, ProductionBrief, Session
from takeone.director.repository import SessionRepository
from takeone.director.service import COMMAND_TTL_NS, DirectorService
from takeone.paths import WORKSPACE
from takeone.voice.api import VoiceAPI
from takeone.voice.contracts import RecordingEvent, VoiceScope
from takeone.voice.provider import LiveSession
from takeone.voice.service import VoiceService, VoiceServiceError


class Provider:
    def status(self):
        return {
            "available": True,
            "state": "configured_unverified",
            "model": "gpt-live-1",
            "provider": "openai",
            "max_session_duration_ms": 60000,
        }

    def create_session(self, offer, cancellation):
        return LiveSession("injected", "injected answer")

    def hangup(self, session):
        pass


def end_first_wire():
    spec = importlib.util.spec_from_file_location(
        "voice_loopback_server", WORKSPACE / "apps/rehearsal/server.py"
    )
    server_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server_module)
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "director.sqlite3"
        director = DirectorService(SessionRepository(database))
        server = server_module.make_server(
            0,
            database,
            {"source": "offline wire fixture"},
            {"previewAvailable": True},
            director_service=director,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(path, body=None, token=None):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["X-TakeOne-Voice-Token"] = token
            request = Request(
                f"http://127.0.0.1:{server.server_port}" + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers=headers,
            )
            try:
                response = urlopen(request, timeout=5)
            except HTTPError as error:
                response = error
            with response:
                return {"status": response.status, "payload": json.load(response)}

        def envelope(created, snapshot):
            return {
                "schema_version": 1,
                "voice_session_id": created["voice_session_id"],
                "scope": snapshot["scope"],
                "generation": snapshot["generation"],
                "expires_monotonic_ns": str(director.clock() + COMMAND_TTL_NS),
            }

        try:
            result = {"runtime": request("/api/voice/runtime")["payload"]}
            session = Session.parse(
                director.create(
                    str(uuid4()),
                    director.epoch,
                    director.clock() + COMMAND_TTL_NS,
                    ProductionBrief("End-first production", "Rehearse", 12000, "9:16"),
                )["session"]
            )
            result["director_id"] = session.session_id
            result["created"] = request(
                "/api/voice/sessions",
                {
                    "schema_version": 1,
                    "mode": "offline",
                    "director_session_id": session.session_id,
                },
            )
            created = result["created"]["payload"]
            token = created["ownership_token"]
            revised = director.submit(
                Command(
                    str(uuid4()),
                    director.epoch,
                    director.clock() + COMMAND_TTL_NS,
                    session.scope(),
                    "revise_brief",
                    ProductionBrief("Revised before End", "Rehearse", 12000, "9:16"),
                )
            )
            assert revised["ok"]
            result["rejected"] = request(
                "/api/voice/disconnect", envelope(created, created["snapshot"]), token
            )
            assert result["rejected"]["status"] == 409
            assert result["rejected"]["payload"]["code"] == "stale_scope"
            result["ended"] = request(
                "/api/voice/disconnect",
                envelope(created, result["rejected"]["payload"]["snapshot"]),
                token,
            )
            result["fresh"] = request("/api/voice/sessions", {"schema_version": 1, "mode": "offline"})
            fresh = result["fresh"]["payload"]
            result["answered"] = request(
                "/api/voice/questions",
                {
                    **envelope(fresh, fresh["snapshot"]),
                    "request_id": str(uuid4()),
                    "question": "A fresh question",
                },
                fresh["ownership_token"],
            )
            assert result["answered"]["status"] == 200
            return result
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def wire():
    with tempfile.TemporaryDirectory() as folder:

        def clock():
            return 1_000_000_000

        director = DirectorService(SessionRepository(Path(folder) / "director.sqlite3"), clock)
        session = director.create(
            str(uuid4()),
            director.epoch,
            clock() + COMMAND_TTL_NS,
            ProductionBrief("Wire test", "Offline boundary", 12000, "9:16"),
        )["session"]
        service = VoiceService(
            director,
            live_provider=Provider(),
            recorder_ready=True,
            conversation_backend=object(),
            clock=clock,
        )
        api = VoiceAPI(service)
        result = {"runtime": api.get("/api/voice/runtime"), "director_id": session["session_id"]}

        def envelope(created, snapshot):
            return {
                "schema_version": 1,
                "voice_session_id": created["voice_session_id"],
                "scope": snapshot["scope"],
                "generation": snapshot["generation"],
                "expires_monotonic_ns": str(clock() + COMMAND_TTL_NS),
            }

        try:
            live = api.post(
                "/api/voice/sessions",
                {"schema_version": 1, "mode": "live", "director_session_id": session["session_id"]},
            )
            result["live_created"] = live
            token = live["ownership_token"]
            result["live_unknown"] = api.get("/api/voice/snapshot", token)
            scope = VoiceScope(**live["snapshot"]["scope"])
            result["live_idle"] = service.observe_recorder(
                RecordingEvent(scope, 0, "idle", "recorder", clock(), clock() + 5_000_000_000)
            )
            result["live_active"] = api.post(
                "/api/voice/live-sessions",
                {**envelope(live, result["live_idle"]["snapshot"]), "offer_sdp": "injected offer"},
                token,
            )
            result["live_requested"] = service.observe_recorder(
                RecordingEvent(scope, 1, "requested", "recorder", clock(), clock() + 5_000_000_000)
            )
            result["live_stale_stop"] = service.observe_recorder(
                RecordingEvent(scope, 1, "stopped", "recorder", clock(), clock() + 5_000_000_000)
            )
            with service._lock:
                service._state.observe_recording(
                    RecordingEvent(scope, 2, "stopped", "fixture", clock(), clock() + 5_000_000_000)
                )
            result["live_fixture_stop"] = api.get("/api/voice/snapshot", token)
            result["live_stopped"] = service.observe_recorder(
                RecordingEvent(scope, 2, "stopped", "recorder", clock(), clock() + 5_000_000_000)
            )
            result["live_disconnected"] = api.post(
                "/api/voice/disconnect", envelope(live, result["live_active"]["snapshot"]), token
            )
            offline = api.post("/api/voice/sessions", {"schema_version": 1, "mode": "offline"})
            result["offline_created"] = offline
            token = offline["ownership_token"]
            requested = api.post(
                "/api/voice/fixture-recording",
                {
                    **envelope(offline, offline["snapshot"]),
                    "event_scope": offline["snapshot"]["scope"],
                    "sequence": 1,
                    "state": "requested",
                },
                token,
            )
            result["requested"] = requested
            result["offline_disconnected"] = api.post(
                "/api/voice/disconnect", envelope(offline, requested["snapshot"]), token
            )
            stopped = api.post(
                "/api/voice/fixture-recording",
                {
                    **envelope(offline, result["offline_disconnected"]["snapshot"]),
                    "event_scope": offline["snapshot"]["scope"],
                    "sequence": 2,
                    "state": "stopped",
                },
                token,
            )
            result["stopped"] = stopped
            result["clean_disconnected"] = api.post(
                "/api/voice/disconnect", envelope(offline, stopped["snapshot"]), token
            )
            result["fresh_offline"] = api.post(
                "/api/voice/sessions", {"schema_version": 1, "mode": "offline"}
            )
            fresh = result["fresh_offline"]
            api.post("/api/voice/disconnect", envelope(fresh, fresh["snapshot"]), fresh["ownership_token"])
            scoped = api.post(
                "/api/voice/sessions",
                {"schema_version": 1, "mode": "offline", "director_session_id": session["session_id"]},
            )
            result["scoped_created"] = scoped
            token = scoped["ownership_token"]
            director.submit(
                Command(
                    str(uuid4()),
                    director.epoch,
                    clock() + COMMAND_TTL_NS,
                    Session.parse(session).scope(),
                    "revise_brief",
                    ProductionBrief("Revised wire", "Offline boundary", 12000, "9:16"),
                )
            )
            try:
                api.post(
                    "/api/voice/fixture-recording",
                    {
                        **envelope(scoped, scoped["snapshot"]),
                        "event_scope": scoped["snapshot"]["scope"],
                        "sequence": 1,
                        "state": "requested",
                    },
                    token,
                )
            except VoiceServiceError as error:
                result["scoped_rejected"] = {"code": error.code, "snapshot": error.snapshot}
            result["scoped_stopped"] = api.post(
                "/api/voice/fixture-recording",
                {
                    **envelope(scoped, result["scoped_rejected"]["snapshot"]),
                    "event_scope": scoped["snapshot"]["scope"],
                    "sequence": 2,
                    "state": "stopped",
                },
                token,
            )
            result["scoped_disconnected"] = api.post(
                "/api/voice/disconnect",
                envelope(scoped, result["scoped_stopped"]["snapshot"]),
                token,
            )
            return result
        finally:
            service.close()


if __name__ == "__main__":
    print(json.dumps({**wire(), "end_first": end_first_wire()}))
