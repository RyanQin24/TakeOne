"""Loopback phone routes.

`PhoneService` has existed with seven actions and was instantiated by nothing;
this is the dispatcher that gives it a door. It follows the shape of
`RecordingAPI`: one `get`, one `post`, path validation here, device behaviour in
the service.

Three rules this file exists to keep:

- No phone route commands robot motion, and none of these actions is reachable
  from the voice tool dispatcher. Gemini may talk about the camera; it may not
  press record on it.
- Every action is explicit. `probe` is the only one that contacts the device
  without a prior device-touching action in the same interaction, and it still
  needs the token.
- `hardware_verified` is whatever the service says, which is `False`. A config
  saying `enabled: true` is not evidence that a device is present.
"""

from .client import CameraError
from .service import TOKEN_HEADER, PhoneService  # noqa: F401  (re-exported for the server)

# The cube validator accepts up to 4 MiB of text, so the transport has to as
# well; a smaller guess here would reject a valid LUT at the wrong layer with
# the wrong message. The slack covers JSON escaping.
LUT_BODY_LIMIT = 4 * 1024 * 1024 + 8 * 1024
BODY_LIMITS = {
    "/api/phone/configure": 4 * 1024,
    "/api/phone/probe": 4 * 1024,
    "/api/phone/format": 4 * 1024,
    "/api/phone/calibrate": 4 * 1024,
    "/api/phone/zoom": 4 * 1024,
    "/api/phone/color": 16 * 1024,
    "/api/phone/lut": LUT_BODY_LIMIT,
    "/api/phone/test-record": 4 * 1024,
}
ACTIONS = {path.rsplit("/", 1)[-1] for path in BODY_LIMITS}


class PhoneAPIError(RuntimeError):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code


class PhoneAPI:
    def __init__(self, service):
        self.service = service

    # ── read ────────────────────────────────────────────────────────────────

    def get(self, path):
        if path != "/api/phone/status":
            raise PhoneAPIError(404, "unknown_phone_endpoint", "Unknown phone endpoint.")
        return self.wire(self.service.status())

    def wire(self, status):
        config = status["config"]
        return {
            "schema_version": 1,
            "ok": True,
            "enabled": bool(config["enabled"]),
            "readiness": dict(status["readiness"]),
            "endpoint": config["endpoint"],
            "paired": bool(config["endpoint"] and config["fingerprint"]),
            # Unconditionally false in the service. The UI reads this as
            # "Not qualified for a take" and computes no optimistic substitute.
            "hardware_verified": status["hardware_verified"],
            "calibration_points": len(config["calibration"]),
            "calibration": list(config["calibration"]),
            "zoom_mapping": "estimated_between_operator_measured_points",
            "optical_framing_verified": False,
            "fingerprint": config["fingerprint"],
            "observed": status["observed"],
            "connection": status["connection"],
            "last_result": status["last_result"],
            "uncertain": status["uncertain"],
            "owner": status["owner"],
            "color": dict(config["color"], baked_pixels_verified=False),
            # The route is loopback-only, exactly like the robot token.
            "token": status["token"],
        }

    # ── write ───────────────────────────────────────────────────────────────

    def post(self, path, body, token=None):
        if path not in BODY_LIMITS:
            raise PhoneAPIError(404, "unknown_phone_endpoint", "Unknown phone endpoint.")
        action = path.rsplit("/", 1)[-1]
        try:
            result = self.service.post(action, body, token)
        except PermissionError as error:
            raise PhoneAPIError(403, "phone_authority_required", str(error)) from error
        except CameraError as error:
            # The client's own refusals are specific and well written. Surface
            # them verbatim rather than restating them vaguely.
            raise PhoneAPIError(409, "phone_refused", str(error)) from error
        except ValueError as error:
            raise PhoneAPIError(400, "phone_request_invalid", str(error)) from error
        except OSError as error:
            raise PhoneAPIError(503, "phone_unreachable", str(error)) from error
        payload = self.wire(result) if isinstance(result, dict) and "config" in result else dict(result)
        payload.setdefault("schema_version", 1)
        payload.setdefault("ok", True)
        payload["code"] = f"phone_{action.replace('-', '_')}"
        return payload
