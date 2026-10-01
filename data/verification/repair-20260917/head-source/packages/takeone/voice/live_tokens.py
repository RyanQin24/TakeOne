"""The /api/voice/live/token gate: one owned request, one single-use Gemini token.

The browser asks with its voice ownership token and scoped envelope; this gate
assembles the locked session — persona, tool declarations, bounded production
state — and mints a token the browser can spend exactly once. The API key and
persona never reach the client. On resume the browser sends its resumption
handle and receives a fresh token with a freshly regenerated production state.
"""

import hashlib
import json

from .api import parse_owned_request
from .persona import build_persona
from .provider_gemini import GeminiTokenError
from .service import VoiceServiceError
from .session_context import build_production_state, cached_production_state

MAX_RESUMPTION_HANDLE_CHARS = 512


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class LiveTokenGate:
    def __init__(self, voice, director, provider, recording=None, *, tools=None):
        self.voice = voice
        self.director = director  # DirectorAPI: public reads stay on the public surface
        self.provider = provider
        self.recording = recording  # RecordingVoiceBridge or None
        self.tools = tools  # VoiceTools, for the locked declarations

    def status(self):
        return self.provider.status()

    def _verdicts(self):
        if self.recording is None:
            return []
        repository = self.recording.recording.repository
        with repository.connect() as connection:
            return repository.recent_verdicts(connection)

    def _catalog(self):
        # One catalog source for both the locked declarations and the state block.
        if self.tools is not None:
            return self.tools._catalog()
        from takeone.director.studio import movement_catalog

        return movement_catalog()

    def _production_state(self, director_session_id, fixture_context):
        from takeone.config import provenance
        from takeone.director.skills import SKILLS

        if director_session_id is None:
            # A fixture session still gets a truthful, minimal block.
            return build_production_state(
                session_id="none",
                brief=fixture_context["brief"],
                document=None,
                document_digest=None,
                verdicts=self._verdicts(),
                catalog=self._catalog(),
            ), None
        detail = self.director.service.repository.inspect(director_session_id)
        creative = detail.get("creative")
        skill = None
        if creative and creative["context"].get("skill_id") in SKILLS:
            skill = SKILLS[creative["context"]["skill_id"]]
        key = (
            director_session_id,
            creative["digest"] if creative else "none",
            _digest(provenance()),
        )
        state = cached_production_state(
            key,
            lambda: build_production_state(
                session_id=director_session_id,
                brief=detail["session"]["brief"],
                document=creative["document"] if creative else None,
                document_digest=creative["digest"] if creative else None,
                skill=skill,
                verdicts=self._verdicts(),
                catalog=self._catalog(),
            ),
        )
        return state, skill

    def post(self, body, token):
        envelope = parse_owned_request(body, (), ("resumption_handle",))
        handle = body.get("resumption_handle")
        if handle is not None and not (
            isinstance(handle, str) and 0 < len(handle) <= MAX_RESUMPTION_HANDLE_CHARS
        ):
            raise ValueError("resumption_handle must be a bounded string")
        authority = self.voice.live_authority(token, envelope)
        state, skill = self._production_state(authority["director_session_id"], authority["context"])
        persona = build_persona(skill)
        declarations = self.tools.declarations() if self.tools else []
        try:
            minted = self.provider.mint(
                system_instruction=persona,
                tools=declarations,
                resumption_handle=handle,
            )
        except GeminiTokenError as error:
            raise VoiceServiceError(503, error.code, str(error), snapshot=authority["snapshot"]) from error
        from .tools import LATENCY, PREAMBLES

        return {
            "schema_version": 1,
            "ok": True,
            "code": "token_minted",
            **minted,
            "production_state": state,
            # The browser speaks the preamble before any compile-class tool call;
            # no tool may hold the turn past this budget without one.
            "tool_latency": LATENCY,
            "tool_preambles": PREAMBLES,
            "preamble_required_after_ms": 150,
            "snapshot": authority["snapshot"],
        }
