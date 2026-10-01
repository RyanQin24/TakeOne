"""Frame analysts: what the pixels can answer, nothing more.

`GeminiFrameAnalyst` below is **not instantiated anywhere**: `review/verdict.py`
always falls through to `LocalFrameAnalyst`, so every verdict in the product
today carries `model = "local-pixel-statistics"` and no vision model has seen a
frame. It is kept rather than deleted because `CLAUDE.md` names this module as
one of exactly three places where Google-facing wire shapes are allowed to live;
removing it would delete a designated boundary. A reader who assumes vision
review uses a vision model is reading the wrong class.

General vision models score barely above chance on cinematography attributes
(shot size, lens, movement) — and TAKE ONE *commanded* those, so the compiler
already holds that ground truth. Analysts here answer only pixel questions: is
something sharp, exposed and steady; is a subject visibly in frame.

Two implementations behind one `analyze(...)` call:

- LocalFrameAnalyst — deterministic pixel statistics from small grayscale
  keyframes, pure Python. Always available wherever ffmpeg is (the recorder
  already requires it). Cannot see subjects; says so.
- GeminiFrameAnalyst — JPEG keyframes to a vision model for the subject
  questions. Never run against the live API from this machine; the wire shape
  lives in one method, transport injectable.
"""

import base64
import http.client
import json
import socket

from . import keyframes

PROMPT_VERSION = 1
GEMINI_HOST = "generativelanguage.googleapis.com"
MAX_RESPONSE_BYTES = 256 * 1_024

VISION_PROMPT = (
    "You are judging raw footage frames from a robot filming rig. Answer only what the "
    "pixels show, as JSON with keys: in_frame (0..1, is a human subject visibly framed), "
    "left_frame (true if the subject exits during these frames), focus (0..1), "
    "exposure (0..1), reason (one sentence, under 200 characters). Do not guess shot "
    "names, lens or camera movement; those are already known from the plan."
)


class AnalysisUnavailable(RuntimeError):
    pass


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


class LocalFrameAnalyst:
    """Sharpness, exposure and inter-frame change from grayscale keyframes."""

    model = "local-pixel-statistics"

    def analyze(self, media_path, media_sha256, timestamps):
        frames = [
            keyframes.read_pgm(path)
            for path in keyframes.extract(media_path, media_sha256, timestamps, kind="pgm")
        ]
        focus = min(self._sharpness(*frame) for frame in frames)
        exposure = min(self._exposure(*frame) for frame in frames)
        difference = self._difference(frames)
        signals = {
            "focus": round(focus, 4),
            "exposure": round(exposure, 4),
            "frame_difference": round(difference, 4),
            "subject": "not_assessed_locally",
        }
        reason = (
            f"Pixel statistics over {len(frames)} frames: focus {focus:.2f}, "
            f"exposure {exposure:.2f}, inter-frame change {difference:.2f}."
        )
        return {"signals": signals, "reason": reason, "model": self.model}

    @staticmethod
    def _sharpness(width, height, pixels):
        """Mean absolute Laplacian, scaled. Blur suppresses it reliably at this size."""
        total = 0
        count = 0
        for y in range(1, height - 1):
            row = y * width
            for x in range(1, width - 1):
                index = row + x
                laplacian = (
                    4 * pixels[index]
                    - pixels[index - 1]
                    - pixels[index + 1]
                    - pixels[index - width]
                    - pixels[index + width]
                )
                total += laplacian if laplacian >= 0 else -laplacian
                count += 1
        return _clamp((total / max(count, 1)) / 12.0)

    @staticmethod
    def _exposure(width, height, pixels):
        mean = sum(pixels) / max(len(pixels), 1)
        return _clamp(1.0 - abs(mean - 118.0) / 118.0)

    @staticmethod
    def _difference(frames):
        if len(frames) < 2:
            return 0.0
        deltas = []
        for (w, h, a), (_, _, b) in zip(frames, frames[1:]):
            step = max(1, (w * h) // 2_000)
            sampled = range(0, w * h, step)
            deltas.append(sum(abs(a[i] - b[i]) for i in sampled) / (255 * len(sampled)))
        return _clamp(sum(deltas) / len(deltas) * 4)


class GeminiFrameAnalyst:
    """Subject-level questions over JPEG keyframes. Unverified against the live API."""

    def __init__(self, model, api_key, *, connection_factory=http.client.HTTPSConnection):
        if not isinstance(model, str) or not model.startswith("gemini-"):
            raise ValueError("Frame analysis model must name a Gemini model")
        self.model = model
        self._api_key = api_key
        self._connect = connection_factory

    def analyze(self, media_path, media_sha256, timestamps):
        if not self._api_key:
            raise AnalysisUnavailable("No vision API key configured")
        frames = keyframes.extract(media_path, media_sha256, timestamps, kind="jpeg")
        parts = [{"text": VISION_PROMPT}]
        for path in frames:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(path.read_bytes()).decode(),
                    }
                }
            )
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        connection = self._connect(GEMINI_HOST, timeout=20)
        try:
            connection.request(
                "POST",
                f"/v1beta/models/{self.model}:generateContent",
                body=json.dumps(body),
                headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            )
            response = connection.getresponse()
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, socket.timeout, http.client.HTTPException) as error:
            raise AnalysisUnavailable(f"Vision service unreachable: {error}") from error
        finally:
            connection.close()
        if response.status != 200 or len(payload) > MAX_RESPONSE_BYTES:
            raise AnalysisUnavailable(f"Vision service answered HTTP {response.status}")
        try:
            answer = json.loads(payload)["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(answer)
            signals = {
                "in_frame": _clamp(parsed["in_frame"]),
                "left_frame": bool(parsed.get("left_frame", False)),
                "focus": _clamp(parsed["focus"]),
                "exposure": _clamp(parsed["exposure"]),
            }
            reason = str(parsed.get("reason", ""))[:200]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise AnalysisUnavailable("Vision response did not match the asked schema") from error
        return {"signals": signals, "reason": reason, "model": self.model}
