"""A blurred take ranks below its sharp original; verdicts cache and degrade honestly."""

import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from takeone.review import keyframes, verdict
from takeone.review.vlm import AnalysisUnavailable

FFMPEG = shutil.which("ffmpeg")


def synthesize(path, *, blur=False, seconds=1.0):
    filters = "scale=320:180" + (",boxblur=10" if blur else "")
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=duration={seconds}:rate=24",
            "-vf",
            filters,
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        timeout=60,
    )


def take_for(path, take_id="a" * 8, plan_id=None):
    import hashlib

    data = Path(path).read_bytes()
    return {
        "take_id": take_id,
        "state": "ready",
        "plan_id": plan_id,
        "media": {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "duration_ms": 1000,
            "requested_timeline_ms": 1000,
            "streams": [{"codec_type": "video", "width": 320, "height": 180}],
        },
    }


@unittest.skipUnless(FFMPEG, "keyframe extraction requires ffmpeg")
class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self._old = (keyframes.DIRECTORY, verdict.DIRECTORY)
        keyframes.DIRECTORY = root / "keyframes"
        verdict.DIRECTORY = root / "verdicts"
        self.addCleanup(self._restore)
        self.sharp = root / "sharp.mp4"
        self.blurred = root / "blurred.mp4"
        synthesize(self.sharp)
        synthesize(self.blurred, blur=True)

    def _restore(self):
        keyframes.DIRECTORY, verdict.DIRECTORY = self._old

    def test_blurred_ranks_below_sharp(self):
        sharp = verdict.review_take(take_for(self.sharp), self.sharp)
        blurred = verdict.review_take(take_for(self.blurred, "b" * 8), self.blurred)
        self.assertLess(blurred["score"], sharp["score"])
        self.assertLess(blurred["signals"]["focus"], sharp["signals"]["focus"])
        self.assertEqual(sharp["model"], "local-pixel-statistics")
        self.assertLessEqual(len(sharp["reason"]), 240)

    def test_verdict_is_cached_and_deterministic(self):
        take = take_for(self.sharp)
        first = verdict.review_take(take, self.sharp, clock=lambda: 111)
        again = verdict.review_take(take, self.sharp, clock=lambda: 999)
        self.assertEqual(first, again)  # created_ns replays from the cache

    def test_failed_analyst_degrades_to_local_then_probe(self):
        class Broken:
            model = "gemini-test"

            def analyze(self, *arguments):
                raise AnalysisUnavailable("offline")

        take = take_for(self.sharp)
        result = verdict.review_take(take, self.sharp, analyst=Broken())
        self.assertEqual(result["model"], "local-pixel-statistics")
        # No frames at all: the probe floor still answers from verified metadata.
        missing = take_for(self.sharp, "c" * 8)
        missing["media"] = {**missing["media"], "sha256": "0" * 64}
        result = verdict.review_take(missing, Path(self.folder.name) / "missing.mp4")
        self.assertEqual(result["model"], "probe-only")
        self.assertEqual(result["signals"]["source"], "probe_only")

    def test_unready_take_is_refused(self):
        take = take_for(self.sharp)
        take["state"] = "failed"
        with self.assertRaises(ValueError):
            verdict.review_take(take, self.sharp)

    def test_keyframes_cache_skips_ffmpeg_on_replay(self):
        take = take_for(self.sharp)
        stamps = keyframes.default_timestamps(1.0)
        first = keyframes.extract(self.sharp, take["media"]["sha256"], stamps, kind="pgm")
        calls = []
        second = keyframes.extract(
            self.sharp,
            take["media"]["sha256"],
            stamps,
            kind="pgm",
            run=lambda *a, **k: calls.append(a),
        )
        self.assertEqual(first, second)
        self.assertEqual(calls, [])

    def test_default_timestamps_stay_inside_the_take(self):
        stamps = keyframes.default_timestamps(10.0)
        self.assertEqual(stamps, [2.0, 4.0, 6.0, 8.0])
        with self.assertRaises(ValueError):
            keyframes.default_timestamps(0)


@unittest.skipUnless(FFMPEG, "the offline recorder requires ffmpeg")
class BridgeReviewTests(unittest.TestCase):
    """start → stop → ready → review, with the verdict persisted beside the take."""

    def test_reviewed_take_persists_its_verdict_and_plan(self):
        from takeone.director.repository import SessionRepository
        from takeone.director.service import DirectorService
        from takeone.recording.contracts import ZoomRamp
        from takeone.recording.voice_bridge import RecordingVoiceBridge
        from takeone.voice.service import VoiceService

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self._old = (keyframes.DIRECTORY, verdict.DIRECTORY)
        keyframes.DIRECTORY = root / "keyframes"
        verdict.DIRECTORY = root / "verdicts"
        self.addCleanup(lambda: setattr(keyframes, "DIRECTORY", self._old[0]))
        self.addCleanup(lambda: setattr(verdict, "DIRECTORY", self._old[1]))

        director = DirectorService(SessionRepository(root / "sessions.sqlite3"))
        voice = VoiceService(director)
        self.addCleanup(voice.close)
        bridge = RecordingVoiceBridge(voice, root / "recording")
        self.addCleanup(bridge.close)
        session = voice.create("offline", None)
        token = session["ownership_token"]

        def envelope():
            from takeone.voice.contracts import VoiceScope

            snapshot = voice.snapshot(token)["snapshot"]
            return (
                session["voice_session_id"],
                VoiceScope(**snapshot["scope"]),
                snapshot["generation"],
                voice.clock() + 10_000_000_000,
            )

        plan_id = "d" * 64
        started = bridge.mutate(
            "start",
            token,
            envelope(),
            "req-start",
            zoom=ZoomRamp(1.0, 1.0, 500),
            scenario="normal",
            plan_id=plan_id,
        )
        take_id = started["take"]["take_id"]
        self.assertEqual(started["take"]["plan_id"], plan_id)
        deadline = time.time() + 30
        while time.time() < deadline:
            if bridge.recording.get(take_id)["state"] == "recording":
                break
            time.sleep(0.05)
        bridge.mutate("stop", token, envelope(), "req-stop", take_id=take_id)
        deadline = time.time() + 30
        while time.time() < deadline:
            take = bridge.recording.get(take_id)
            if take["state"] in ("ready", "failed"):
                break
            time.sleep(0.1)
        self.assertEqual(take["state"], "ready", take.get("error"))

        outcome = bridge.review(token, envelope(), take_id)
        self.assertEqual(outcome["code"], "take_reviewed")
        self.assertEqual(outcome["verdict"]["plan_id"], plan_id)
        self.assertEqual(len(outcome["verdicts"]), 1)
        self.assertEqual(outcome["verdicts"][0]["take_id"], take_id)
        # Replay: same verdict, still one row.
        again = bridge.review(token, envelope(), take_id)
        self.assertEqual(len(again["verdicts"]), 1)


if __name__ == "__main__":
    unittest.main()
