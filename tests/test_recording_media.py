import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from takeone.recording import (
    RecordingError,
    RecordingService,
    SimulatedRecorder,
    SyntheticMediaWriter,
    ZoomRamp,
)
from takeone.recording.media import MediaWriteError

FFMPEG = Path(shutil.which("ffmpeg") or "ffmpeg")
FFPROBE = Path(shutil.which("ffprobe") or "ffprobe")


class Clock:
    def __init__(self):
        self.value = 1_000_000_000_000_000_000

    def __call__(self):
        return self.value

    def advance_ms(self, milliseconds):
        self.value += milliseconds * 1_000_000


class DamagedPacketWriter(SyntheticMediaWriter):
    """Damage a real encoded packet before the writer validates its partial file."""

    def _run(self, argv, *, code, tool):
        result = super()._run(argv, code=code, tool=tool)
        if code == "media_generation_failed":
            partial = Path(argv[-1])
            packets = subprocess.run(
                [
                    str(self.ffprobe),
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_packets",
                    "-show_entries",
                    "packet=pos,size",
                    "-of",
                    "json",
                    str(partial),
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
            packet = json.loads(packets.stdout)["packets"][2]
            position, size = int(packet["pos"]), int(packet["size"])
            damaged = bytearray(partial.read_bytes())
            start, end = position + 20, position + min(size, 120)
            damaged[start:end] = bytes(end - start)
            partial.write_bytes(damaged)
            self.permissive_decode = subprocess.run(
                [str(self.ffmpeg), "-v", "error", "-nostdin", "-i", str(partial), "-f", "null", "-"],
                check=False,
                capture_output=True,
                timeout=10,
            )
        return result


class RecordingMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.writer = SyntheticMediaWriter(ffmpeg=FFMPEG, ffprobe=FFPROBE, timeout_seconds=10)

    def test_real_ffmpeg_output_decodes_has_expected_streams_duration_and_stays_immutable(self):
        first = self.writer.write("00000000-0000-0000-0000-000000000001", self.root, 500, "normal")
        first_path = self.root / first["relative_path"]
        original = first_path.read_bytes()
        self.assertEqual(first["sha256"], hashlib.sha256(original).hexdigest())
        self.assertGreater(first["size_bytes"], 0)
        self.assertLessEqual(abs(first["duration_ms"] - 500), 150)
        self.assertEqual({stream["codec_type"] for stream in first["streams"]}, {"audio", "video"})
        video = next(stream for stream in first["streams"] if stream["codec_type"] == "video")
        self.assertEqual(video["codec_name"], "h264")
        self.assertEqual(first["probe"]["streams"], first["streams"])
        self.assertEqual(first["probe"]["format"]["size"], str(first["size_bytes"]))
        subprocess.run(
            [str(FFMPEG), "-v", "error", "-nostdin", "-i", str(first_path), "-f", "null", "-"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        second = self.writer.write("00000000-0000-0000-0000-000000000002", self.root, 250, "normal")
        self.assertTrue((self.root / second["relative_path"]).is_file())
        self.assertEqual(first_path.read_bytes(), original)
        with self.assertRaises(MediaWriteError) as raised:
            self.writer.write("00000000-0000-0000-0000-000000000001", self.root, 500, "normal")
        self.assertEqual(raised.exception.code, "refused_overwrite")
        self.assertEqual(first_path.read_bytes(), original)

    def test_writer_rejects_noncanonical_take_directory_identity(self):
        escaped = self.root.parent / f"escape-{self.root.name}"
        with self.assertRaises(ValueError):
            self.writer.write(f"../{escaped.name}", self.root, 250, "normal")
        self.assertFalse(escaped.exists())

    def test_corrupt_media_and_save_failure_never_publish_ready_artifact(self):
        corrupt_id = "00000000-0000-0000-0000-000000000003"
        with self.assertRaises(MediaWriteError) as raised:
            self.writer.write(corrupt_id, self.root, 250, "corrupt_media")
        self.assertEqual(raised.exception.code, "corrupt_media")
        self.assertFalse((self.root / corrupt_id / "synthetic.mp4").exists())

        failed_id = "00000000-0000-0000-0000-000000000004"
        with self.assertRaises(MediaWriteError) as raised:
            self.writer.write(failed_id, self.root, 250, "save_failure")
        self.assertEqual(raised.exception.code, "save_failure")
        self.assertFalse((self.root / failed_id / "synthetic.mp4").exists())

    def test_missing_media_tool_is_explicitly_unavailable(self):
        writer = SyntheticMediaWriter(
            ffmpeg=self.root / "missing-ffmpeg",
            ffprobe=self.root / "missing-ffprobe",
            timeout_seconds=1,
        )
        with self.assertRaises(MediaWriteError) as raised:
            writer.write("00000000-0000-0000-0000-000000000005", self.root, 250, "normal")
        self.assertEqual(raised.exception.code, "media_tool_unavailable")
        self.assertIn("ffmpeg", str(raised.exception).lower())

    def test_damaged_packet_with_successful_permissive_decode_is_not_published(self):
        writer = DamagedPacketWriter(ffmpeg=FFMPEG, ffprobe=FFPROBE, timeout_seconds=10)
        take_id = "00000000-0000-0000-0000-000000000006"
        with self.assertRaises(MediaWriteError) as raised:
            writer.write(take_id, self.root, 1000, "normal")
        self.assertEqual(writer.permissive_decode.returncode, 0)
        self.assertTrue(writer.permissive_decode.stderr)
        self.assertEqual(raised.exception.code, "corrupt_media")
        self.assertTrue((self.root / take_id / "synthetic.partial.mp4").is_file())
        self.assertFalse((self.root / take_id / "synthetic.mp4").exists())

    def test_damaged_packet_fails_take_without_ready_media(self):
        clock = Clock()
        writer = DamagedPacketWriter(ffmpeg=FFMPEG, ffprobe=FFPROBE, timeout_seconds=10)
        media_root = self.root / "media"
        service = RecordingService(
            self.root / "recording.sqlite3",
            media_root,
            clock=clock,
            simulator=SimulatedRecorder(start_delay_ms=1, delayed_start_ms=2, timeout_ms=3),
            media_writer=writer,
        )
        self.addCleanup(service.close)
        take = service.start("start-damaged", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 1000))
        clock.advance_ms(1)
        self.assertEqual(service.get(take["take_id"])["state"], "recording")
        service.stop(take["take_id"], "stop-damaged")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = service.get(take["take_id"])
            if result["state"] != "finalizing":
                break
            time.sleep(0.02)
        self.assertEqual(writer.permissive_decode.returncode, 0)
        self.assertTrue(writer.permissive_decode.stderr)
        self.assertEqual(result["state"], "failed", (result, writer.permissive_decode.stderr))
        self.assertEqual(result["error"]["code"], "corrupt_media")
        self.assertIsNone(result["media"])
        self.assertFalse(result["real_media_verified"])
        self.assertFalse((media_root / take["take_id"] / "synthetic.mp4").exists())
        with self.assertRaises(RecordingError) as raised:
            service.media_path(take["take_id"])
        self.assertEqual(raised.exception.code, "media_unavailable")

    def test_service_rejects_changed_ready_file_instead_of_serving_it(self):
        clock = Clock()
        service = RecordingService(
            self.root / "recording.sqlite3",
            self.root / "media",
            clock=clock,
            simulator=SimulatedRecorder(start_delay_ms=1, delayed_start_ms=2, timeout_ms=3),
            media_writer=self.writer,
        )
        self.addCleanup(service.close)
        take = service.start("start-1", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 250))
        clock.advance_ms(1)
        self.assertEqual(service.get(take["take_id"])["state"], "recording")
        service.stop(take["take_id"], "stop-1")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = service.get(take["take_id"])
            if result["state"] != "finalizing":
                break
            time.sleep(0.02)
        self.assertEqual(result["state"], "ready", result)
        path = service.media_path(take["take_id"])
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaises(RecordingError) as raised:
            service.media_path(take["take_id"])
        self.assertEqual(raised.exception.code, "media_integrity_failed")

    def test_writer_failures_are_persisted_and_do_not_claim_real_media(self):
        for scenario, expected in (("save_failure", "save_failure"), ("corrupt_media", "corrupt_media")):
            with self.subTest(scenario=scenario):
                database = self.root / f"{scenario}.sqlite3"
                media = self.root / f"media-{scenario}"
                clock = Clock()
                service = RecordingService(
                    database,
                    media,
                    clock=clock,
                    simulator=SimulatedRecorder(start_delay_ms=1, delayed_start_ms=2, timeout_ms=3),
                    media_writer=self.writer,
                )
                self.addCleanup(service.close)
                take = service.start(
                    f"start-{scenario}",
                    {"source": "standalone_fixture"},
                    ZoomRamp(1, 2, 250),
                    scenario,
                )
                clock.advance_ms(1)
                service.get(take["take_id"])
                service.stop(take["take_id"], f"stop-{scenario}")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    result = service.get(take["take_id"])
                    if result["state"] != "finalizing":
                        break
                    time.sleep(0.02)
                self.assertEqual((result["state"], result["error"]["code"]), ("failed", expected))
                self.assertIsNone(result["media"])
                self.assertFalse(result["real_media_verified"])

    def test_recovery_cancels_queued_finalizer_before_media_writer_runs(self):
        clock = Clock()
        media_root = self.root / "queued-media"
        service = RecordingService(
            self.root / "queued.sqlite3",
            media_root,
            clock=clock,
            simulator=SimulatedRecorder(start_delay_ms=1, delayed_start_ms=2, timeout_ms=3),
            media_writer=self.writer,
        )
        self.addCleanup(service.close)
        worker_entered = threading.Event()
        worker_release = threading.Event()
        self.addCleanup(worker_release.set)

        def occupy_worker():
            worker_entered.set()
            worker_release.wait(2)

        blocker = service._executor.submit(occupy_worker)
        self.assertTrue(worker_entered.wait(1))
        take = service.start("start-queued", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 250))
        clock.advance_ms(1)
        service.get(take["take_id"])
        service.stop(take["take_id"], "stop-queued")
        service.recover(take["take_id"], "recover-queued")
        worker_release.set()
        blocker.result(timeout=2)
        time.sleep(0.05)
        self.assertFalse((media_root / take["take_id"]).exists())
        self.assertEqual(service.get(take["take_id"])["state"], "failed")

    def test_finalization_admission_is_released_when_previous_process_ends(self):
        database = self.root / "process-restart.sqlite3"
        media_root = self.root / "process-restart-media"
        marker = self.root / "writer-entered"
        take_file = self.root / "old-take-id"
        child_code = """
import sys
import time
from pathlib import Path
from takeone.recording import RecordingService, SimulatedRecorder, ZoomRamp

class Clock:
    value = 1_000_000_000_000_000_000
    def __call__(self):
        return self.value

class BlockingWriter:
    def write(self, take_id, media_root, duration_ms, scenario):
        Path(sys.argv[3]).write_text("entered", encoding="utf-8")
        time.sleep(60)

clock = Clock()
service = RecordingService(
    Path(sys.argv[1]),
    Path(sys.argv[2]),
    clock=clock,
    simulator=SimulatedRecorder(start_delay_ms=1, delayed_start_ms=2, timeout_ms=3),
    media_writer=BlockingWriter(),
)
take = service.start("start-old", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 250))
Path(sys.argv[4]).write_text(take["take_id"], encoding="utf-8")
clock.value += 1_000_000
service.get(take["take_id"])
service.stop(take["take_id"], "stop-old")
time.sleep(60)
"""
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                child_code,
                str(database),
                str(media_root),
                str(marker),
                str(take_file),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def stop_child():
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

        self.addCleanup(stop_child)
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not marker.exists():
            child.kill()
            child.wait(timeout=5)
            self.fail(f"child writer did not start; exit code {child.returncode}")
        old_take_id = take_file.read_text(encoding="utf-8")
        child.terminate()
        child.wait(timeout=5)

        clock = Clock()
        replacement = RecordingService(
            database,
            media_root,
            clock=clock,
            simulator=SimulatedRecorder(start_delay_ms=1, delayed_start_ms=2, timeout_ms=3),
            media_writer=self.writer,
        )
        self.addCleanup(replacement.close)
        replacement.recover(old_take_id, "recover-old")
        take = replacement.start("start-replacement", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 250))
        clock.advance_ms(1)
        replacement.get(take["take_id"])
        replacement.stop(take["take_id"], "stop-replacement")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = replacement.get(take["take_id"])
            if result["state"] != "finalizing":
                break
            time.sleep(0.02)
        self.assertEqual(result["state"], "ready", result)


if __name__ == "__main__":
    unittest.main()
