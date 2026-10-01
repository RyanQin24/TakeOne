"""Offline integration rehearsal with synthetic effects and explicit audio restoration.

This exercises existing APIs and the direct local media preparation recipe.
It does not submit generation or attest preservation of real footage.
"""

import copy
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from takeone.editor.api import EditorAPI
from takeone.editor.errors import EditorError
from takeone.editor.jobs import JobPool
from takeone.editor.repository import ProjectRepository
from takeone.editor.service import EditorService
from takeone.editor.state import RenderSettings

from tests.editor.test_render_qualification import (
    audio_samples,
    frame_count,
    mean_absolute_error,
    operation,
    rgb_frame,
    sha256,
    tone_amplitude,
)
from tests.editor.test_vfx_planning import SimulatedProvider


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg and FFprobe")
class VFXHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="takeone-vfx-handoff-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.sources = []
        for name, color, tone in (("first", "red", 440), ("second", "blue", 660)):
            path = self.media / f"{name}.mp4"
            self.ffmpeg(
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=160x90:r=30:d=3",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={tone}:sample_rate=48000:duration=3",
                "-af",
                "volume='if(lt(t,0.5),0,1)':eval=frame" if name == "first" else "anull",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(path),
            )
            self.sources.append(path)
        self.source_hashes = [sha256(path) for path in self.sources]
        self.jobs = JobPool(max_workers=1)
        self.addCleanup(self.jobs.close)
        self.provider = SimulatedProvider()
        self.provider.release.set()
        self.reopen()
        self.api.post(
            "/api/editor/projects",
            {
                "project_id": "demo",
                "title": "Offline effects handoff",
                "render_settings": RenderSettings(master_width=160, master_height=90, fps_num=30).wire(),
            },
        )
        self.source_ids = [
            self.api.import_media("demo", {"path": str(path), "build_proxy": False})["media_id"]
            for path in self.sources
        ]

    def ffmpeg(self, *args):
        return subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", *args],
            check=True,
            capture_output=True,
            timeout=30,
        )

    def reopen(self):
        self.service = EditorService(ProjectRepository(self.root / "projects.sqlite3"))
        self.api = EditorAPI(
            self.service, self.root / "workspace", [self.media], jobs=self.jobs, vfx_provider=self.provider
        )

    def submit(self, op_type, target, **params):
        return self.api.post("/api/editor/projects/demo/operations", operation(op_type, target, **params))

    def test_proposal_preparation_intake_paced_export_reload_and_undo(self):
        # Broken audio mapping, source offsets, no-effect placement, journaling,
        # retry identity or clip pacing must fail the measured exported result.
        request = {
            "request_id": str(uuid.uuid4()),
            "expected_version": self.service.state("demo").version,
            "script": "One brief sparkle, then a longer unmodified shot.",
            "sources": [
                {
                    "media_id": media_id,
                    "source_sha256": digest,
                    "source_start_s": start,
                    "source_end_s": end,
                    "observations": [
                        {"source": "synthetic fixture", "text": "Uniform color with no people."}
                    ],
                }
                for media_id, digest, start, end in zip(
                    self.source_ids, self.source_hashes, (0.5, 0), (2.5, 3)
                )
            ],
        }
        before = self.service.state("demo").wire()
        self.api.post("/api/editor/projects/demo/vfx/plan", request)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            proposal = self.api.get(f"/api/editor/projects/demo/vfx/plans/{request['request_id']}")
            if proposal["status"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        self.assertEqual(proposal["status"], "proposal")
        self.assertEqual([item["decision"] for item in proposal["proposals"]], ["augment", "none"])
        self.assertEqual(proposal["provenance"]["source"], "simulated_provider")
        self.assertEqual(self.api.post("/api/editor/projects/demo/vfx/plan", request), proposal)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(self.service.state("demo").wire(), before)

        # Stand-in output intentionally has different sound. No cloud/model call.
        raw = self.media / "simulated-effect.mp4"
        self.ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=160x90:r=30:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000:duration=2",
            "-vf",
            "drawbox=x=10:y=10:w=40:h=40:color=white:t=fill:enable='lt(t,0.5)'",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(raw),
        )
        raw_hash = sha256(raw)
        prepared = self.media / "effect-original-audio.mp4"
        self.ffmpeg(
            "-i",
            str(raw),
            "-ss",
            "0.5",
            "-i",
            str(self.sources[0]),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            "2",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(prepared),
        )
        body = {
            "path": str(prepared),
            "source_media_id": self.source_ids[0],
            "source_sha256": self.source_hashes[0],
            "source_start_s": 0.5,
            "source_end_s": 2.5,
            "output_source_space": "rec709",
            "provider": "offline-fixture",
            "model": "no-generation-performed",
            "model_version": "not-applicable",
            "job_id": "synthetic-handoff",
            "prompt": proposal["proposals"][0]["prompt"],
            "settings": {
                "proposal_request_id": request["request_id"],
                "local_audio_transform": {
                    "input_candidate_sha256": raw_hash,
                    "original_source_sha256": self.source_hashes[0],
                    "original_source_start_s": 0.5,
                    "duration_s": 2.0,
                    "discard_candidate_audio": True,
                    "video_codec": "copy",
                    "audio_codec": "aac",
                },
            },
            "cost": {"amount": None, "unit": "credits", "status": "unknown"},
            "rights_evidence": "Local synthetic colors and tones only.",
            "review": {
                "reviewer": "offline-fixture",
                "decision": "approved",
                "notes": "Synthetic rehearsal only; no real-footage approval.",
                "preserved": dict.fromkeys(
                    ("people", "action", "camera_motion", "geometry", "text_logos"), True
                ),
                "audio": "reviewed",
            },
        }
        imported = self.api.post("/api/editor/projects/demo/vfx/derivatives", body)
        self.assertFalse(imported["placed"])
        self.assertEqual(len(self.service.state("demo").timeline.tracks), 0)
        history_length = len(self.service.history("demo"))
        self.reopen()
        retry = self.api.post("/api/editor/projects/demo/vfx/derivatives", copy.deepcopy(body))
        self.assertTrue(retry["reused"])
        self.assertEqual(len(self.service.history("demo")), history_length)
        self.assertEqual(retry["lineage"]["settings"], body["settings"])
        self.submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        self.submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="effect",
            media_id=imported["media_id"],
            timeline_start_s=0,
            source_start_s=0,
            source_end_s=2,
        )
        self.submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="plain",
            media_id=self.source_ids[1],
            timeline_start_s=2,
            source_start_s=0,
            source_end_s=3,
        )
        final_state = self.service.state("demo").wire()
        self.reopen()
        self.assertEqual(self.service.state("demo").wire(), final_state)
        self.assertEqual(self.service.replay("demo")[0].wire(), final_state)
        output = Path(
            self.api.post("/api/editor/projects/demo/render", {"target": "master", "wait": True})["artifact"]
        )
        self.assertEqual(frame_count(output), 150)
        self.assertGreater(mean_absolute_error(rgb_frame(output, 59 / 30), rgb_frame(output, 2)), 100)
        self.assertLess(mean_absolute_error(rgb_frame(prepared, 0.25), rgb_frame(output, 0.25)), 3)
        self.assertGreater(mean_absolute_error(rgb_frame(output, 0.25), rgb_frame(output, 0.75)), 5)
        first_audio, second_audio = audio_samples(output, 0.5, 0.5), audio_samples(output, 2.5, 0.5)
        self.assertGreater(tone_amplitude(first_audio, 440), 0.02)
        # The first source is silent before 0.5 s. A wrong zero seek keeps
        # the right frequency later but loses this early selected-span sound.
        self.assertGreater(tone_amplitude(audio_samples(output, 0.1, 0.2), 440), 0.02)
        self.assertLess(tone_amplitude(first_audio, 880), 0.001)
        self.assertGreater(tone_amplitude(second_audio, 660), 0.02)
        self.assertTrue(
            self.api.post("/api/editor/projects/demo/render", {"target": "master", "wait": True})["cached"]
        )
        self.api.post("/api/editor/projects/demo/undo", {"steps": 1})
        undo_output = Path(
            self.api.post("/api/editor/projects/demo/render", {"target": "master", "wait": True})["artifact"]
        )
        self.assertEqual(frame_count(undo_output), 60)
        self.assertEqual([sha256(path) for path in self.sources], self.source_hashes)
        self.assertEqual(sha256(raw), raw_hash)
        self.assertEqual(sha256(prepared), imported["lineage"]["output_sha256"])
        self.assertTrue(
            self.api.post("/api/editor/projects/demo/vfx/derivatives", copy.deepcopy(body))["reused"]
        )
        alternate = self.media / "alternate-effect.mp4"
        self.ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=160x90:r=30:d=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(alternate),
        )
        stale_body = copy.deepcopy(body)
        stale_body["path"] = str(alternate)
        with self.assertRaisesRegex(EditorError, "stale"):
            self.api.post("/api/editor/projects/demo/vfx/derivatives", stale_body)


if __name__ == "__main__":
    unittest.main()
