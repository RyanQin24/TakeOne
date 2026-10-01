"""Footage that has reached this computer is a separate fact from a take.

A phone take ends with `media_location: phone_internal_storage` and
`media_verified: false`, because Blackmagic REST hands out transport control,
not frames. Sync does not soften that. It answers a different question — is
there a file with this take's clip name on this disk — and writes its answer
beside the inbox instead of into the take.
"""

import tempfile
import unittest
from pathlib import Path

from takeone.recording import sync

PLAN_ID = "e" * 64


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def take(self, plan_id=PLAN_ID, take_id="take-1", state="ready"):
        return {"take_id": take_id, "plan_id": plan_id, "state": state, "source": "phone"}

    def write(self, name, payload=b"clip"):
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_a_take_with_no_file_stays_on_the_phone(self):
        report = sync.reconcile([self.take()], self.root)
        self.assertEqual(report["synced_count"], 0)
        self.assertFalse(report["takes"][0]["synced"])
        self.assertIsNone(report["takes"][0]["media"])
        self.assertFalse(report["media_verified"])

    def test_a_clip_named_for_the_take_is_matched_with_its_digest(self):
        self.write(f"{sync.clip_name(PLAN_ID)}_0001.mov", b"a" * 64)
        report = sync.reconcile([self.take()], self.root)
        self.assertEqual(report["synced_count"], 1)
        media = report["takes"][0]["media"]
        self.assertEqual(media["size_bytes"], 64)
        self.assertTrue(media["fully_hashed"])
        self.assertEqual(len(media["sha256"]), 64)
        # Having the bytes is not having judged the picture.
        self.assertFalse(report["takes"][0]["media_reviewed"])

    def test_a_file_belonging_to_no_take_is_listed_rather_than_guessed_at(self):
        self.write("IMG_4411.mov")
        report = sync.reconcile([self.take()], self.root)
        self.assertEqual(report["synced_count"], 0)
        self.assertEqual([entry["name"] for entry in report["unmatched"]], ["IMG_4411.mov"])

    def test_a_non_clip_file_is_ignored(self):
        self.write(f"{sync.clip_name(PLAN_ID)}.txt")
        report = sync.reconcile([self.take()], self.root)
        self.assertEqual(report["file_count"], 0)
        self.assertFalse(report["takes"][0]["synced"])

    def test_actual_device_filename_is_matched_without_renaming(self):
        self.write("Camera_C002.mov", b"12345")
        take = {
            **self.take(),
            "device_reported": {
                "clip": {
                    "filePath": "Camera_C002.mov",
                    "fileSize": 5,
                }
            },
        }
        self.assertEqual(sync.reconcile([take], self.root)["synced_count"], 1)
        self.write("Camera_C002.mov", b"short")
        take["device_reported"]["clip"]["fileSize"] = 50
        self.assertEqual(sync.reconcile([take], self.root)["synced_count"], 0)

    def test_changed_file_invalidates_the_digest_cache(self):
        self.write("Camera_C002.mov", b"old")
        first = sync.scan(self.root)[0]["sha256"]
        self.write("Camera_C002.mov", b"new original")
        self.assertNotEqual(sync.scan(self.root)[0]["sha256"], first)

    def test_simulated_takes_are_not_phone_footage(self):
        report = sync.reconcile([{**self.take(), "source": "simulated"}], self.root)
        self.assertEqual(report["takes"], [])

    def test_the_manifest_is_written_beside_the_inbox(self):
        report = sync.reconcile([self.take()], self.root)
        path = sync.write_manifest(report, self.root)
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "sync-manifest.json")


if __name__ == "__main__":
    unittest.main()
