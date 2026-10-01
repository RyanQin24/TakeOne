"""Ephemeral Gemini Live tokens. This process never proxies audio — the browser
holds the WebSocket, and the API key never leaves this process.

A minted token is single-use (`uses: 1`), must start its session within
`new_session_ttl_seconds`, and locks the model, the persona (system
instruction), the tool declarations and context-window compression so the
browser cannot alter any of them. Configuration changes therefore happen only
here, server-side.

The exact REST body in `_token_request_body` was exercised against the live
v1beta `auth_tokens` service with a real key on 2026-09-17; its field names come
from that run rather than from a reading of the documentation. This module is the only owner of the
provisioning wire format. The tests capture the request and assert the locked
fields and the shape of the URL; they deliberately do not pin an API version
string, which is a question for Google's documentation rather than a unit test.
"""

import http.client
import json
import math
import os
import socket
from datetime import datetime, timedelta, timezone

GEMINI_HOST = "generativelanguage.googleapis.com"
TOKEN_PATH = "/v1beta/auth_tokens"
API_KEY_ENVIRONMENT = "GEMINI_API_KEY"
MAX_RESPONSE_BYTES = 64 * 1_024
# The model id lives in configs/voice-live.json and nowhere else. It used to be
# pinned here by equality, checked at server construction, so a rename Google
# made was a boot failure that no configuration could answer — and the id in
# question had never been tried against the live service. An allow-list read
# from configuration, defaulting to a prefix check, makes the next rename a
# one-line edit to a config file.
KNOWN_MODEL_PREFIXES = ("gemini-", "models/gemini-")


class GeminiTokenError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _rfc3339(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_config(config):
    required = {
        "schema_version",
        "enabled",
        "model",
        "response_modalities",
        "compression_trigger_tokens",
        "token_ttl_seconds",
        "new_session_ttl_seconds",
        "vad_prefix_padding_ms",
        "vad_silence_duration_ms",
        "client_vad_end_silence_ms",
        "semantic_video_min_interval_ms",
    }
    optional = {"model_allowlist"}
    if not isinstance(config, dict) or not required <= set(config) or not set(config) <= required | optional:
        raise ValueError("Invalid voice-live configuration fields")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("Unsupported voice-live configuration schema")
    if type(config["enabled"]) is not bool:
        raise ValueError("voice-live enabled must be true or false")
    model = config["model"]
    allowlist = config.get("model_allowlist")
    if allowlist is not None:
        if (
            not isinstance(allowlist, list)
            or not allowlist
            or any(not isinstance(name, str) or not name for name in allowlist)
        ):
            raise ValueError("voice-live model_allowlist must list one or more model ids")
        if model not in allowlist:
            raise ValueError(
                f"voice-live model {model!r} is not in model_allowlist "
                f"({', '.join(allowlist)}); set it in configs/voice-live.json"
            )
    elif not isinstance(model, str) or not model.startswith(KNOWN_MODEL_PREFIXES):
        raise ValueError(
            f"voice-live model {model!r} does not look like a Gemini model id; "
            f"expected one starting with {' or '.join(KNOWN_MODEL_PREFIXES)}, "
            "or list it explicitly in model_allowlist in configs/voice-live.json"
        )
    modalities = config["response_modalities"]
    if (
        not isinstance(modalities, list)
        or not modalities
        or any(m not in ("AUDIO", "TEXT") for m in modalities)
    ):
        raise ValueError("response_modalities must list AUDIO and/or TEXT")
    for name, low, high in (
        ("compression_trigger_tokens", 1_000, 1_000_000),
        ("token_ttl_seconds", 60, 1_800),
        ("new_session_ttl_seconds", 10, 300),
        ("vad_prefix_padding_ms", 0, 1_000),
        ("vad_silence_duration_ms", 100, 2_000),
        ("client_vad_end_silence_ms", 300, 2_000),
        ("semantic_video_min_interval_ms", 1_000, 60_000),
    ):
        value = config[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not low <= value <= high
        ):
            raise ValueError(f"{name} must be between {low} and {high}")
    return config


class GeminiLiveProvider:
    """Mints ephemeral tokens with the session configuration locked server-side."""

    def __init__(
        self,
        config,
        api_key=None,
        *,
        connection_factory=http.client.HTTPSConnection,
        now=lambda: datetime.now(timezone.utc),
    ):
        self.config = validate_config(config)
        self._api_key = api_key if api_key is not None else os.environ.get(API_KEY_ENVIRONMENT)
        self._connect = connection_factory
        self._now = now

    def status(self):
        return {
            "transport": "gemini_live_browser_direct",
            "enabled": self.config["enabled"],
            "model": self.config["model"],
            "key_present": bool(self._api_key),
            "available": self.config["enabled"] and bool(self._api_key),
            "client_vad_end_silence_ms": self.config["client_vad_end_silence_ms"],
            "semantic_video_min_interval_ms": self.config["semantic_video_min_interval_ms"],
        }

    def _token_request_body(self, *, system_instruction, tools, resumption_handle):
        """Build the constrained v1beta BidiGenerateContent configuration."""
        setup = {
            "model": f"models/{self.config['model']}",
            "generationConfig": {
                "responseModalities": self.config["response_modalities"],
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}],
            },
            "contextWindowCompression": {
                "slidingWindow": {},
                "triggerTokens": str(int(self.config["compression_trigger_tokens"])),
            },
            "sessionResumption": ({"handle": resumption_handle} if resumption_handle else {}),
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "disabled": False,
                    "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                    "endOfSpeechSensitivity": "END_SENSITIVITY_HIGH",
                    "prefixPaddingMs": int(self.config["vad_prefix_padding_ms"]),
                    "silenceDurationMs": int(self.config["vad_silence_duration_ms"]),
                }
            },
        }

        if tools:
            setup["tools"] = [{"functionDeclarations": tools}]

        moment = self._now()

        return {
            "uses": 1,
            "expireTime": _rfc3339(moment + timedelta(seconds=self.config["token_ttl_seconds"])),
            "newSessionExpireTime": _rfc3339(
                moment + timedelta(seconds=self.config["new_session_ttl_seconds"])
            ),
            "bidiGenerateContentSetup": setup,
        }

    def mint(self, *, system_instruction, tools=(), resumption_handle=None):
        """One single-use token. Raises GeminiTokenError; never returns a fake token."""
        if not self.config["enabled"]:
            raise GeminiTokenError("live_disabled", "Voice live transport is disabled in configuration.")
        if not self._api_key:
            raise GeminiTokenError("key_missing", f"Set {API_KEY_ENVIRONMENT} in the server environment.")
        body = self._token_request_body(
            system_instruction=system_instruction,
            tools=list(tools),
            resumption_handle=resumption_handle,
        )
        connection = self._connect(GEMINI_HOST, timeout=10)
        try:
            connection.request(
                "POST",
                TOKEN_PATH,
                body=json.dumps(body),
                headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            )
            response = connection.getresponse()
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, socket.timeout, http.client.HTTPException) as error:
            raise GeminiTokenError("mint_unreachable", f"Token service unreachable: {error}") from error
        finally:
            connection.close()
        # Status first: a large error body used to be reported as "exceeded the
        # bounded size", which hid the real HTTP status behind a transport
        # complaint. Bodies may carry quota or key details, so the status is all
        # that is ever echoed.
        if response.status != 200:
            raise GeminiTokenError("mint_failed", f"Token service answered HTTP {response.status}.")
        if len(payload) > MAX_RESPONSE_BYTES:
            raise GeminiTokenError("mint_failed", "Token response exceeded the bounded size.")
        try:
            token = json.loads(payload)["name"]
        except (ValueError, KeyError, TypeError) as error:
            raise GeminiTokenError("mint_failed", "Token response had no token name.") from error
        if not isinstance(token, str) or not token:
            raise GeminiTokenError("mint_failed", "Token response had no token name.")
        return {
            "token": token,
            "model": self.config["model"],
            "expire_time": body["expireTime"],
            "new_session_expire_time": body["newSessionExpireTime"],
            "single_use": True,
            "client_vad_end_silence_ms": self.config["client_vad_end_silence_ms"],
            "semantic_video_min_interval_ms": self.config["semantic_video_min_interval_ms"],
        }
