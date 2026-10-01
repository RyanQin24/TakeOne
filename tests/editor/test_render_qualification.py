"""Qualification of the existing editor assembly path against real FFmpeg media.

The fixtures are deliberately generated in the test workspace.  They use a
BT.601-tagged red take and a BT.709-tagged blue take, each with its own tone,
so decoded pixels and audio can be measured rather than inferred from a render
plan.  This is a renderer qualification, not a replacement renderer.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from takeone.editor.api import EditorAPI
from takeone.editor.errors import OperationError
from takeone.editor.jobs import JobPool
from takeone.editor.repository import ProjectRepository
from takeone.editor.service import EditorService
from takeone.editor.state import RenderSettings
from takeone.editor.timing.curve import SpeedCurve, SpeedPoint

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=True, capture_output=True, text=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stream_document(path: Path) -> dict:
    return json.loads(
        run(
            FFPROBE,
            "-v",
            "error",
            "-show_streams",
            "-show_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=color_space,color_transfer,color_primaries,avg_frame_rate,r_frame_rate:frame=best_effort_timestamp_time",
            "-of",
            "json",
            str(path),
        ).stdout
    )


def frame_count(path: Path) -> int:
    return int(
        run(
            FFPROBE,
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ).stdout.strip()
    )


def dimensions(path: Path) -> tuple[int, int]:
    width, height = (
        run(
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        )
        .stdout.strip()
        .split(",")
    )
    return int(width), int(height)


def rgb_frame(path: Path, at_s: float) -> bytes:
    width, height = dimensions(path)
    raw = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-i",
            str(path),
            "-ss",
            f"{at_s:.6f}",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    expected = width * height * 3
    if len(raw) != expected:
        raise AssertionError(f"wanted {expected} RGB bytes, got {len(raw)} from {path}")
    return raw


def rgb_frames(path: Path) -> list[bytes]:
    width, height = dimensions(path)
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path), "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
        check=True,
        capture_output=True,
    ).stdout
    frame_bytes = width * height * 3
    if len(raw) % frame_bytes:
        raise AssertionError(f"incomplete RGB frame from {path}")
    return [raw[offset : offset + frame_bytes] for offset in range(0, len(raw), frame_bytes)]


def mean_absolute_error(first: bytes, second: bytes) -> float:
    if len(first) != len(second):
        raise AssertionError("RGB frames have different dimensions")
    return sum(abs(a - b) for a, b in zip(first, second)) / len(first)


def audio_samples(path: Path, start_s: float, duration_s: float) -> list[float]:
    import array

    raw = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-ss",
            f"{start_s:.6f}",
            "-t",
            f"{duration_s:.6f}",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    values = array.array("f")
    values.frombytes(raw)
    return list(values)


def tone_amplitude(samples: list[float], frequency: float, sample_rate: int = 48000) -> float:
    """A simple lock-in measurement, robust enough for the AAC qualification tones."""
    if not samples:
        return 0.0
    cosine = sum(
        value * math.cos(2 * math.pi * frequency * i / sample_rate) for i, value in enumerate(samples)
    )
    sine = sum(value * math.sin(2 * math.pi * frequency * i / sample_rate) for i, value in enumerate(samples))
    return 2.0 * math.hypot(cosine, sine) / len(samples)


def operation(op_type: str, target: dict, **parameters: object) -> dict:
    return {
        "operation": {
            "operation_id": str(uuid.uuid4()),
            "type": op_type,
            "target": target,
            "parameters": parameters,
        }
    }


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg and FFprobe are required for renderer qualification")
class RenderQualification(unittest.TestCase):
    def setUp(self) -> None:
        retained = os.environ.get("TAKEONE_QUALIFICATION_OUTPUT")
        self.temp = None
        if retained:
            self.root = Path(retained).resolve() / self._testMethodName
            self.root.mkdir(parents=True, exist_ok=False)
        else:
            self.temp = tempfile.TemporaryDirectory(prefix="takeone-render-qualification-")
            self.root = Path(self.temp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.red = self.media / "red-601.mp4"
        self.blue = self.media / "blue-709.mp4"
        self.bed = self.media / "bed-660.mp4"
        self.vfr = self.media / "fractional-vfr.mp4"
        self.landmark = self.media / "landmark-av.mp4"
        self._make_fixtures()
        self.original_hashes = {
            path: sha256(path) for path in (self.red, self.blue, self.bed, self.vfr, self.landmark)
        }
        self.repository_path = self.root / "projects.sqlite3"
        self.jobs = JobPool(max_workers=1)
        self.service = EditorService(ProjectRepository(self.repository_path))
        self.api = EditorAPI(self.service, self.root / "workspace", [self.media], jobs=self.jobs)
        self.api.post(
            "/api/editor/projects",
            {
                "project_id": "qualification",
                "title": "Renderer qualification",
                "render_settings": RenderSettings(
                    master_width=320,
                    master_height=180,
                    preview_long_edge=240,
                    fps_num=30,
                    fps_den=1,
                    master_crf=18,
                    preview_crf=18,
                ).wire(),
            },
        )

    def tearDown(self) -> None:
        self.jobs.close()
        if self.temp is not None:
            self.temp.cleanup()

    def _make_fixtures(self) -> None:
        common = ["-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
        run(
            FFMPEG,
            *common,
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=30:d=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt470bg",
            "-color_primaries",
            "bt470bg",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(self.red),
        )
        run(
            FFMPEG,
            *common,
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=30:d=7",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000:duration=7",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(self.blue),
        )
        run(
            FFMPEG,
            *common,
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:r=30:d=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=48000:duration=6",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(self.bed),
        )
        run(
            FFMPEG,
            *common,
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=30:d=1.3",
            "-vf",
            "select='not(eq(mod(n,5),1)+eq(mod(n,5),4))'",
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(self.vfr),
        )
        run(
            FFMPEG,
            *common,
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x180:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            r"aevalsrc='if(lt(t,1)\,0.2*sin(2*PI*440*t)\,0.2*sin(2*PI*880*t))':s=48000:d=2",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(self.landmark),
        )

    def _import(self, path: Path, build_proxy: bool = False) -> str:
        return self.api.post(
            "/api/editor/projects/qualification/media",
            {"path": str(path), "build_proxy": build_proxy, "place": False, "source_space": "rec709"},
        )["media_id"]

    def _submit(self, op_type: str, target: dict, **parameters: object) -> None:
        self.api.post(
            "/api/editor/projects/qualification/operations", operation(op_type, target, **parameters)
        )

    def _render_job(self, target: str) -> Path:
        response = self.api.post(
            "/api/editor/projects/qualification/render", {"target": target, "wait": False}
        )
        self.assertFalse(response["cached"])
        job_id = response["job"]["job_id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = self.jobs.get(job_id)
            if job["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(0.025)
        else:
            self.fail(f"render job did not finish: {job_id}")
        self.assertEqual(job["status"], "COMPLETED", job.get("error"))
        return Path(job["artifact"])

    def _assemble_four_cut_timeline(self) -> tuple[str, str, str]:
        red_id, blue_id, bed_id = self._import(self.red), self._import(self.blue), self._import(self.bed)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        clips = (
            ("c1", red_id, 0.0, 0.50, 2.00),
            ("c2", blue_id, 1.5, 0.333333, 2.833333),
            ("c3", red_id, 4.0, 2.50, 4.50),
            ("c4", blue_id, 6.0, 3.00, 6.00),
        )
        for clip_id, media_id, timeline_start_s, source_start_s, source_end_s in clips:
            self._submit(
                "ADD_CLIP",
                {"kind": "track", "track_id": "V1"},
                clip_id=clip_id,
                media_id=media_id,
                timeline_start_s=timeline_start_s,
                source_start_s=source_start_s,
                source_end_s=source_end_s,
            )
        return red_id, blue_id, bed_id

    def test_music_span_cannot_use_video_duration_as_audio_duration(self) -> None:
        short_audio = self.media / "long-video-short-audio.mp4"
        run(
            FFMPEG,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=30:d=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(short_audio),
        )
        original_hash = sha256(short_audio)
        media_id = self._import(short_audio)
        before = self.service.state("qualification").wire()
        with self.assertRaisesRegex(OperationError, "source range"):
            self._submit(
                "ADD_MUSIC",
                {"kind": "project"},
                event_id="past-audio-end",
                asset_id=media_id,
                timeline_start_s=0.0,
                source_start_s=1.0,
                duration_s=2.0,
            )
        self.assertEqual(self.service.state("qualification").wire(), before)
        self.assertEqual(sha256(short_audio), original_hash)
        self.assertAlmostEqual(before["media"][media_id]["probe"]["audio_duration_s"], 2.0)
        self._submit(
            "ADD_MUSIC",
            {"kind": "project"},
            event_id="fits-audio",
            asset_id=media_id,
            timeline_start_s=0.0,
            source_start_s=1.5,
            duration_s=0.5,
        )
        reopened = EditorService(ProjectRepository(self.repository_path))
        self.assertEqual(reopened.state("qualification").wire(), self.service.state("qualification").wire())
        self.assertEqual(reopened.replay("qualification")[0].wire(), reopened.state("qualification").wire())

    def test_music_span_cannot_start_before_a_delayed_audio_stream(self) -> None:
        delayed_audio = self.media / "delayed-audio.mp4"
        run(
            FFMPEG,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=30:d=4",
            "-itsoffset",
            "1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(delayed_audio),
        )
        media_id = self._import(delayed_audio)
        with self.assertRaisesRegex(OperationError, "source range"):
            self._submit(
                "ADD_MUSIC",
                {"kind": "project"},
                event_id="before-audio-start",
                asset_id=media_id,
                timeline_start_s=0.0,
                source_start_s=0.5,
                duration_s=0.25,
            )

    def test_job_path_qualifies_cuts_colour_cache_reload_undo_and_vfr_limit(self) -> None:
        red_id, blue_id, _ = self._assemble_four_cut_timeline()
        sources = stream_document(self.red)["streams"][0], stream_document(self.blue)["streams"][0]
        self.assertEqual(sources[0]["color_space"], "bt470bg")
        self.assertEqual(sources[1]["color_space"], "bt709")

        master = self._render_job("master")
        self.assertEqual(frame_count(master), 270)
        self.assertEqual(dimensions(master), (320, 180))
        self.assertEqual(stream_document(master)["streams"][0]["color_space"], "bt709")

        # The samples are decoded through FFmpeg from their tagged source, not expected RGB constants.
        source_spans = (
            (self.red, 0.50, 0.0),
            (self.blue, 0.333333, 1.5),
            (self.red, 2.50, 4.0),
            (self.blue, 3.00, 6.0),
        )
        for source, source_start, output_start in source_spans:
            self.assertLess(
                mean_absolute_error(
                    rgb_frame(source, source_start + 0.5), rgb_frame(master, output_start + 0.5)
                ),
                3.0,
            )

        decoded = rgb_frames(master)
        for before, after in ((44, 45), (119, 120), (179, 180)):
            left = decoded[before]
            right = decoded[after]
            self.assertGreater(mean_absolute_error(left, right), 100.0)

        cached = self.api.post(
            "/api/editor/projects/qualification/render", {"target": "master", "wait": False}
        )
        self.assertTrue(cached["cached"])
        preview = self._render_job("preview")
        self.assertNotEqual(preview, master)
        self.assertEqual(dimensions(preview), (240, 136))

        self._submit("SET_PHASE", {"kind": "project"}, phase="audio")
        expected = self.service.state("qualification").wire()
        self.service = EditorService(ProjectRepository(self.repository_path))
        self.api.service = self.service
        replayed, _, _ = self.service.replay("qualification")
        self.assertEqual(replayed.wire(), expected)
        self.api.post("/api/editor/projects/qualification/undo", {"steps": 1})
        self.service = EditorService(ProjectRepository(self.repository_path))
        self.api.service = self.service
        after_undo, _, _ = self.service.replay("qualification")
        self.assertEqual(self.service.state("qualification").wire(), after_undo.wire())

        vfr = stream_document(self.vfr)
        timestamps = [float(item["best_effort_timestamp_time"]) for item in vfr["frames"]]
        deltas = {round(b - a, 6) for a, b in zip(timestamps, timestamps[1:])}
        self.assertGreater(len(deltas), 1, "fixture must retain variable frame timestamps")
        self.assertEqual(stream_document(master)["streams"][0]["avg_frame_rate"], "30/1")
        self.assertEqual({path: sha256(path) for path in self.original_hashes}, self.original_hashes)

    def test_dissolve_preserves_embedded_audio_and_mixes_timed_faded_bed_without_picture_change(self) -> None:
        _, _, bed_id = self._assemble_four_cut_timeline()
        self._submit(
            "APPLY_TRANSITION",
            {"kind": "track", "track_id": "V1"},
            transition_id="dissolve1",
            effect_id="crossfade",
            effect_version=1,
            from_clip_id="c1",
            to_clip_id="c2",
            duration_s=0.5,
        )
        without_bed = self._render_job("master")
        self._submit(
            "ADD_MUSIC",
            {"kind": "project"},
            event_id="bed1",
            asset_id=bed_id,
            timeline_start_s=3.0,
            duration_s=1.5,
            source_start_s=0.5,
            gain_db=-6.0,
            fade_in_s=0.25,
            fade_out_s=0.25,
        )
        mixed = self._render_job("master")
        self.assertEqual(frame_count(mixed), frame_count(without_bed))
        for at_s in (0.75, 2.0, 3.75, 6.5):
            self.assertLess(mean_absolute_error(rgb_frame(without_bed, at_s), rgb_frame(mixed, at_s)), 0.1)

        # 440/880 Hz are original clip audio; 660 Hz is the timed music bed.
        self.assertGreater(tone_amplitude(audio_samples(mixed, 0.5, 0.75), 440), 0.02)
        self.assertGreater(tone_amplitude(audio_samples(mixed, 2.0, 0.75), 880), 0.02)
        # The picture dissolves from red/440 to blue/880 from 1.0 through 1.5s.
        # Measure both streams at matching timestamps: a late dissolve sample must have
        # shifted toward the incoming blue/880 take, rather than waiting for a hard audio cut.
        early_picture = rgb_frame(mixed, 1.10)
        late_picture = rgb_frame(mixed, 1.40)
        self.assertGreater(sum(early_picture[0::3]), sum(early_picture[2::3]))
        self.assertGreater(sum(late_picture[2::3]), sum(late_picture[0::3]))
        early_440 = tone_amplitude(audio_samples(mixed, 1.05, 0.10), 440)
        early_880 = tone_amplitude(audio_samples(mixed, 1.05, 0.10), 880)
        late_440 = tone_amplitude(audio_samples(mixed, 1.35, 0.10), 440)
        late_880 = tone_amplitude(audio_samples(mixed, 1.35, 0.10), 880)
        self.assertGreater(early_440, early_880)
        self.assertGreater(late_880, late_440)
        self.assertLess(tone_amplitude(audio_samples(mixed, 2.0, 0.5), 660), 0.001)
        self.assertGreater(tone_amplitude(audio_samples(mixed, 3.55, 0.5), 660), 0.02)
        self.assertLess(tone_amplitude(audio_samples(mixed, 5.0, 0.5), 660), 0.001)
        fade = [tone_amplitude(audio_samples(mixed, start, 0.07), 660) for start in (3.02, 3.10, 3.18)]
        self.assertLessEqual(fade[0], fade[1] + 0.003)
        self.assertLessEqual(fade[1], fade[2] + 0.003)
        fade_out = [tone_amplitude(audio_samples(mixed, start, 0.05), 660) for start in (4.27, 4.35, 4.43)]
        self.assertGreaterEqual(fade_out[0] + 0.003, fade_out[1])
        self.assertGreaterEqual(fade_out[1] + 0.003, fade_out[2])
        self.assertEqual({path: sha256(path) for path in self.original_hashes}, self.original_hashes)

    def test_preview_uses_original_audio_for_silent_proxy_and_music_event(self) -> None:
        red_id = self._import(self.red, build_proxy=True)
        bed_id = self._import(self.bed, build_proxy=True)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        self._submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="c1",
            media_id=red_id,
            timeline_start_s=0.0,
            source_start_s=0.5,
            source_end_s=2.5,
        )
        self._submit(
            "ADD_MUSIC",
            {"kind": "project"},
            event_id="bed1",
            asset_id=bed_id,
            timeline_start_s=0.25,
            duration_s=1.0,
            source_start_s=0.5,
            gain_db=-6.0,
        )
        preview = self._render_job("preview")
        self.assertGreater(tone_amplitude(audio_samples(preview, 1.5, 0.3), 440), 0.02)
        self.assertGreater(tone_amplitude(audio_samples(preview, 0.7, 0.3), 660), 0.02)

    def test_nine_audible_clips_render_without_audio_node_input_limit(self) -> None:
        red_id = self._import(self.red)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        for index in range(9):
            self._submit(
                "ADD_CLIP",
                {"kind": "track", "track_id": "V1"},
                clip_id=f"c{index + 1}",
                media_id=red_id,
                timeline_start_s=float(index * 2),
                source_start_s=0.0,
                source_end_s=2.0,
            )
        master = self._render_job("master")
        self.assertEqual(frame_count(master), 540)
        self.assertGreater(tone_amplitude(audio_samples(master, 17.0, 0.5), 440), 0.02)

    def test_piecewise_speed_curve_retimes_audio_landmarks_and_following_cut(self) -> None:
        landmark_id = self._import(self.landmark)
        red_id = self._import(self.red)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        self._submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="c1",
            media_id=landmark_id,
            timeline_start_s=0.0,
            source_start_s=0.0,
            source_end_s=2.0,
        )
        self._submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="c2",
            media_id=red_id,
            timeline_start_s=2.0,
            source_start_s=0.0,
            source_end_s=1.0,
        )
        curve = SpeedCurve((SpeedPoint(0.0, 0.5), SpeedPoint(2.0, 0.5, "hold"), SpeedPoint(3.0, 1.0, "hold")))
        self._submit(
            "APPLY_SPEED_CURVE",
            {"kind": "clip", "clip_id": "c1"},
            curve=curve.wire(),
            interpolation="none",
        )
        master = self._render_job("master")
        self.assertGreater(tone_amplitude(audio_samples(master, 1.05, 0.2), 440), 0.02)
        self.assertGreater(tone_amplitude(audio_samples(master, 2.50, 0.2), 880), 0.02)
        self.assertGreater(tone_amplitude(audio_samples(master, 4.20, 0.2), 440), 0.02)
        early = rgb_frame(master, 1.05)
        late = rgb_frame(master, 2.50)
        cut = rgb_frame(master, 4.20)
        self.assertGreater(sum(early[0::3]), sum(early[1::3]))
        self.assertGreater(sum(late[1::3]), sum(late[0::3]))
        self.assertGreater(mean_absolute_error(late, cut), 100.0)

    def _delayed_audio_fixture(self) -> Path:
        source = self.media / "delayed-clip-audio.mp4"
        run(
            FFMPEG,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=30:d=4",
            "-itsoffset",
            "1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-t",
            "4",
            str(source),
        )
        return source

    def test_measured_audio_bounds_survive_trim_speed_and_following_concat(self) -> None:
        source = self._delayed_audio_fixture()
        source_id, following_id = self._import(source), self._import(self.bed)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        self._submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="delayed",
            media_id=source_id,
            timeline_start_s=0,
            source_start_s=0.5,
            source_end_s=3.5,
        )
        self._submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="following",
            media_id=following_id,
            timeline_start_s=3,
            source_start_s=0,
            source_end_s=1,
        )
        self._submit(
            "APPLY_SPEED_CURVE",
            {"kind": "clip", "clip_id": "delayed"},
            curve=SpeedCurve.constant(1.5, 2).wire(),
            interpolation="none",
        )
        rendered = self._render_job("master")
        self.assertEqual(frame_count(rendered), 75)
        self.assertLess(tone_amplitude(audio_samples(rendered, 0.05, 0.1), 440), 0.001)
        self.assertGreater(tone_amplitude(audio_samples(rendered, 0.4, 0.2), 440), 0.02)
        self.assertLess(tone_amplitude(audio_samples(rendered, 1.35, 0.1), 440), 0.001)
        self.assertGreater(tone_amplitude(audio_samples(rendered, 1.7, 0.2), 660), 0.02)

    def test_measured_audio_bounds_survive_dissolve_acrossfade(self) -> None:
        source = self._delayed_audio_fixture()
        source_id, following_id = self._import(source), self._import(self.bed)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        for clip_id, media_id, start, end in (
            ("delayed", source_id, 0, 4),
            ("following", following_id, 4, 1),
        ):
            self._submit(
                "ADD_CLIP",
                {"kind": "track", "track_id": "V1"},
                clip_id=clip_id,
                media_id=media_id,
                timeline_start_s=start,
                source_start_s=0,
                source_end_s=end,
            )
        self._submit(
            "APPLY_TRANSITION",
            {"kind": "track", "track_id": "V1"},
            transition_id="delayed-dissolve",
            effect_id="crossfade",
            effect_version=1,
            from_clip_id="delayed",
            to_clip_id="following",
            duration_s=0.5,
        )
        rendered = self._render_job("master")
        self.assertEqual(frame_count(rendered), 135)
        self.assertLess(tone_amplitude(audio_samples(rendered, 0.25, 0.2), 440), 0.001)
        self.assertGreater(tone_amplitude(audio_samples(rendered, 1.5, 0.2), 440), 0.02)
        self.assertLess(tone_amplitude(audio_samples(rendered, 3.2, 0.2), 440), 0.001)
        self.assertGreater(tone_amplitude(audio_samples(rendered, 3.75, 0.2), 660), 0.02)

    def test_valid_steep_speed_curve_stays_within_internal_retime_point_limit(self) -> None:
        red_id = self._import(self.red)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        self._submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="c1",
            media_id=red_id,
            timeline_start_s=0.0,
            source_start_s=0.0,
            source_end_s=2.0,
        )
        curve = SpeedCurve((SpeedPoint(0.0, 0.5), SpeedPoint(2.0, 0.5, "hold"), SpeedPoint(3.0, 2.0, "hold")))
        self._submit(
            "APPLY_SPEED_CURVE",
            {"kind": "clip", "clip_id": "c1"},
            curve=curve.wire(),
            interpolation="none",
        )
        rendered = self._render_job("master")
        self.assertGreater(tone_amplitude(audio_samples(rendered, 1.0, 0.2), 440), 0.02)

    def _render_retimed_followed_by_bed(self, source: Path, span: float, curve: SpeedCurve) -> Path:
        source_id, following_id = self._import(source), self._import(self.bed)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        for clip_id, media_id, start, end in (
            ("c1", source_id, 0.0, span),
            ("c2", following_id, span, 1.0),
        ):
            self._submit(
                "ADD_CLIP",
                {"kind": "track", "track_id": "V1"},
                clip_id=clip_id,
                media_id=media_id,
                timeline_start_s=start,
                source_start_s=0.0,
                source_end_s=end,
            )
        self._submit(
            "APPLY_SPEED_CURVE",
            {"kind": "clip", "clip_id": "c1"},
            curve=curve.wire(),
            interpolation="none",
        )
        return self._render_job("master")

    def _assert_audio_boundary(self, samples: list[float], at: float, before: int, after: int) -> None:
        # A 10 ms detector locates the actual audible event independently of the
        # renderer's duration metadata. Demand the existing one-frame tolerance.
        measurements = []
        for step in range(-12, 13):
            center = at + step * 0.005
            window = samples[round((center - 0.005) * 48000) : round((center + 0.005) * 48000)]
            measurements.append((center, tone_amplitude(window, after) > tone_amplitude(window, before)))
        crossings = [center for center, incoming in measurements if incoming]
        self.assertTrue(crossings, f"no {before}->{after} Hz boundary near {at}")
        self.assertAlmostEqual(crossings[0], at, delta=1 / 30)
        for center, frequency in ((at - 0.05, before), (at + 0.05, after)):
            window = samples[round((center - 0.01) * 48000) : round((center + 0.01) * 48000)]
            self.assertGreater(tone_amplitude(window, frequency), 0.05)

    def test_linear_speed_preserves_internal_sound_event_and_exact_following_cut(self) -> None:
        # Arrival easing is linear: v(t)=0.5+0.9375*t after fitting to 2 s.
        # Integrating and solving s(t)=1 gives 1.02158717198 s; s(1.6)=2.
        curve = SpeedCurve((SpeedPoint(0.0, 0.5), SpeedPoint(3.0, 2.0, "linear")))
        master = self._render_retimed_followed_by_bed(self.landmark, 2.0, curve)
        samples = audio_samples(master, 0.0, 2.6)
        self._assert_audio_boundary(samples, 1.02158717198, 440, 880)
        self._assert_audio_boundary(samples, 1.6, 880, 660)
        end_of_first = samples[round(1.45 * 48000) : round(1.55 * 48000)]
        self.assertGreater(tone_amplitude(end_of_first, 880), 0.1)
        self.assertLess(tone_amplitude(end_of_first, 660), 0.01)
        frames = rgb_frames(master)
        self.assertEqual(len(frames), 78)
        self.assertGreater(sum(frames[47][1::3]), sum(frames[47][0::3]))
        self.assertLess(max(frames[48]), 5)
        green_frame = next(i for i, frame in enumerate(frames) if frame[1] > frame[0])
        self.assertEqual(green_frame, 31)
        self.assertEqual({path: sha256(path) for path in self.original_hashes}, self.original_hashes)

    def test_slow_motion_preserves_native_high_frame_rate_landmark(self) -> None:
        source = self.media / "high-frame-rate-landmark.mp4"
        run(
            FFMPEG,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=120:d=0.5",
            "-f",
            "lavfi",
            "-i",
            r"aevalsrc='if(lt(t,0.225)\,0.2*sin(2*PI*440*t)\,0.2*sin(2*PI*880*t))':s=48000:d=0.5",
            "-vf",
            "drawbox=c=green:t=fill:enable='eq(n,27)'",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(source),
        )
        source_id = self._import(source)
        self._submit("ADD_TRACK", {"kind": "project"}, track_id="V1", kind="video")
        self._submit(
            "ADD_CLIP",
            {"kind": "track", "track_id": "V1"},
            clip_id="c1",
            media_id=source_id,
            timeline_start_s=0.0,
            source_start_s=0.0,
            source_end_s=0.5,
        )
        self._submit(
            "APPLY_SPEED_CURVE",
            {"kind": "clip", "clip_id": "c1"},
            curve=SpeedCurve.constant(2.0, 0.25).wire(),
            interpolation="none",
        )
        rendered = self._render_job("master")
        frames = rgb_frames(rendered)
        green_frames = [index for index, frame in enumerate(frames) if sum(frame[1::3]) > sum(frame[0::3])]
        self.assertEqual(len(frames), 60)
        self.assertTrue(green_frames)
        self.assertAlmostEqual(green_frames[0] / 30, 0.9, delta=1 / 30)
        self._assert_audio_boundary(audio_samples(rendered, 0.0, 1.1), 0.9, 440, 880)

    def test_public_ramp_renders_slope_changes_and_following_cut(self) -> None:
        source = self.media / "ramp-landmarks.mp4"
        run(
            FFMPEG,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=100:d=2.04",
            "-f",
            "lavfi",
            "-i",
            r"aevalsrc='0.2*sin(2*PI*if(lt(t,0.5)\,440\,if(lt(t,1)\,880\,if(lt(t,1.5)\,330\,990)))*t)':s=48000:d=2.04",
            "-vf",
            "drawbox=c=green:t=fill:enable='gte(t,0.5)',drawbox=c=blue:t=fill:enable='gte(t,1)',drawbox=c=yellow:t=fill:enable='gte(t,1.5)'",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(source),
        )
        original = sha256(source)
        master = self._render_retimed_followed_by_bed(source, 2.04, SpeedCurve.ramp(4.0, 0.3))
        samples = audio_samples(master, 0.0, 5.0)
        # Independently solved ease-in-out integrals, including both changing slopes.
        for at, before, after in (
            (0.610795305, 440, 880),
            (2.166666667, 880, 330),
            (3.399154567, 330, 990),
            (4.0, 990, 660),
        ):
            self._assert_audio_boundary(samples, at, before, after)
        frames = rgb_frames(master)
        self.assertEqual(len(frames), 150)
        self.assertGreater(sum(frames[119][0::3]), sum(frames[119][2::3]))
        self.assertLess(max(frames[120]), 5)
        boundaries = [
            i for i in range(1, len(frames)) if mean_absolute_error(frames[i - 1][:3], frames[i][:3]) > 50
        ]
        self.assertEqual(boundaries, [18, 65, 102, 120])
        self.assertEqual(sha256(source), original)

    def test_retime_endpoint_roundoff_does_not_add_a_cut_frame(self) -> None:
        # 2 / 1.2 seconds is exactly 50 frames at 30 fps, although the graph's
        # canonical nine-decimal representation rounds that duration upward.
        master = self._render_retimed_followed_by_bed(self.landmark, 2.0, SpeedCurve.constant(2.0, 1.2))
        frames = rgb_frames(master)
        self.assertEqual(len(frames), 80)
        self.assertGreater(frames[49][1], frames[49][0])
        self.assertLess(max(frames[50]), 5)
        self._assert_audio_boundary(audio_samples(master, 0, 8 / 3), 5 / 3, 880, 660)


if __name__ == "__main__":
    unittest.main()
