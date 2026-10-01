"""Exercise verification output routing through isolated script subprocesses."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VerificationScriptTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.fixture_root = Path(self.folder.name) / "repository"
        self.caller = Path(self.folder.name) / "caller"
        (self.fixture_root / "scripts").mkdir(parents=True)
        self.caller.mkdir()
        shutil.copy2(ROOT / "scripts/verify.py", self.fixture_root / "scripts/verify.py")

        hooks = Path(self.folder.name) / "hooks"
        hooks.mkdir()
        (hooks / "sitecustomize.py").write_text(
            """\
import os
import subprocess

call_index = 0

def successful_run(command, **kwargs):
    global call_index
    current = call_index
    call_index += 1
    fail_at = int(os.environ.get(\"TAKEONE_TEST_FAILURE_INDEX\", \"-1\"))
    exit_code = 7 if current == fail_at else 0
    return subprocess.CompletedProcess(command, exit_code, b\"isolated check result\\n\", b\"\")

subprocess.run = successful_run
""",
            encoding="utf-8",
        )
        self.environment = dict(os.environ)
        self.environment["PYTHONPATH"] = str(hooks)

    def test_custom_output_directory_is_resolved_from_callers_working_directory(self):
        result = subprocess.run(
            [
                sys.executable,
                str(self.fixture_root / "scripts/verify.py"),
                "--output-dir",
                "voice-verification",
            ],
            cwd=self.caller,
            env=self.environment,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary_path = self.caller / "voice-verification/summary.json"
        self.assertTrue(summary_path.is_file())
        self.assertFalse((self.fixture_root / "data/verification/summary.json").exists())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(len(summary["checks"]), 7)
        self.assertEqual(
            summary["checks"][4]["command"][-2:],
            ["--output-dir", str((self.caller / "voice-verification").resolve())],
        )

    def test_default_output_directory_remains_inside_repository_fixture(self):
        result = subprocess.run(
            [sys.executable, str(self.fixture_root / "scripts/verify.py")],
            cwd=self.caller,
            env=self.environment,
            capture_output=True,
        )

        default_destination = (self.fixture_root / "data/verification").resolve()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary = json.loads((default_destination / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(len(summary["checks"]), 7)
        self.assertEqual(
            summary["checks"][4]["command"][-2:],
            ["--output-dir", str(default_destination)],
        )
        self.assertFalse((self.caller / "data/verification/summary.json").exists())

    def test_one_failed_check_propagates_after_all_seven_checks_run(self):
        environment = dict(self.environment)
        environment["TAKEONE_TEST_FAILURE_INDEX"] = "2"
        result = subprocess.run(
            [
                sys.executable,
                str(self.fixture_root / "scripts/verify.py"),
                "--output-dir",
                "failed-verification",
            ],
            cwd=self.caller,
            env=environment,
            capture_output=True,
        )

        summary = json.loads((self.caller / "failed-verification/summary.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual([check["exit_code"] for check in summary["checks"]], [0, 0, 7, 0, 0, 0, 0])
        self.assertEqual(len(list((self.caller / "failed-verification").glob("check-*.txt"))), 7)


class IntegrityScriptTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.fixture_root = Path(self.folder.name) / "repository"
        self.caller = Path(self.folder.name) / "caller"
        (self.fixture_root / "scripts").mkdir(parents=True)
        self.caller.mkdir()
        shutil.copy2(ROOT / "scripts/check_integrity.py", self.fixture_root / "scripts/check_integrity.py")
        snapshot = self.fixture_root / "archive/recovery/20260912T023620Z"
        snapshot.mkdir(parents=True)
        (snapshot / "manifest.json").write_text('{"files": []}', encoding="utf-8")
        original = self.fixture_root / "lerobot/configs/cinebot/calibration_audit.json"
        imported = self.fixture_root / "calibration/evidence/calibration_audit.json"
        original.parent.mkdir(parents=True)
        imported.parent.mkdir(parents=True)
        original.write_bytes(b'{"fixture": true}\n')
        imported.write_bytes(original.read_bytes())

    def run_audit(self, *arguments):
        return subprocess.run(
            [sys.executable, str(self.fixture_root / "scripts/check_integrity.py"), *arguments],
            cwd=self.caller,
            capture_output=True,
        )

    def test_custom_output_directory_places_preservation_report_relative_to_caller(self):
        result = self.run_audit("--output-dir", "voice-audit")

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        report_path = self.caller / "voice-audit/preservation.json"
        self.assertTrue(report_path.is_file())
        self.assertTrue(json.loads(report_path.read_text(encoding="utf-8"))["passed"])
        self.assertFalse((self.fixture_root / "data/verification/preservation.json").exists())

    def test_default_preservation_report_remains_inside_repository_fixture(self):
        result = self.run_audit()

        report_path = self.fixture_root / "data/verification/preservation.json"
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(report_path.is_file())
        self.assertTrue(json.loads(report_path.read_text(encoding="utf-8"))["passed"])

    def test_preservation_failure_is_reported_at_custom_destination_and_exits_nonzero(self):
        expected = b"preserved source\n"
        manifest = {
            "files": [
                {
                    "path": "lerobot/example.txt",
                    "bytes": len(expected),
                    "sha256": hashlib.sha256(expected).hexdigest(),
                }
            ]
        }
        snapshot = self.fixture_root / "archive/recovery/20260912T023620Z/manifest.json"
        snapshot.write_text(json.dumps(manifest), encoding="utf-8")
        changed = self.fixture_root / "lerobot/example.txt"
        changed.write_bytes(b"changed source\n")

        result = self.run_audit("--output-dir", "failed-audit")

        report_path = self.caller / "failed-audit/preservation.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["failures"], ["lerobot/example.txt"])


if __name__ == "__main__":
    unittest.main()
