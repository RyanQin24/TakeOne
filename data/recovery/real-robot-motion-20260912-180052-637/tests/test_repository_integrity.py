"""Verify publication checks preserve source and authenticate hydrated LFS files."""

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.check_integrity import matches_snapshot


class RepositoryIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "artifact.bin"

    def entry(self, original):
        return {
            "path": "lerobot/tests/artifacts/example.bin",
            "bytes": len(original),
            "sha256": hashlib.sha256(original).hexdigest(),
        }

    def test_original_bytes_need_no_git_access(self):
        original = b"preserved\r\nsource\r\n"
        self.path.write_bytes(original)
        with patch("scripts.check_integrity.subprocess.run") as git:
            self.assertTrue(matches_snapshot(self.path, self.entry(original)))
        git.assert_not_called()

    def test_changed_source_is_rejected(self):
        original = b"original source\n"
        self.path.write_bytes(b"changed source\n")
        result = subprocess.CompletedProcess([], 0, original, b"")
        with patch("scripts.check_integrity.subprocess.run", return_value=result):
            self.assertFalse(matches_snapshot(self.path, self.entry(original)))

    def test_lfs_payload_requires_original_pointer_and_matching_hash_and_size(self):
        payload = b"actual upstream artifact"
        oid = hashlib.sha256(payload).hexdigest()
        pointer = (
            f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {len(payload)}\n"
        ).encode()
        self.path.write_bytes(payload)
        for stored_pointer, expected in (
            (pointer, True),
            (pointer.replace(oid.encode(), b"0" * 64), False),
        ):
            with self.subTest(pointer=stored_pointer):
                result = subprocess.CompletedProcess([], 0, stored_pointer, b"")
                with patch("scripts.check_integrity.subprocess.run", return_value=result):
                    self.assertEqual(matches_snapshot(self.path, self.entry(pointer)), expected)
        result = subprocess.CompletedProcess([], 0, pointer, b"")
        self.path.write_bytes(payload + b"corruption")
        with patch("scripts.check_integrity.subprocess.run", return_value=result):
            self.assertFalse(matches_snapshot(self.path, self.entry(pointer)))

    def test_lfs_size_mismatch_is_rejected_even_with_matching_hash(self):
        payload = b"artifact"
        oid = hashlib.sha256(payload).hexdigest()
        pointer = (
            f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {len(payload) + 1}\n"
        ).encode()
        self.path.write_bytes(payload)
        result = subprocess.CompletedProcess([], 0, pointer, b"")
        with patch("scripts.check_integrity.subprocess.run", return_value=result):
            self.assertFalse(matches_snapshot(self.path, self.entry(pointer)))
