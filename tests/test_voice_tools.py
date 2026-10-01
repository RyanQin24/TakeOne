"""Voice tools: named refusals, quiet latch, idempotent retries, bounded spoken results."""

import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

from takeone.director.api import DirectorAPI
from takeone.director.contracts import ProductionBrief
from takeone.director.repository import SessionRepository
from takeone.director.service import DirectorService
from takeone.director.skills import sample_project
from takeone.recording.voice_bridge import RecordingVoiceBridge
from takeone.voice.live_tokens import LiveTokenGate
from takeone.voice.provider_gemini import GeminiLiveProvider, GeminiTokenError
from takeone.voice.service import VoiceService, VoiceServiceError
from takeone.voice.tools import RESULT_MAX_CHARS, VoiceTools, declarations

from tests.test_session_context import fixture_catalog

SCIPY = importlib.util.find_spec("scipy") is not None
PLAN_ID = "c" * 64
TEN_SECONDS = 10_000_000_000


def fake_preview(settings):
    return {
        "plan_id": PLAN_ID,
        "duration_s": 5.0,
        "summary": {"distance_m": 1.2, "subject_distance_m": 1.4},
        "notes": [],
        "template": {"name": settings["template_id"]},
    }


class Harness(unittest.TestCase):
    with_recording = False
    sample = None  # a skills sample id, or None for a fixture voice session

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.director_service = DirectorService(
            SessionRepository(Path(self.folder.name) / "sessions.sqlite3")
        )
        self.director = DirectorAPI(self.director_service)
        self.voice = VoiceService(self.director_service)
        self.addCleanup(self.voice.close)
        director_session_id = None
        if self.sample:
            sample = sample_project(self.sample)
            created = self.director_service.create(
                str(uuid4()),
                self.director_service.epoch,
                self.director_service.clock() + TEN_SECONDS,
                ProductionBrief.parse(sample["brief"]),
            )
            director_session_id = created["session"]["session_id"]
            outcome = self.director.post(
                "/api/director/creative",
                self.creative_body(
                    str(uuid4()),
                    director_session_id,
                    0,
                    "load_sample",
                    {"skill_id": self.sample},
                ),
            )
            assert outcome["ok"], outcome
            self.director_session_id = director_session_id
        self.recording = None
        if self.with_recording:
            self.recording = RecordingVoiceBridge(self.voice, Path(self.folder.name) / "recording")
            self.addCleanup(self.recording.close)
        session = self.voice.create("offline", director_session_id)
        self.token = session["ownership_token"]
        self.session_id = session["voice_session_id"]
        self.tools = VoiceTools(
            self.voice,
            self.director,
            self.recording,
            compilers={"catalog": fixture_catalog, "compile_preview": fake_preview},
        )

    def creative_body(self, operation_id, session_id, revision, action, payload):
        return {
            "schema_version": 1,
            "operation_id": operation_id,
            "runtime_epoch": self.director_service.epoch,
            "expires_monotonic_ns": str(self.director_service.clock() + TEN_SECONDS),
            "scope": {
                "session_id": session_id,
                "expected_revision": revision,
                "cancellation_generation": 0,
                "take_id": None,
                "plan_id": None,
            },
            "action": action,
            "payload": payload,
        }

    def body(self, tool, arguments, request_id="req-1", **extra):
        snapshot = self.voice.snapshot(self.token)["snapshot"]
        return {
            "schema_version": 1,
            "voice_session_id": self.session_id,
            "scope": snapshot["scope"],
            "generation": snapshot["generation"],
            "expires_monotonic_ns": str(self.voice.clock() + TEN_SECONDS),
            "tool": tool,
            "request_id": request_id,
            "arguments": arguments,
            **extra,
        }

    def call(self, tool, arguments, request_id="req-1", **extra):
        return self.tools.post(self.body(tool, arguments, request_id, **extra), self.token)


class ProposeShotTests(Harness):
    def test_valid_movement_compiles_and_names_its_plan(self):
        result = self.call(
            "propose_shot",
            {
                "template_id": "template_3",
                "subject_motion": "hold",
                "parameters": [{"name": "field_1", "value": 2.0}],
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["plan_id"], PLAN_ID)
        self.assertIn("template_3 ready", result["message"])

    def test_out_of_range_refusal_names_field_and_bounds(self):
        result = self.call(
            "propose_shot",
            {
                "template_id": "template_3",
                "subject_motion": "hold",
                "parameters": [{"name": "field_1", "value": 99.0}],
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "out_of_range")
        self.assertEqual(result["parameter"], "field_1")
        self.assertEqual(result["allowed"], [0.1, 25.0])
        self.assertIn("field_1 is 99", result["message"])

    def test_unknown_parameter_and_unknown_template_are_named(self):
        result = self.call(
            "propose_shot",
            {
                "template_id": "template_3",
                "subject_motion": "hold",
                "parameters": [{"name": "surprise", "value": 1}],
            },
        )
        self.assertEqual((result["ok"], result["parameter"]), (False, "surprise"))
        result = self.call(
            "propose_shot",
            {
                "template_id": "flying_drone",
                "subject_motion": "hold",
                "parameters": [],
            },
            request_id="req-2",
        )
        self.assertEqual(result["code"], "unresolved_movement")

    def test_results_are_capped_for_speech(self):
        def verbose(settings):
            return {**fake_preview(settings), "notes": ["x" * 900]}

        self.tools._compilers["compile_preview"] = verbose
        result = self.call(
            "propose_shot",
            {
                "template_id": "template_3",
                "subject_motion": "hold",
                "parameters": [],
            },
        )
        self.assertLessEqual(len(result["message"]), RESULT_MAX_CHARS)

    def test_speculative_compile_returns_immediately_and_warms(self):
        compiled = []

        def record(settings):
            compiled.append(settings["template_id"])
            return fake_preview(settings)

        self.tools._compilers["compile_preview"] = record
        result = self.call(
            "propose_shot",
            {
                "template_id": "template_3",
                "subject_motion": "hold",
                "parameters": [],
            },
            speculative=True,
        )
        self.assertEqual(result["code"], "warming")
        deadline = time.time() + 5
        while not compiled and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(compiled, ["template_3"])

    def test_envelope_is_enforced(self):
        body = self.body(
            "propose_shot", {"template_id": "template_3", "subject_motion": "hold", "parameters": []}
        )
        with self.assertRaises(VoiceServiceError):
            self.tools.post(body, "not-the-owner")
        body["generation"] += 1
        with self.assertRaises(VoiceServiceError):
            self.tools.post(body, self.token)


class LatchAndTakeTests(Harness):
    with_recording = True

    def start_take(self, request_id="take-1"):
        return self.call("start_take", {"duration_s": 1.0, "plan_id": PLAN_ID}, request_id)

    def test_take_engages_the_latch_then_stop_releases_it(self):
        started = self.start_take()
        self.assertTrue(started["ok"], started)
        self.assertEqual(started["plan_id"], PLAN_ID)
        self.assertIn("silent", started["message"])
        # While the take runs, the conversation is quiet: only stop_take may act.
        refused = self.call(
            "propose_shot",
            {
                "template_id": "template_3",
                "subject_motion": "hold",
                "parameters": [],
            },
            request_id="quiet-1",
        )
        self.assertEqual(refused["code"], "quiet")
        self.assertTrue(refused["snapshot"]["quiet"])
        stopped = self.call("stop_take", {"take_id": started["take_id"]}, "stop-1")
        self.assertTrue(stopped["ok"], stopped)

    def test_replaying_the_same_request_body_yields_one_take(self):
        # A reconnect retry re-sends the identical body; a different body under a
        # reused request ID is a conflict the bridge already refuses.
        body = self.body("start_take", {"duration_s": 1.0, "plan_id": PLAN_ID}, "dup-1")
        first = self.tools.post(body, self.token)
        again = self.tools.post(body, self.token)
        self.assertEqual(first["take_id"], again["take_id"])
        takes = self.recording.recording.list_takes()
        self.assertEqual(len(takes), 1)
        self.assertEqual(takes[0]["plan_id"], PLAN_ID)

    def test_bad_duration_and_bad_plan_are_named(self):
        result = self.call("start_take", {"duration_s": 99}, "bad-1")
        self.assertEqual((result["code"], result["parameter"]), ("out_of_range", "duration_s"))
        result = self.call("start_take", {"duration_s": 1, "plan_id": "nope"}, "bad-2")
        self.assertEqual(result["parameter"], "plan_id")


@unittest.skipUnless(SCIPY, "creative validation imports the previs stack")
class ScriptToolTests(Harness):
    sample = "dialogue"

    def test_revise_text_field_is_the_durable_record(self):
        result = self.call(
            "revise_script",
            {
                "shot_id": "shot-2",
                "field": "action",
                "value_text": "Hold the pause a beat longer.",
            },
        )
        self.assertTrue(result["ok"], result)
        detail = self.director_service.repository.inspect(self.director_session_id)
        shots = [s for scene in detail["creative"]["document"]["scenes"] for s in scene["shots"]]
        self.assertEqual(shots[1]["action"], "Hold the pause a beat longer.")

    def test_selected_line_bounds_are_named(self):
        result = self.call(
            "revise_script",
            {
                "shot_id": "shot-1",
                "field": "selected_line",
                "value_number": 9,
            },
        )
        self.assertEqual(result["parameter"], "selected_line")
        self.assertIn("0 to 2", result["message"])

    def test_unknown_shot_is_refused(self):
        result = self.call(
            "revise_script",
            {
                "shot_id": "shot-99",
                "field": "action",
                "value_text": "x",
            },
        )
        self.assertEqual(result["parameter"], "shot_id")

    def test_approve_script_commits_current_digest(self):
        result = self.call("approve_script", {})
        self.assertTrue(result["ok"], result)
        detail = self.director_service.repository.inspect(self.director_session_id)
        self.assertTrue(detail["creative"]["approved"])

    @unittest.skipUnless(SCIPY, "rehearsal manifest translates movements")
    def test_rehearse_translates_legacy_static_primitives_without_guessing_motion(self):
        approved = self.call("approve_script", {}, "approve-1")
        self.assertTrue(approved["ok"])
        result = self.call("rehearse", {}, "rehearse-1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["studio_link"], f"/?script={self.director_session_id}")
        self.assertEqual(result["blocked_shot_ids"], [])


class DeclarationTests(unittest.TestCase):
    def test_declarations_lock_template_ids_when_supplied(self):
        tools = declarations(["push_in", "hero_orbit"])
        names = [tool["name"] for tool in tools]
        self.assertEqual(
            names,
            [
                "propose_shot",
                "revise_script",
                "approve_script",
                "rehearse",
                "start_take",
                "stop_take",
                "inspect_scene",
                "select_subject",
                "prepare_filming_behavior",
                "start_filming_behavior",
                "adjust_filming_behavior",
                "hold_filming_behavior",
                "stop_filming_behavior",
                "describe_frame",
            ],
        )
        propose = tools[0]["parameters"]
        self.assertEqual(propose["properties"]["template_id"]["enum"], ["push_in", "hero_orbit"])
        self.assertNotIn("enum", declarations()[0]["parameters"]["properties"]["template_id"])


class FakeConnection:
    status_payload = (200, b'{"name": "auth_tokens/abc123"}')
    last_request = None

    def __init__(self, host, timeout=None):
        pass

    def request(self, method, path, body=None, headers=None):
        FakeConnection.last_request = {"method": method, "path": path, "body": body, "headers": headers}

    def getresponse(self):
        status, payload = self.status_payload

        class Response:
            pass

        response = Response()
        response.status = status
        response.read = lambda limit: payload
        return response

    def close(self):
        pass


def gemini(enabled=True, key="k", factory=FakeConnection, model="gemini-3.8-live"):
    return GeminiLiveProvider(
        {
            "schema_version": 1,
            "enabled": enabled,
            "model": model,
            "response_modalities": ["AUDIO"],
            "compression_trigger_tokens": 16000,
            "token_ttl_seconds": 1800,
            "new_session_ttl_seconds": 60,
            "vad_prefix_padding_ms": 20,
            "vad_silence_duration_ms": 650,
            "client_vad_end_silence_ms": 500,
            "semantic_video_min_interval_ms": 1000,
        },
        key,
        connection_factory=factory,
    )


class GeminiProviderTests(unittest.TestCase):
    def test_mint_locks_model_persona_tools_and_compression(self):
        import json

        provider = gemini()
        minted = provider.mint(system_instruction="PERSONA", tools=[{"name": "propose_shot"}])
        self.assertEqual(minted["token"], "auth_tokens/abc123")
        self.assertTrue(minted["single_use"])
        sent = json.loads(FakeConnection.last_request["body"])
        self.assertEqual(sent["uses"], 1)
        setup = sent["bidiGenerateContentSetup"]
        # Whatever is configured arrives on the wire as models/<configured>.
        self.assertEqual(setup["model"], f"models/{provider.config['model']}")
        self.assertEqual(setup["systemInstruction"]["parts"][0]["text"], "PERSONA")
        self.assertEqual(setup["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(setup["contextWindowCompression"]["triggerTokens"], "16000")
        self.assertEqual(setup["tools"][0]["functionDeclarations"][0]["name"], "propose_shot")
        self.assertEqual(FakeConnection.last_request["headers"]["x-goog-api-key"], "k")

    def test_the_model_id_is_configuration_rather_than_a_literal(self):
        import json

        # Whatever is configured arrives on the wire as models/<configured>.
        provider = gemini(model="gemini-live-2.5-flash-preview")
        provider.mint(system_instruction="PERSONA")
        sent = json.loads(FakeConnection.last_request["body"])
        self.assertEqual(sent["bidiGenerateContentSetup"]["model"], "models/gemini-live-2.5-flash-preview")

    def test_a_wrong_model_names_the_value_and_the_accepted_pattern(self):
        with self.assertRaises(ValueError) as caught:
            gemini(model="gpt-4o")
        message = str(caught.exception)
        self.assertIn("gpt-4o", message)
        self.assertIn("gemini-", message)
        self.assertIn("configs/voice-live.json", message)

    def test_an_explicit_allowlist_overrides_the_prefix_check(self):
        from takeone.voice.provider_gemini import validate_config

        base = {
            "schema_version": 1,
            "enabled": False,
            "model": "vertex-live-1",
            "model_allowlist": ["vertex-live-1"],
            "response_modalities": ["AUDIO"],
            "compression_trigger_tokens": 16000,
            "token_ttl_seconds": 1800,
            "new_session_ttl_seconds": 60,
            "vad_prefix_padding_ms": 20,
            "vad_silence_duration_ms": 650,
            "client_vad_end_silence_ms": 500,
            "semantic_video_min_interval_ms": 1000,
        }
        validate_config(base)
        with self.assertRaises(ValueError) as caught:
            validate_config(dict(base, model_allowlist=["something-else"]))
        self.assertIn("vertex-live-1", str(caught.exception))
        self.assertIn("model_allowlist", str(caught.exception))

    def test_disabled_and_keyless_and_failed_mints_are_typed(self):
        with self.assertRaises(GeminiTokenError) as caught:
            gemini(enabled=False).mint(system_instruction="p")
        self.assertEqual(caught.exception.code, "live_disabled")
        with self.assertRaises(GeminiTokenError) as caught:
            gemini(key=None).mint(system_instruction="p")
        self.assertEqual(caught.exception.code, "key_missing")
        FakeConnection.status_payload = (403, b"{}")
        try:
            with self.assertRaises(GeminiTokenError) as caught:
                gemini().mint(system_instruction="p")
            self.assertEqual(caught.exception.code, "mint_failed")
        finally:
            FakeConnection.status_payload = (200, b'{"name": "auth_tokens/abc123"}')

    def test_config_is_strict(self):
        for corrupt in (
            {"model": "gpt-4o"},
            {"enabled": "yes"},
            {"compression_trigger_tokens": 10},
            {"surprise": True},
        ):
            config = {
                "schema_version": 1,
                "enabled": False,
                "model": "gemini-3.8-live",
                "response_modalities": ["AUDIO"],
                "compression_trigger_tokens": 16000,
                "token_ttl_seconds": 1800,
                "new_session_ttl_seconds": 60,
                "vad_prefix_padding_ms": 20,
                "vad_silence_duration_ms": 650,
                "client_vad_end_silence_ms": 500,
                "semantic_video_min_interval_ms": 1000,
            }
            config.update(corrupt)
            if "surprise" in corrupt:
                config.pop("enabled")
            with self.assertRaises(ValueError):
                GeminiLiveProvider(config, "k")


class TokenGateTests(Harness):
    def gate(self, provider=None):
        return LiveTokenGate(
            self.voice,
            self.director,
            provider or gemini(),
            tools=VoiceTools(self.voice, self.director, compilers={"catalog": fixture_catalog}),
        )

    def gate_body(self, **extra):
        snapshot = self.voice.snapshot(self.token)["snapshot"]
        return {
            "schema_version": 1,
            "voice_session_id": self.session_id,
            "scope": snapshot["scope"],
            "generation": snapshot["generation"],
            "expires_monotonic_ns": str(self.voice.clock() + TEN_SECONDS),
            **extra,
        }

    def test_token_ships_production_state_and_locked_tools(self):
        import json

        result = self.gate().post(self.gate_body(), self.token)
        self.assertEqual(result["code"], "token_minted")
        self.assertEqual(result["token"], "auth_tokens/abc123")
        state = result["production_state"]
        self.assertEqual(state["script"], {"available": False, "reason": "no_script_yet"})
        self.assertEqual(state["brief"]["title"], "Offline voice rehearsal")
        sent = json.loads(FakeConnection.last_request["body"])
        setup = sent["bidiGenerateContentSetup"]
        self.assertIn("Never claim hardware readiness", setup["systemInstruction"]["parts"][0]["text"])
        declared = [d["name"] for d in setup["tools"][0]["functionDeclarations"]]
        self.assertIn("start_take", declared)
        self.assertNotIn("sessionResumption", {})  # fresh session: empty handle config

    def test_resume_reuses_the_handle(self):
        import json

        self.gate().post(self.gate_body(resumption_handle="handle-1"), self.token)
        sent = json.loads(FakeConnection.last_request["body"])
        self.assertEqual(sent["bidiGenerateContentSetup"]["sessionResumption"], {"handle": "handle-1"})

    def test_mint_failure_is_a_voice_error_with_snapshot(self):
        with self.assertRaises(VoiceServiceError) as caught:
            self.gate(gemini(enabled=False)).post(self.gate_body(), self.token)
        self.assertEqual(caught.exception.code, "live_disabled")
        self.assertIsNotNone(caught.exception.snapshot)

    def test_ownership_is_required(self):
        with self.assertRaises(VoiceServiceError):
            self.gate().post(self.gate_body(), "wrong-token")


@unittest.skipUnless(SCIPY, "creative validation imports the previs stack")
class DirectorBackedTokenTests(Harness):
    sample = "dialogue"

    def test_state_carries_the_script_and_skill(self):
        gate = LiveTokenGate(
            self.voice,
            self.director,
            gemini(),
            tools=VoiceTools(self.voice, self.director, compilers={"catalog": fixture_catalog}),
        )
        snapshot = self.voice.snapshot(self.token)["snapshot"]
        result = gate.post(
            {
                "schema_version": 1,
                "voice_session_id": self.session_id,
                "scope": snapshot["scope"],
                "generation": snapshot["generation"],
                "expires_monotonic_ns": str(self.voice.clock() + TEN_SECONDS),
            },
            self.token,
        )
        state = result["production_state"]
        self.assertTrue(state["script"]["available"])
        self.assertEqual(state["skill"]["id"], "dialogue")


if __name__ == "__main__":
    unittest.main()
