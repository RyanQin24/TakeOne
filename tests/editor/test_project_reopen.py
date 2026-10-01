"""Persisted initial creative intent must survive reopening and history replay."""

import tempfile
import unittest
from pathlib import Path

from takeone.editor import project
from takeone.editor.errors import MigrationError
from takeone.editor.operations import OperationType, Target
from takeone.editor.repository import ProjectRepository
from takeone.editor.service import EditorService

from tests.editor.support import media_op, op


class ReopenProjectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "projects.sqlite3"
        self.service = EditorService(ProjectRepository(self.path))
        self.intent = {"prompt": "A quiet decision", "target_duration_s": 12}
        self.service.create("film", "Film", intent=self.intent)

    def reopen(self):
        return EditorService(ProjectRepository(self.path))

    def test_initial_brief_survives_reopen_without_operations(self):
        self.assertEqual(self.reopen().state("film").intent.prompt, self.intent["prompt"])

    def test_initial_brief_survives_import_reopen_and_undo(self):
        self.service.submit("film", media_op())
        reopened = self.reopen()
        self.assertIn("m1", reopened.state("film").media)
        self.assertEqual(reopened.state("film").intent.prompt, self.intent["prompt"])
        reopened.undo("film")
        self.assertEqual(self.reopen().state("film").intent.prompt, self.intent["prompt"])
        self.assertFalse(self.reopen().state("film").media)

    def test_logged_intent_still_detects_tampered_snapshot(self):
        self.service.submit(
            "film",
            op(
                OperationType.SET_INTENT,
                Target.project(),
                intent={"prompt": "New idea", "target_duration_s": 12},
            ),
        )
        snapshot = self.service.repository.snapshot("film")["state"]
        snapshot["intent"]["prompt"] = "Tampered"
        history = [row["operation"] for row in self.service.history("film")]
        with self.assertRaises(MigrationError):
            project.rebuild("film", history, snapshot)

    def test_initial_brief_does_not_hide_other_snapshot_corruption(self):
        self.service.submit("film", media_op())
        snapshot = self.service.repository.snapshot("film")["state"]
        snapshot["version"] += 1
        history = [row["operation"] for row in self.service.history("film")]
        with self.assertRaises(MigrationError):
            project.rebuild("film", history, snapshot)
