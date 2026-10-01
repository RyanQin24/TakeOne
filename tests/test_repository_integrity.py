"""Verify publication checks preserve source and authenticate hydrated LFS files."""

import hashlib
import json
import shutil
import subprocess
import sys
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


class PreservationScriptTests(unittest.TestCase):
    def test_nested_repository_reports_default_and_custom_destinations(self):
        root = Path(__file__).resolve().parents[1]
        for changed in (False, True):
            for custom in (False, True):
                with (
                    self.subTest(changed=changed, custom=custom),
                    # A fixture is a complete independent repository. Keep it
                    # outside the live checkout so workspace Git/file watchers
                    # cannot hold its nested directory during Windows cleanup.
                    tempfile.TemporaryDirectory(prefix="takeone-integrity-") as temporary,
                ):
                    fixture = Path(temporary)
                    script = fixture / "scripts/check_integrity.py"
                    script.parent.mkdir()
                    shutil.copyfile(root / "scripts/check_integrity.py", script)
                    nested = fixture / "lerobot"
                    audit = nested / "configs/cinebot/calibration_audit.json"
                    audit.parent.mkdir(parents=True)
                    original = b'{"evidence": "' + b"x" * 1200 + b'"}\n'
                    audit.write_bytes(original)
                    imported = fixture / "calibration/evidence/calibration_audit.json"
                    imported.parent.mkdir(parents=True)
                    imported.write_bytes(original)

                    def git(*arguments):
                        return subprocess.check_output(
                            [
                                "git",
                                "-C",
                                str(nested),
                                "-c",
                                "core.hooksPath=/dev/null",
                                "-c",
                                "commit.gpgsign=false",
                                "-c",
                                "user.name=Fixture",
                                "-c",
                                "user.email=fixture@example.invalid",
                                *arguments,
                            ],
                            stderr=subprocess.STDOUT,
                        )

                    git("init")
                    git("add", ".")
                    git("commit", "-m", "Preserved fixture")
                    snapshot = fixture / "archive/recovery/20260912T023620Z"
                    snapshot.mkdir(parents=True)
                    (snapshot / "manifest.json").write_text(
                        json.dumps(
                            {
                                "files": [
                                    {
                                        "path": audit.relative_to(fixture).as_posix(),
                                        "sha256": hashlib.sha256(original).hexdigest(),
                                        "bytes": len(original),
                                    }
                                ]
                            }
                        )
                    )
                    (snapshot / "lerobot-head.txt").write_bytes(git("rev-parse", "HEAD"))
                    (snapshot / "lerobot-status.txt").write_bytes(git("status", "--porcelain=v1", "-uall"))
                    if changed:
                        audit.write_bytes(original + b" ")
                    caller = fixture / "caller"
                    caller.mkdir()
                    arguments = ["--output-dir", "reports"] if custom else []
                    result = subprocess.run(
                        [sys.executable, str(script), *arguments],
                        cwd=caller,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(result.returncode, int(changed), result.stdout + result.stderr)
                    target = caller / "reports" if custom else fixture / "data/verification"
                    self.assertTrue((target / "preservation.json").is_file(), result.stderr)
                    report = json.loads((target / "preservation.json").read_text())
                    self.assertEqual(report, json.loads(result.stdout))
                    self.assertTrue(report["nested_git_history_checked"])
                    self.assertEqual(report["lerobot_files_checked"], 1)
                    self.assertEqual(report["passed"], not changed)
                    self.assertEqual(
                        set(report["failures"]),
                        {
                            "lerobot/configs/cinebot/calibration_audit.json",
                            "lerobot-status.txt",
                            "imported calibration audit",
                        }
                        if changed
                        else set(),
                    )
                    self.assertEqual(imported.read_bytes(), original)
                    if custom:
                        self.assertFalse((fixture / "data/verification").exists())
