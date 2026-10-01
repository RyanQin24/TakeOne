"""Original-file transfer failures must not publish incomplete or wrong footage."""

import asyncio
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from takeone.phone.capture import PhoneTake
from takeone.phone.client import CameraError
from takeone.phone.transfer import clean_interrupted_copies, copy_original, enqueue, valid_clip


class Files:
    def __init__(self, payload=b"original-video", *, changed=False, disconnect=False):
        self.payload = payload
        self.offset = 0
        self.stats = 0
        self.changed = changed
        self.disconnect = disconnect
        self.closed = False

    async def stat(self, path):
        self.stats += 1
        return {
            "st_ifmt": "S_IFREG",
            "st_size": len(self.payload),
            "st_mtime": 2 if self.changed and self.stats > 1 else 1,
        }

    async def fopen(self, path, mode):
        assert mode == "r"
        return 1

    async def fread(self, handle, size):
        if self.disconnect:
            raise OSError("USB unplugged")
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    async def fclose(self, handle):
        self.closed = True


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clip = {"clipUniqueId": 42, "filePath": "Camera_C001.mov", "fileSize": 14}

    def copy(self, files):
        return asyncio.run(copy_original(files, self.clip, self.root))

    def test_usb_original_is_streamed_verified_and_atomically_published(self):
        files = Files()
        receipt = self.copy(files)
        self.assertEqual((self.root / self.clip["filePath"]).read_bytes(), files.payload)
        self.assertEqual(receipt["sha256"], hashlib.sha256(files.payload).hexdigest())
        self.assertTrue(files.closed)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_disconnect_leaves_no_video_and_a_retry_succeeds(self):
        with self.assertRaisesRegex(OSError, "unplugged"):
            self.copy(Files(disconnect=True))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.copy(Files())["size_bytes"], 14)

    def test_growing_file_is_not_published(self):
        with self.assertRaisesRegex(OSError, "changed"):
            self.copy(Files(changed=True))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_different_existing_original_is_never_overwritten(self):
        target = self.root / self.clip["filePath"]
        target.write_bytes(b"different-original")
        with self.assertRaises(FileExistsError):
            self.copy(Files())
        self.assertEqual(target.read_bytes(), b"different-original")

    def test_identical_existing_original_is_idempotent(self):
        self.copy(Files())
        receipt = self.copy(Files())
        self.assertEqual(receipt["size_bytes"], 14)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_source_size_must_match_the_stopped_clip(self):
        with self.assertRaisesRegex(ValueError, "expected size"):
            self.copy(Files(b"too short"))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unsafe_phone_paths_are_rejected(self):
        for name in ("../a.mov", "..\\a.mov", "C:a.mov", "x:stream.mov", "x.mov ", "x.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                valid_clip({**self.clip, "filePath": name})

    def test_queue_survives_repeated_stop_notifications(self):
        first = enqueue(self.clip, root=self.root)
        self.assertEqual(first, enqueue(self.clip, root=self.root))
        self.assertEqual(len(list((self.root / "jobs").glob("*.json"))), 1)

    def test_restart_cleans_only_the_workers_own_incomplete_files(self):
        own = self.root / (".takeone-usb-" + "a" * 32 + ".partial")
        other = self.root / "other.partial"
        own.write_bytes(b"unfinished")
        other.write_bytes(b"preserve")
        clean_interrupted_copies(self.root)
        self.assertFalse(own.exists())
        self.assertEqual(other.read_bytes(), b"preserve")

    def capture(self, clips):
        take = object.__new__(PhoneTake)
        take.auto_transfer = True
        take.clips_before = {"41": {"clipUniqueId": 41}}
        take.folder = self.root
        take.report = {}
        take._read_clips = lambda: clips
        return take

    def test_actual_phone_filename_is_bound_to_the_take(self):
        take = self.capture({"41": {}, "42": self.clip})
        with patch("takeone.phone.capture.enqueue", return_value="job.json") as queue:
            take._queue_original()
        queue.assert_called_once_with(self.clip, self.root)
        self.assertEqual(take.report["clip"]["filePath"], "Camera_C001.mov")

    def test_ambiguous_clip_readback_does_not_copy_the_wrong_take(self):
        take = self.capture({"41": {}, "42": self.clip, "43": self.clip})
        with patch("takeone.phone.capture.enqueue") as queue:
            take._queue_original()
        queue.assert_not_called()
        self.assertEqual(take.report["transfer_state"], "needs_attention")

    def test_stop_acknowledgement_is_required_before_queueing(self):
        for confirmed in (True, False):
            with self.subTest(confirmed=confirmed):
                take = self.capture({"42": self.clip})
                take.closed = False
                take.finished = threading.Event()
                take.thread = take.health_thread = None
                take.report = {"start_attempted": True, "stop_confirmed": False, "error": None}
                take.client = Mock()
                if not confirmed:
                    take.client.wait_recording.side_effect = CameraError("stop unconfirmed")
                with patch.object(take, "_queue_original") as queue:
                    take.close()
                self.assertEqual(queue.call_count, int(confirmed))

    def test_full_take_lifecycle_queues_the_new_original_after_stop(self):
        camera = Mock()
        camera.probe.return_value = {"recording": False, "fingerprint": "same"}
        stopped = False
        calls = []

        def request(method, path, *args):
            nonlocal stopped
            calls.append(path)
            if path == "/clips":
                return {"clips": [self.clip] if stopped else []}
            if path == "/transports/0/stop":
                stopped = True
            return None

        camera.request.side_effect = request
        config = {
            "calibration": [{"focal_mm": 24, "normalised": 0}, {"focal_mm": 48, "normalised": 1}],
            "zoom_hz": 20,
            "fingerprint": "same",
            "color": {},
            "auto_transfer": True,
        }
        with (
            patch("takeone.phone.capture.apply_color", return_value={}),
            patch(
                "takeone.phone.capture.enqueue",
                return_value="job.json",
            ) as queue,
        ):
            with PhoneTake(
                config, {"plan_id": "take-1", "duration_s": 0}, self.root, threading.Event(), client=camera
            ) as take:
                queue.assert_not_called()
            queue.assert_called_once_with(self.clip, self.root)
        self.assertEqual(calls, ["/clips", "/transports/0/record", "/transports/0/stop", "/clips"])
        self.assertTrue(take.report["stop_confirmed"])
        self.assertEqual(take.report["clip"], self.clip)


if __name__ == "__main__":
    unittest.main()
